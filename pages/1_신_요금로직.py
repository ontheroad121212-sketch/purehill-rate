# -*- coding: utf-8 -*-
"""
신 요금로직 페이지 (16칸 사다리 · 앵커 캘린더 · Opening/Absolute Floor)
=============================================================================
app.py 는 한 글자도 고치지 않습니다.
Streamlit 은 엔트리 파일 옆의 pages/ 폴더를 자동으로 읽어 왼쪽에 페이지 목록을
만들어 줍니다. 그래서 이 파일을 넣는 것만으로 메뉴가 하나 생깁니다.

폴더 구조
  app.py                      ← 기존 파일. 원본 그대로
  rate_engine_new.py          ← 신 로직 엔진
  pages/1_신_요금로직.py        ← 이 파일
  requirements.txt            ← 그대로

세션 공유
  메인 페이지에서 리포트를 올렸다면 그 데이터(today_df / prev_df)가 이 페이지로
  그대로 넘어옵니다. 이 페이지에서 따로 올려도 되고, 그러면 메인 페이지에도
  같이 반영됩니다 (같은 세션 상태를 쓰기 때문입니다).

기존 로직과 분리되는 것
  사다리 · 요금표 · 시작점 · 상한/하한 · 예외 저장소(applied_rates_v3) ·
  변경 이력(audit_log_v3). 어느 쪽을 고쳐도 반대쪽 요금은 움직이지 않습니다.
=============================================================================
"""

import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import firebase_admin
from firebase_admin import credentials, firestore

import rate_engine_new as eng

st.set_page_config(page_title="신 요금로직", layout="wide")

# =============================================================================
# 1. 파이어베이스 — 메인 페이지와 같은 앱 인스턴스를 씁니다 (중복 초기화 방지)
# =============================================================================
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")

try:
    db = firestore.client()
except Exception as e:
    db = None
    st.warning(f"DB 미연결 — 예외 저장은 이 세션에만 남습니다. ({e})")

COL_SNAPSHOTS = "daily_snapshots"
COL_SETTINGS = "settings"

ROW_MAP = {4: "GDB", 5: "GDF", 6: "FDB", 7: "FDE", 8: "FPT",
           9: "FFD", 10: "HDP", 11: "HDT", 12: "HDF", 13: "PPV"}


# =============================================================================
# 2. 리포트 파서 — 메인 페이지와 같은 포맷을 읽습니다
# =============================================================================
def parse_date_cell(d_val, base_day):
    """엑셀 헤더의 날짜 값을 date로. base_day 기준으로 연도를 추론합니다."""
    if d_val is None:
        return None
    try:
        if pd.isna(d_val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(d_val, pd.Timestamp):
        return d_val.date()
    if isinstance(d_val, datetime):
        return d_val.date()
    if isinstance(d_val, date):
        return d_val
    if isinstance(d_val, (int, float)) and not isinstance(d_val, bool):
        try:
            return (pd.to_datetime('1899-12-30')
                    + pd.to_timedelta(float(d_val), 'D')).date()
        except (ValueError, OverflowError):
            return None
    s = str(d_val).strip()
    if not s:
        return None
    ym = re.search(r'(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})', s)
    if ym:
        try:
            return date(int(ym.group(1)), int(ym.group(2)), int(ym.group(3)))
        except ValueError:
            return None
    s2 = s.replace('.', '-').replace('/', '-').replace(' ', '')
    m = re.search(r'(\d{1,2})-(\d{1,2})', s2)
    if not m:
        return None
    mo, dy = int(m.group(1)), int(m.group(2))
    for cy in (base_day.year, base_day.year + 1, base_day.year - 1):
        try:
            c = date(cy, mo, dy)
        except ValueError:
            continue
        if -180 <= (c - base_day).days <= 400:
            return c
    return None


def parse_reports(files, base_day):
    """업로드 파일들 → DataFrame(Date, RoomID, Available, Total, Tag)"""
    rows, failed = [], []
    for f in files:
        tag = re.search(r'\d{8}', f.name)
        tag = tag.group() if tag else f.name
        try:
            raw = pd.read_excel(f, header=None)
        except Exception as e:
            st.error(f"{f.name} 읽기 실패: {e}")
            continue
        if len(raw) < 4:
            st.error(f"{f.name}: 행이 너무 적습니다 (헤더 구조 확인)")
            continue
        header = raw.iloc[2, 2:].values
        parsed = []
        for v in header:
            d = parse_date_cell(v, base_day)
            parsed.append(d)
            if d is None and pd.notna(v) and str(v).strip() and str(v) not in failed:
                failed.append(str(v))
        for r_idx, rid in ROW_MAP.items():
            if r_idx >= len(raw):
                continue
            tot = pd.to_numeric(raw.iloc[r_idx, 1], errors='coerce')
            for d, av in zip(parsed, raw.iloc[r_idx, 2:].values):
                if d is None:
                    continue
                rows.append({"Date": d, "RoomID": rid,
                             "Available": pd.to_numeric(av, errors='coerce'),
                             "Total": tot, "Tag": tag})
    return pd.DataFrame(rows), failed


def load_latest_snapshot():
    if db is None:
        return pd.DataFrame(), None
    try:
        docs = (db.collection(COL_SNAPSHOTS)
                  .order_by("save_time", direction=firestore.Query.DESCENDING)
                  .limit(1).stream())
        for doc in docs:
            d = doc.to_dict()
            df = pd.DataFrame(d.get('data', []))
            if not df.empty and 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.date
            prev = pd.DataFrame(d.get('prev_data', []) or [])
            if not prev.empty and 'Date' in prev.columns:
                prev['Date'] = pd.to_datetime(prev['Date']).dt.date
            return (df, prev), d.get('work_date', '알수없음')
    except Exception as e:
        st.error(f"최신 스냅샷 불러오기 실패: {e}")
    return (pd.DataFrame(), pd.DataFrame()), None


def load_snapshot_by_date(work_date_str):
    if db is None:
        return None
    try:
        docs = (db.collection(COL_SNAPSHOTS)
                  .where("work_date", "==", work_date_str).limit(1).stream())
        for doc in docs:
            d = doc.to_dict()
            df = pd.DataFrame(d.get('data', []))
            if not df.empty and 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.date
            prev = pd.DataFrame(d.get('prev_data', []) or [])
            if not prev.empty and 'Date' in prev.columns:
                prev['Date'] = pd.to_datetime(prev['Date']).dt.date
            return df, prev
    except Exception as e:
        st.error(f"불러오기 실패: {e}")
    return None


def load_channels():
    if 'channel_list' in st.session_state and 'promotions' in st.session_state:
        return
    st.session_state.setdefault('channel_list', [])
    st.session_state.setdefault('promotions', {})
    if db is None:
        return
    try:
        doc = db.collection(COL_SETTINGS).document("channels").get()
        if doc.exists:
            d = doc.to_dict()
            st.session_state.channel_list = d.get("channel_list", [])
            st.session_state.promotions = d.get("promotions", {})
    except Exception:
        pass


# =============================================================================
# 3. 세션 상태 — 메인 페이지와 같은 키를 씁니다
# =============================================================================
st.session_state.setdefault('today_df', pd.DataFrame())
st.session_state.setdefault('prev_df', pd.DataFrame())
st.session_state.setdefault('new_engine_label', "")
load_channels()

# =============================================================================
# 4. 사이드바
# =============================================================================
with st.sidebar:
    st.markdown("### 🟩 신 요금로직")
    st.caption("메인 페이지(기존 로직)와 완전히 분리된 계산입니다. "
               "app.py 는 손대지 않았습니다.")
    st.divider()

    # ── 기준일 ────────────────────────────────────────────────────
    #  D-일수(페이스·재심사)는 이 날짜를 '오늘'로 봅니다.
    #  과거 재고로 로직을 검증할 때 그 시점으로 되돌려 놓으면 그대로 재현됩니다.
    with st.container(border=True):
        st.markdown("#### 📌 기준일 (= 오늘)")
        use_custom = st.checkbox("직접 지정", value=False, key="new_use_custom_today",
                                 help="과거 재고로 로직을 검증할 때 그 시점으로 되돌립니다. "
                                      "앵커·연휴·재고·floor는 기준일과 무관하고, "
                                      "페이스와 재심사 판정만 달라집니다.")
        if use_custom:
            base_day = st.date_input("기준일", value=date.today(), key="new_base_day")
        else:
            base_day = date.today()
        st.caption(f"D-일수 기준: **{base_day.strftime('%Y-%m-%d')}** "
                   f"({eng.WD_KR[base_day.weekday()]})")

    st.divider()
    st.markdown("#### 📂 재고 데이터")
    cur = st.session_state.today_df
    if cur is not None and not cur.empty:
        try:
            lo, hi = min(cur['Date']), max(cur['Date'])
            st.success(f"{len(cur):,}행 · {lo.strftime('%m/%d')} ~ {hi.strftime('%m/%d')}"
                       + (f"\n\n{st.session_state.new_engine_label}"
                          if st.session_state.new_engine_label else ""))
        except Exception:
            st.success(f"{len(cur):,}행 적재됨")
    else:
        st.info("데이터가 없습니다. 아래에서 올리거나 불러오세요.")

    files = st.file_uploader("리포트 업로드", accept_multiple_files=True,
                             key="new_uploader")
    if files and st.button("📥 업로드 반영", use_container_width=True,
                           key="new_apply_upload"):
        new_df, failed = parse_reports(files, base_day)
        if new_df.empty:
            st.error("읽어낸 행이 없습니다. 파일 형식을 확인하세요.")
        else:
            old = st.session_state.today_df
            if old is not None and not old.empty:
                st.session_state.prev_df = old.copy()
                merged = (pd.concat([new_df, old])
                            .drop_duplicates(subset=['Date', 'RoomID'], keep='first'))
                st.session_state.today_df = merged.sort_values(['Date', 'RoomID'])
                st.session_state.new_engine_label = "직전 화면 데이터를 이전 기록으로 사용"
            else:
                st.session_state.today_df = new_df.sort_values(['Date', 'RoomID'])
                st.session_state.new_engine_label = "신규 업로드 (이전 기록 없음)"
            if failed:
                st.warning(f"날짜로 인식하지 못한 헤더 {len(failed)}건: "
                           + ", ".join(failed[:8]))
            st.rerun()

    if st.button("🗄️ DB 최신 스냅샷 불러오기", use_container_width=True,
                 key="new_load_latest"):
        (df, prev), wd = load_latest_snapshot()
        if df is None or df.empty:
            st.warning("저장된 스냅샷이 없습니다.")
        else:
            st.session_state.today_df = df
            st.session_state.prev_df = prev if prev is not None else pd.DataFrame()
            st.session_state.new_engine_label = f"DB 스냅샷: {wd} 기준"
            st.rerun()

    with st.expander("📅 특정 저장일 불러오기", expanded=False):
        wd = st.date_input("저장일", value=date.today(), key="new_hist_day")
        if st.button("불러오기", use_container_width=True, key="new_load_hist"):
            got = load_snapshot_by_date(wd.strftime('%Y-%m-%d'))
            if not got or got[0] is None or got[0].empty:
                st.warning("해당 저장일 데이터가 없습니다.")
            else:
                st.session_state.today_df = got[0]
                st.session_state.prev_df = got[1] if got[1] is not None else pd.DataFrame()
                st.session_state.new_engine_label = f"과거 기록: {wd} 기준"
                st.rerun()

    prev = st.session_state.prev_df
    if prev is not None and not prev.empty:
        st.caption(f"✅ 이전 기록 {len(prev):,}행 — 페이스 단계가 작동합니다")
    else:
        st.caption("⚠️ 이전 기록 없음 — 페이스 단계는 0으로 계산됩니다 "
                   "(앵커·연휴·재고·floor는 정상)")

    if st.button("🧹 이 페이지 데이터 비우기", use_container_width=True,
                 key="new_clear"):
        st.session_state.today_df = pd.DataFrame()
        st.session_state.prev_df = pd.DataFrame()
        st.session_state.new_engine_label = ""
        st.rerun()

    st.divider()
    st.caption(f"엔진 판: **{eng.NEW_EDITION}** · 사다리 16칸 · 앵커 84셀\n\n"
               f"연도와 무관합니다 (앵커 = 월 x 요일, 공휴일 자동 산출).")

# =============================================================================
# 5. 본문
# =============================================================================
eng.render_page(
    curr_df=st.session_state.today_df,
    prev_df=st.session_state.prev_df,
    db=db,
    promotions=st.session_state.get('promotions', {}),
    channel_list=st.session_state.get('channel_list', []),
    today=base_day,
)
