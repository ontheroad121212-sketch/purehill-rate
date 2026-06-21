import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import math
import re
import io
import hashlib
import json

# --- 1. 파이어베이스 초기화 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# --- 2. 전역 설정 데이터 ---
BAR_GRADIENT_COLORS = {
    "BAR0P": "#7B0000",  # BAR0보다 진한 최고가
    "BAR0": "#B71C1C",
    "BAR1": "#D32F2F", "BAR2": "#EF5350", "BAR3": "#FF8A65", "BAR4": "#FFB199",
    "BAR5": "#81C784", "BAR6": "#A5D6A7", "BAR7": "#C8E6C9", "BAR8": "#E8F5E9",
}
BAR_LIGHT_COLORS = {
    "BAR0P": "#EF9A9A",
    "BAR0": "#FFCDD2",
    "BAR1": "#FFEBEE", "BAR2": "#FFEBEE", "BAR3": "#FFF3E0", "BAR4": "#FFF3E0",
    "BAR5": "#E8F5E9", "BAR6": "#E8F5E9", "BAR7": "#F1F8E9", "BAR8": "#F1F8E9",
}
# BAR 고가→저가 순서 (인덱스 낮을수록 비쌈)
BAR_ORDER = ["BAR0P", "BAR0", "BAR1", "BAR2", "BAR3", "BAR4", "BAR5", "BAR6", "BAR7", "BAR8"]
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
DYNAMIC_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF"]
FIXED_ROOMS = ["GDB", "GDF", "FFD", "FPT", "PPV"]
ALL_ROOMS = DYNAMIC_ROOMS + FIXED_ROOMS

PRICE_TABLE = {
    "FDB": {"BAR0P": 894000, "BAR0": 805000, "BAR1": 721000, "BAR2": 642000, "BAR3": 567000, "BAR4": 502000, "BAR5": 445000, "BAR6": 396000, "BAR7": 353000, "BAR8": 315000},
    "FDE": {"BAR0P": 931000, "BAR0": 842000, "BAR1": 758000, "BAR2": 679000, "BAR3": 604000, "BAR4": 539000, "BAR5": 482000, "BAR6": 433000, "BAR7": 390000, "BAR8": 352000},
    "HDP": {"BAR0P": 859000, "BAR0": 770000, "BAR1": 686000, "BAR2": 607000, "BAR3": 532000, "BAR4": 467000, "BAR5": 410000, "BAR6": 361000, "BAR7": 318000, "BAR8": 280000},
    "HDT": {"BAR0P": 829000, "BAR0": 740000, "BAR1": 656000, "BAR2": 577000, "BAR3": 502000, "BAR4": 437000, "BAR5": 380000, "BAR6": 331000, "BAR7": 288000, "BAR8": 250000},
    "HDF": {"BAR0P": 999000, "BAR0": 910000, "BAR1": 826000, "BAR2": 747000, "BAR3": 672000, "BAR4": 607000, "BAR5": 550000, "BAR6": 501000, "BAR7": 458000, "BAR8": 420000},
}
# FPT 펫룸 독립 BAR 요금표 (호텔 전체 OCC 기준, 500,000~900,000)
FPT_TABLE = {
    "BAR0P": 950000, "BAR0": 900000, "BAR1": 850000, "BAR2": 800000, "BAR3": 750000,
    "BAR4": 700000, "BAR5": 650000, "BAR6": 600000, "BAR7": 550000, "BAR8": 500000,
}
# PPV 풀빌라 럭셔리 독립 BAR 요금표 (FDB 연동, 1,290,000~2,790,000)
PPV_TABLE = {
    "BAR0P": 2790000, "BAR0": 2490000, "BAR1": 2340000, "BAR2": 2190000, "BAR3": 2040000,
    "BAR4": 1890000, "BAR5": 1740000, "BAR6": 1590000, "BAR7": 1440000, "BAR8": 1290000,
}
# GDB 그린밸리 더블 독립 BAR 요금표 (자체 OCC 기준, 298,000~718,000)
GDB_TABLE = {
    "BAR0P": 718000, "BAR0": 658000, "BAR1": 598000, "BAR2": 538000, "BAR3": 478000,
    "BAR4": 418000, "BAR5": 358000, "BAR6": 298000, "BAR7": 298000, "BAR8": 298000,
}
# GDF 그린밸리 패밀리 독립 BAR 요금표 (자체 OCC 기준, 390,000~969,000)
GDF_TABLE = {
    "BAR0P": 969000, "BAR0": 880000, "BAR1": 796000, "BAR2": 717000, "BAR3": 642000,
    "BAR4": 577000, "BAR5": 520000, "BAR6": 471000, "BAR7": 428000, "BAR8": 390000,
}
# FFD 포레스트 패밀리 더블 BAR 요금표 (FDE+20k 플로어 스냅업, 372,000~951,000)
FFD_TABLE = {
    "BAR0P": 951000, "BAR0": 862000, "BAR1": 778000, "BAR2": 699000, "BAR3": 624000,
    "BAR4": 559000, "BAR5": 502000, "BAR6": 453000, "BAR7": 410000, "BAR8": 372000,
}
# 하위 호환용 (구 스냅샷 읽기 등에 사용될 수 있음, 신규 산출에는 미사용)
FIXED_PRICE_TABLE = {
    "GDB": {"UND1": 298000, "UND2": 298000, "MID1": 298000, "MID2": 298000, "UPP1": 298000, "UPP2": 298000},
    "GDF": {"UND1": 375000, "UND2": 410000, "MID1": 410000, "MID2": 488000, "UPP1": 488000, "UPP2": 578000},
    "FFD": {"UND1": 353000, "UND2": 393000, "MID1": 433000, "MID2": 482000, "UPP1": 539000, "UPP2": 604000},
    "FPT": {"UND1": 500000, "UND2": 550000, "MID1": 600000, "MID2": 650000, "UPP1": 700000, "UPP2": 750000},
    "PPV": {"UND1": 1104000, "UND2": 1154000, "MID1": 1154000, "MID2": 1304000, "UPP1": 1304000, "UPP2": 1554000},
}

TODAY = date.today()

# Firebase 컬렉션 이름 (스네이크케이스)
COL_SNAPSHOTS = "daily_snapshots"
COL_APPLIED = "applied_rates"
COL_SETTINGS = "settings"
COL_AUDIT = "audit_log"
COL_RESTORE = "restore_points"


# =============================================================================
# 3. 로직 함수
# =============================================================================
def get_season_details(date_obj):
    m, d = date_obj.month, date_obj.day
    md = f"{m:02d}.{d:02d}"
    actual_is_weekend = date_obj.weekday() in [4, 5]
    if ("02.13" <= md <= "02.18") or ("09.23" <= md <= "09.28"):
        season, is_weekend = "UPP", True
    elif ("12.21" <= md <= "12.31") or ("10.01" <= md <= "10.08"):
        season, is_weekend = "UPP", False
    elif ("05.03" <= md <= "05.05") or ("05.24" <= md <= "05.26") or ("06.05" <= md <= "06.07"):
        season, is_weekend = "MID", True
    elif "07.17" <= md <= "08.29":
        season, is_weekend = "UPP", actual_is_weekend
    elif ("01.04" <= md <= "03.31") or ("11.01" <= md <= "12.20"):
        season, is_weekend = "UND", actual_is_weekend
    else:
        season, is_weekend = "MID", actual_is_weekend
    type_code = f"{season}{'2' if is_weekend else '1'}"
    return type_code, season, is_weekend


def get_start_bar(date_obj):
    """날짜 기반 시작 BAR 반환 (해당 날 OCC 최저일 때의 BAR).
    BAR_ORDER에서 인덱스 높을수록 저렴. 시작 BAR = OCC 0% 때의 BAR."""
    m, d = date_obj.month, date_obj.day
    md = f"{m:02d}.{d:02d}"
    actual_is_weekend = date_obj.weekday() in [4, 5]

    # ── 최성수기: BAR2 시작 (주중/주말 동일) ──
    if (("07.25" <= md <= "08.08") or
        ("08.14" <= md <= "08.16") or
        ("09.24" <= md <= "09.28") or
        ("10.01" <= md <= "10.10") or
        ("12.24" <= md <= "12.26") or
        md == "12.31"):
        return "BAR2"

    # ── 준성수기: BAR3 시작 ──
    if "08.09" <= md <= "08.13":
        return "BAR3"

    # ── 여름 성수기 (7/17~8/29) 나머지: 주중 BAR5, 주말 BAR4 ──
    if "07.17" <= md <= "08.29":
        return "BAR4" if actual_is_weekend else "BAR5"

    # ── 12월 겨울 특수 (21~30, 24~26은 위에서 처리) ──
    if "12.21" <= md <= "12.30":
        return "BAR4"

    # ── 9~10월: 주중 BAR6, 주말 BAR5 ──
    if "09.01" <= md <= "10.31":
        return "BAR5" if actual_is_weekend else "BAR6"

    # ── 11월~12월20일: 주중 BAR7, 주말 BAR6 ──
    if "11.01" <= md <= "12.20":
        return "BAR6" if actual_is_weekend else "BAR7"

    # ── 나머지 날짜 (1~6월, 7월 1~16일): 기존 시즌 로직으로 매핑 ──
    _, season, is_weekend_ovr = get_season_details(date_obj)
    # is_weekend_ovr 포함 (설날·추석 등 휴일 평일→주말 오버라이드 반영)
    return {
        ("UPP", True):  "BAR4", ("UPP", False):  "BAR5",
        ("MID", True):  "BAR6", ("MID", False):  "BAR7",
        ("UND", True):  "BAR7", ("UND", False):  "BAR8",
    }.get((season, is_weekend_ovr), "BAR8")


def determine_bar(date_obj, occ):
    """날짜 + OCC → BAR 코드.
    시작 BAR에서 OCC 구간마다 한 단계씩 고가 BAR로 이동 (최대 3단계)."""
    start_bar = get_start_bar(date_obj)
    start_idx = BAR_ORDER.index(start_bar)
    if occ >= 81:   offset = 3
    elif occ >= 51: offset = 2
    elif occ >= 31: offset = 1
    else:           offset = 0
    return BAR_ORDER[max(0, start_idx - offset)]


# =============================================================================
# 3-NEW. 희소성 프리미엄 + 전체 날짜 가격 통합 산출 (역전방지 + 연동 포함)
# =============================================================================
_price_cache = {}  # 리런 단위 캐시 (모듈 레벨, 리런마다 초기화됨)


def compute_scarcity_premium(avail, date_obj):
    """희소성 프리미엄: 잔여2실 +20,000 / 잔여1실 +50,000 / 체크인7일이내 잔여1실 +70,000"""
    try:
        avail_int = int(float(avail)) if pd.notna(avail) else 999
    except Exception:
        avail_int = 999
    days_to_checkin = (date_obj - TODAY).days
    if avail_int <= 1:
        return 70000 if days_to_checkin <= 7 else 50000
    elif avail_int <= 2:
        return 20000
    return 0


def snap_to_bar_ceil(table, floor_price):
    """floor_price 이상인 BAR 중 가장 저렴한(번호 높은) BAR 반환.
    예) FFD floor=609,000 → BAR5(502,000)는 미달, BAR4(559,000)도 미달,
        BAR3(624,000) ≥ 609,000 → 'BAR3'
    모든 BAR가 floor 미만이면 'BAR0'(최고가) 반환."""
    best_bar = "BAR0"
    best_num = -1
    for bar, price in table.items():
        try:
            num = int(bar.replace("BAR", ""))
        except Exception:
            continue
        if price >= floor_price and num > best_num:
            best_num = num
            best_bar = bar
    return best_bar


def compute_all_prices_for_date(date_obj, curr_df, manual_bars=None):
    """주어진 날짜의 전체 객실 가격 통합 산출.
    Step1: 전체 호텔OCC → hotel_bar
    Step2~3: 메인5객실 BAR+가격
    Step4: 역전방지 (HDT<HDP<FDB<FDE<HDF)
    Step5~6: 특수객실 연동+희소성 프리미엄
    Returns: {rid: {'occ', 'bar', 'price', 'is_manual'}}
    """
    if manual_bars is None:
        manual_bars = {}

    date_str = date_obj.strftime('%Y-%m-%d')
    cache_key = (date_str, id(curr_df), tuple(sorted(manual_bars.items())))
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    type_code, season, is_weekend = get_season_details(date_obj)
    date_rows = curr_df[curr_df['Date'] == date_obj]

    # Step 1. 전체 호텔 OCC
    total_avail_sum, total_rooms_sum = 0.0, 0.0
    for _, row in date_rows.iterrows():
        try:
            total_avail_sum += float(row['Available']) if pd.notna(row['Available']) else 0.0
            total_rooms_sum += float(row['Total']) if pd.notna(row['Total']) else 0.0
        except Exception:
            pass
    hotel_occ = ((total_rooms_sum - total_avail_sum) / total_rooms_sum * 100) if total_rooms_sum > 0 else 0
    hotel_bar = determine_bar(date_obj, hotel_occ)

    result = {}

    # Step 2~3. 메인 5개 객실 BAR + 기본 가격
    main_rooms_order = ["HDT", "HDP", "FDB", "FDE", "HDF"]
    base_prices, bars, occs, is_manuals = {}, {}, {}, {}

    for rid in main_rooms_order:
        m = date_rows[date_rows['RoomID'] == rid]
        if m.empty:
            continue
        try:
            av = float(m.iloc[0]['Available']) if pd.notna(m.iloc[0]['Available']) else 0.0
        except Exception:
            av = 0.0
        tot = m.iloc[0]['Total']
        occ = ((tot - av) / tot * 100) if tot > 0 else 0
        occs[rid] = occ

        manual_bar = manual_bars.get(f"{date_str}_{rid}")
        if manual_bar:
            bar, is_manual = manual_bar, True
        else:
            bar, is_manual = determine_bar(date_obj, occ), False

        bars[rid] = bar
        is_manuals[rid] = is_manual
        base_prices[rid] = PRICE_TABLE.get(rid, {}).get(bar, 0)

    # Step 4. 가격 역전 방지
    fp = dict(base_prices)
    if "HDT" in fp and "HDP" in fp:
        fp["HDP"] = max(fp["HDP"], fp["HDT"] + 30000)
    if "HDP" in fp and "FDB" in fp:
        fp["FDB"] = max(fp["FDB"], fp["HDP"] + 35000)
    if "FDB" in fp and "FDE" in fp:
        fp["FDE"] = max(fp["FDE"], fp["FDB"] + 37000)
    if "FDE" in fp and "HDF" in fp:
        fp["HDF"] = max(fp["HDF"], fp["FDE"] + 70000)

    for rid in main_rooms_order:
        if rid not in fp:
            continue
        occ_bar = bars.get(rid, "BAR8")
        adj_price = fp[rid]
        # 역전방지로 가격 상향된 경우 유효 BAR 역산
        if adj_price != base_prices.get(rid, adj_price):
            eff_bar = price_to_effective_bar(rid, adj_price) or occ_bar
        else:
            eff_bar = occ_bar
        result[rid] = {
            'occ': occs.get(rid, 0),
            'bar': eff_bar,
            'original_bar': occ_bar,
            'price': adj_price,
            'is_manual': is_manuals.get(rid, False),
        }

    # Step 5. GDB/GDF: 자체 OCC 기반 독립 BAR (그린밸리 펜션형, 메인 계층 무관)
    fde_p = fp.get("FDE", 0)

    for rid, table, cap in [("GDB", GDB_TABLE, 678000), ("GDF", GDF_TABLE, 878000)]:
        m = date_rows[date_rows['RoomID'] == rid]
        if m.empty:
            continue
        try:
            av = float(m.iloc[0]['Available']) if pd.notna(m.iloc[0]['Available']) else 0.0
        except Exception:
            av = 0.0
        tot = m.iloc[0]['Total']
        occ = ((tot - av) / tot * 100) if tot > 0 else 0
        own_bar = determine_bar(date_obj, occ)
        base_p = table.get(own_bar, list(table.values())[-1])
        scarcity = compute_scarcity_premium(av, date_obj)
        final_p = min(base_p + scarcity, cap)
        eff_bar = price_to_effective_bar(rid, final_p) or own_bar
        result[rid] = {'occ': occ, 'bar': eff_bar, 'original_bar': own_bar, 'price': final_p, 'is_manual': False}

    # Step 6. FFD: FDE+20k 플로어 기준 FFD_TABLE 스냅업 (FDE 연동)
    m_ffd = date_rows[date_rows['RoomID'] == "FFD"]
    if not m_ffd.empty:
        try:
            av_ffd = float(m_ffd.iloc[0]['Available']) if pd.notna(m_ffd.iloc[0]['Available']) else 0.0
        except Exception:
            av_ffd = 0.0
        tot_ffd = m_ffd.iloc[0]['Total']
        occ_ffd = ((tot_ffd - av_ffd) / tot_ffd * 100) if tot_ffd > 0 else 0
        scarcity_ffd = compute_scarcity_premium(av_ffd, date_obj)
        ffd_floor = fde_p + 20000 + scarcity_ffd
        ffd_bar = snap_to_bar_ceil(FFD_TABLE, ffd_floor)
        ffd_price = FFD_TABLE.get(ffd_bar, FFD_TABLE["BAR0"])
        result["FFD"] = {'occ': occ_ffd, 'bar': ffd_bar, 'original_bar': ffd_bar, 'price': ffd_price, 'is_manual': False}

    # Step 7. FPT/PPV: FDB BAR 연동 (FDB 오르면 같이 오름, 역전 없음)
    fdb_bar = result.get("FDB", {}).get("bar", hotel_bar)
    for rid, table, cap in [("FPT", FPT_TABLE, 900000), ("PPV", PPV_TABLE, 2490000)]:
        m = date_rows[date_rows['RoomID'] == rid]
        if m.empty:
            continue
        try:
            av = float(m.iloc[0]['Available']) if pd.notna(m.iloc[0]['Available']) else 0.0
        except Exception:
            av = 0.0
        tot = m.iloc[0]['Total']
        occ = ((tot - av) / tot * 100) if tot > 0 else 0
        base_p = table.get(fdb_bar, list(table.values())[-1])
        scarcity = compute_scarcity_premium(av, date_obj)
        final_p = min(base_p + scarcity, cap)
        result[rid] = {'occ': occ, 'bar': fdb_bar, 'original_bar': fdb_bar, 'price': final_p, 'is_manual': False}

    _price_cache[cache_key] = result
    return result



def price_to_effective_bar(room_id, price):
    """조정된 가격에서 가장 가까운 실효 BAR 코드를 역산.
    price 이하인 BAR 중 가장 높은 가격의 BAR 반환 (BAR0 제외).
    예) HDF 749,000 → BAR2(747,000)"""
    if room_id in DYNAMIC_ROOMS:
        table = PRICE_TABLE.get(room_id, {})
    elif room_id == "FPT":
        table = FPT_TABLE
    elif room_id == "PPV":
        table = PPV_TABLE
    elif room_id == "GDB":
        table = GDB_TABLE
    elif room_id == "GDF":
        table = GDF_TABLE
    elif room_id == "FFD":
        table = FFD_TABLE
    else:
        return None
    best_bar, best_price = None, None
    for i in range(1, 9):
        bar = f"BAR{i}"
        p = table.get(bar)
        if p is None:
            continue
        if p <= price:
            if best_price is None or p > best_price:
                best_price, best_bar = p, bar
    return best_bar


def get_final_values(room_id, date_obj, avail, total, manual_bar=None):
    # --- 통합 산출 경로 (session_state에 today_df 있을 때) ---
    try:
        curr_df = st.session_state.get('today_df', pd.DataFrame())
        if not curr_df.empty:
            manual_bars = dict(st.session_state.get('manual_bars', {}))
            if manual_bar:
                manual_bars[f"{date_obj.strftime('%Y-%m-%d')}_{room_id}"] = manual_bar
            all_prices = compute_all_prices_for_date(date_obj, curr_df, manual_bars)
            if room_id in all_prices:
                info = all_prices[room_id]
                return info['occ'], info['bar'], info['price'], info.get('is_manual', False)
    except Exception:
        pass

    # --- Fallback ---
    type_code, season, is_weekend = get_season_details(date_obj)
    try:
        current_avail = float(avail) if pd.notna(avail) else 0.0
    except Exception:
        current_avail = 0.0
    occ = ((total - current_avail) / total * 100) if total > 0 else 0

    if manual_bar:
        bar = manual_bar
        if room_id in DYNAMIC_ROOMS:
            price = PRICE_TABLE.get(room_id, {}).get(bar, 0)
        elif room_id == "FPT":
            price = FPT_TABLE.get(bar, 0)
        elif room_id == "PPV":
            price = PPV_TABLE.get(bar, 0)
        elif room_id == "GDB":
            price = GDB_TABLE.get(bar, 0)
        elif room_id == "GDF":
            price = GDF_TABLE.get(bar, 0)
        elif room_id == "FFD":
            price = FFD_TABLE.get(bar, 0)
        else:
            price = 0
        return occ, bar, price, True

    if room_id in DYNAMIC_ROOMS:
        bar = determine_bar(date_obj, occ)
        price = PRICE_TABLE.get(room_id, {}).get(bar, 0)
    elif room_id == "FPT":
        # fallback: curr_df 없을 때 FDB BAR 참조 불가 → hotel OCC 근사치 사용
        bar = determine_bar(date_obj, occ)
        price = FPT_TABLE.get(bar, 500000)
    elif room_id == "PPV":
        # fallback: curr_df 없을 때 FDB BAR 참조 불가 → hotel OCC 근사치 사용
        bar = determine_bar(date_obj, occ)
        price = PPV_TABLE.get(bar, 1290000)
    elif room_id == "GDB":
        bar = determine_bar(date_obj, occ)
        price = GDB_TABLE.get(bar, 298000)
    elif room_id == "GDF":
        bar = determine_bar(date_obj, occ)
        price = GDF_TABLE.get(bar, 392000)
    elif room_id == "FFD":
        bar = determine_bar(date_obj, occ)
        price = FFD_TABLE.get(bar, 372000)
    else:
        bar = type_code
        price = 0
    return occ, bar, price, False


def date_filter_toggle(key_prefix, total_dates, default_show_past=False):
    past_count = sum(1 for d in total_dates if d < TODAY)
    future_count = len(total_dates) - past_count

    if past_count == 0:
        return total_dates

    show_past = st.checkbox(
        f"📜 과거 {past_count}일 포함 (현재 미래 {future_count}일만 표시)",
        value=default_show_past,
        key=f"show_past_{key_prefix}"
    )
    return total_dates if show_past else [d for d in total_dates if d >= TODAY]


def filter_df_by_dates(df, visible_dates):
    if df.empty:
        return df
    return df[df['Date'].isin(visible_dates)].copy()


# =============================================================================
# 3-A. 재검토 캐싱 (B 개선: build_review_map)
# =============================================================================
def _df_signature(df, applied_rates):
    """DataFrame + applied_rates의 시그니처 - 캐시 키용"""
    if df.empty:
        d_sig = "empty"
    else:
        # 핵심 컬럼만 사용해서 해시
        try:
            d_sig = hashlib.md5(
                pd.util.hash_pandas_object(df[['Date', 'RoomID', 'Available', 'Total']]).values.tobytes()
            ).hexdigest()
        except Exception:
            d_sig = str(len(df)) + "_" + str(df['Date'].min()) + "_" + str(df['Date'].max())
    try:
        a_sig = hashlib.md5(json.dumps(applied_rates, sort_keys=True, default=str).encode()).hexdigest()
    except Exception:
        a_sig = str(len(applied_rates))
    return f"{d_sig}_{a_sig}"


def build_review_map(current_df, applied_rates):
    """모든 (rid, date) 조합에 대해 재검토 필요 여부를 한 번에 계산.
    리턴: dict {(rid, date_obj): {'needs': bool, 'applied': str, 'rec': str, 'rec_at_apply': str}}
    세션 캐시 사용 (시그니처 기반)"""
    if current_df.empty:
        return {}

    sig = _df_signature(current_df, applied_rates)
    cache_key = f"_review_map_cache_{sig}"

    if cache_key in st.session_state:
        return st.session_state[cache_key]

    result = {}
    for rid in DYNAMIC_ROOMS:
        room_df = current_df[current_df['RoomID'] == rid]
        for _, row in room_df.iterrows():
            d = row['Date']
            date_str = d.strftime('%Y-%m-%d')
            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)

            if not applied_bar:
                continue

            _, rec_bar, _, _ = get_final_values(rid, d, row['Available'], row['Total'])
            rec_at_apply = applied_rates.get(date_str, {}).get('rec_bar_at_apply', {}).get(rid)
            needs = bool(rec_at_apply and rec_at_apply != rec_bar)

            result[(rid, d)] = {
                'needs': needs,
                'applied': applied_bar,
                'rec': rec_bar,
                'rec_at_apply': rec_at_apply,
            }

    # 이전 캐시 정리 (메모리 절약)
    for k in list(st.session_state.keys()):
        if k.startswith("_review_map_cache_") and k != cache_key:
            del st.session_state[k]
    st.session_state[cache_key] = result
    return result


def is_review_needed(rid, date_obj, current_df, applied_rates):
    """캐시된 리뷰맵 사용 - 기존 호출부 호환용"""
    review_map = build_review_map(current_df, applied_rates)
    info = review_map.get((rid, date_obj))
    if not info:
        # 캐시에 없으면 적용 BAR이 없다는 뜻 - 기존 동작 유지
        date_str = date_obj.strftime('%Y-%m-%d')
        applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
        if not applied_bar:
            return False, None, None
        # 안전장치
        curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == date_obj)]
        if curr_match.empty:
            return False, applied_bar, None
        _, rec_bar, _, _ = get_final_values(rid, date_obj, curr_match.iloc[0]['Available'], curr_match.iloc[0]['Total'])
        return False, applied_bar, rec_bar
    return info['needs'], info['applied'], info['rec']


# =============================================================================
# 3-B. 가격 무결성 검증 (F 개선)
# =============================================================================
def validate_price_tables():
    """PRICE_TABLE의 BAR1~BAR8 가격이 단조 감소(BAR1>BAR2>...>BAR8)인지 검증.
    리턴: list of warnings"""
    warnings = []
    for room, bars in PRICE_TABLE.items():
        prev_price = None
        prev_bar = None
        for i in range(1, 9):
            bar = f"BAR{i}"
            p = bars.get(bar)
            if p is None:
                warnings.append(f"⚠️ {room}: {bar} 가격 누락")
                continue
            if prev_price is not None and p >= prev_price:
                warnings.append(f"🚨 {room}: {prev_bar}({prev_price:,}) ≤ {bar}({p:,}) — 가격 역전!")
            prev_price = p
            prev_bar = bar
        bar0 = bars.get("BAR0")
        bar1 = bars.get("BAR1")
        if bar0 is not None and bar1 is not None and bar0 <= bar1:
            warnings.append(f"🚨 {room}: BAR0({bar0:,}) ≤ BAR1({bar1:,}) — 수동인상가가 BAR1보다 작거나 같음!")

    # FPT_TABLE / PPV_TABLE: BAR1>BAR2>...>BAR8 단조 감소 확인
    for tname, tbl in [("FPT_TABLE", FPT_TABLE), ("PPV_TABLE", PPV_TABLE)]:
        prev_price, prev_bar = None, None
        for i in range(1, 9):
            bar = f"BAR{i}"
            p = tbl.get(bar)
            if p is None:
                warnings.append(f"⚠️ {tname}: {bar} 가격 누락")
                continue
            if prev_price is not None and p >= prev_price:
                warnings.append(f"🚨 {tname}: {prev_bar}({prev_price:,}) ≤ {bar}({p:,}) — 가격 역전!")
            prev_price, prev_bar = p, bar
    return warnings


# =============================================================================
# 4. 렌더러 (마스터 테이블)
# =============================================================================
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준", applied_rates=None):
    if current_df.empty:
        return "<div style='padding:20px;'>데이터를 업로드하세요.</div>"
    dates = sorted(current_df['Date'].unique())

    if mode == "판매가":
        items_to_show = st.session_state.promotions.get(ch_name, {}).get("items", [])
        row_padding = "1px"
        header_padding = "2px"
        line_style = "line-height: 1.0; font-size: 11px;"
        font_size = "11px"
        col_width_style = "min-width: 45px;"
    else:
        items_to_show = ALL_ROOMS
        row_padding = "8px"
        header_padding = "5px"
        line_style = ""
        font_size = "11px"
        col_width_style = ""

    if mode == "판매가" and not items_to_show:
        return f"<div style='padding:10px; color:gray;'>👉 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"

    bg_title_color = "#E3F2FD" if mode == "최종결과" else "#f0f2f6"
    border_title_color = "#1976D2" if mode == "최종결과" else "#000"

    html = f"<div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; padding:10px; background:{bg_title_color}; border-left:10px solid {border_title_color};'>{title}</div>"
    html += "<div style='overflow-x: auto; white-space: nowrap; border: 1px solid #ddd;'>"
    html += f"<table style='width:100%; border-collapse:collapse; font-size:{font_size}; min-width:1000px;'><thead><tr style='background:#f9f9f9;'><th rowspan='2' style='border:1px solid #ddd; width:180px; position:sticky; left:0; background:#f9f9f9; z-index:2; padding:{header_padding};'>객실/프로모션</th>"
    for d in dates:
        html += f"<th style='border:1px solid #ddd; padding:{header_padding}; {col_width_style}'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd == '일' else ("blue" if wd == '토' else "black")
        html += f"<th style='border:1px solid #ddd; padding:{header_padding}; color:{color}; {col_width_style}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for item in items_to_show:
        if mode == "판매가":
            rid = item.get('객실타입', 'Unknown')
            label_text = item.get('상품명', 'No Name')
            label = f"<b>{rid}</b> <span style='color:blue; margin-left:4px;'>: {label_text}</span>"
            try: discount = float(item.get('할인(%)') or 0)
            except: discount = 0.0
            try: add_price = int(item.get('추가금') or 0)
            except: add_price = 0
        else:
            rid = item
            label = rid
            if rid in ["HDF", "PPV"]: label = f"<b>{rid}</b>"

        border_thick = "border-bottom:3.4px solid #000;" if rid in ["HDF", "PPV"] else ""
        html += f"<tr style='{border_thick}'><td style='border:1px solid #ddd; padding:{row_padding}; background:#fff; border-right:4px solid #000; position:sticky; left:0; z-index:1; {line_style}'>{label}</td>"

        for d in dates:
            date_str = d.strftime('%Y-%m-%d')

            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += f"<td style='border:1px solid #ddd; padding:{row_padding}; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']

            override_key = f"{date_str}_{rid}"
            m_bar = st.session_state.get('manual_bars', {}).get(override_key) if mode == "판매가" else None
            occ, bar, base_price, is_manual = get_final_values(rid, d, avail, total, m_bar)

            prev_bar, prev_avail = None, None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    prev_avail = prev_m.iloc[0]['Available']
                    p_m_bar = st.session_state.get('manual_bars', {}).get(override_key) if mode == "판매가" else None
                    try:
                        _prev_manual = dict(st.session_state.get('manual_bars', {}))
                        if p_m_bar:
                            _prev_manual[f"{date_str}_{rid}"] = p_m_bar
                        _prev_all = compute_all_prices_for_date(d, prev_df, _prev_manual)
                        prev_bar = _prev_all.get(rid, {}).get('bar')
                    except Exception:
                        prev_bar = None

            style = f"border:1px solid #ddd; padding:{row_padding}; text-align:center; background-color:white; {line_style}"

            if mode == "기준":
                bg = BAR_GRADIENT_COLORS.get(bar, "#FFFFFF")
                style += f"background-color: {bg};"
                try:
                    _ap = compute_all_prices_for_date(d, current_df, st.session_state.get('manual_bars', {}))
                    _orig = _ap.get(rid, {}).get('original_bar', bar)
                except Exception:
                    _orig = bar
                if _orig and _orig != bar:
                    bar_disp = (f"<span style='color:#bbb;text-decoration:line-through;"
                                f"font-size:9px;'>{_orig}</span>"
                                f"<span style='color:#c62828;'>▲</span><b>{bar}</b>")
                else:
                    bar_disp = f"<b>{bar}</b>"
                content = f"{bar_disp}<br>{base_price:,}<br>{occ:.0f}%"

            elif mode == "최종결과":
                applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid) if applied_rates else None
                is_applied = applied_bar is not None
                # 가격 직접 오버라이드(GDB/GDF/FFD 숫자 문자열) vs BAR 오버라이드 구분
                _is_price_ovr = is_applied and str(applied_bar).strip().isdigit()
                if _is_price_ovr:
                    final_bar = bar          # 색상은 계산 BAR 기준
                    final_price = int(str(applied_bar).strip())
                elif is_applied:
                    final_bar = applied_bar
                    final_price = get_bar_price(rid, final_bar) or base_price
                else:
                    final_bar = bar
                    final_price = base_price
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFFFFF")

                needs_review = False
                if is_applied and applied_rates and rid in DYNAMIC_ROOMS:
                    needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)

                try:
                    _ap2 = compute_all_prices_for_date(d, current_df, st.session_state.get('manual_bars', {}))
                    _orig2 = _ap2.get(rid, {}).get('original_bar', final_bar)
                except Exception:
                    _orig2 = final_bar
                if _is_price_ovr:
                    _bar_disp2 = f"<b>직접가격</b>"
                elif _orig2 and _orig2 != final_bar and not is_applied:
                    _bar_disp2 = (f"<span style='color:#bbb;text-decoration:line-through;"
                                  f"font-size:9px;'>{_orig2}</span>"
                                  f"<span style='color:#c62828;'>▲</span><b>{final_bar}</b>")
                else:
                    _bar_disp2 = f"<b>{final_bar}</b>"
                if is_applied:
                    if needs_review:
                        style += f"background-color: {bg}; border: 3px solid #FF6F00; font-weight: bold; box-shadow: inset 0 0 0 2px #FFD54F;"
                        content = f"⚠️ {_bar_disp2}<br>{final_price:,}<br>{occ:.0f}%"
                    else:
                        style += f"background-color: {bg}; border: 3px solid #2E7D32; font-weight: bold;"
                        content = f"⭐ {_bar_disp2}<br>{final_price:,}<br>{occ:.0f}%"
                else:
                    style += f"background-color: {bg}; opacity: 0.9;"
                    content = f"{_bar_disp2}<br>{final_price:,}<br>{occ:.0f}%"

            elif mode == "변화":
                curr_av_safe = float(avail) if pd.notna(avail) else 0.0
                prev_av_safe = float(prev_avail) if (prev_avail is not None and pd.notna(prev_avail)) else 0.0
                pickup = (prev_av_safe - curr_av_safe) if prev_avail is not None else 0
                bg = BAR_LIGHT_COLORS.get(bar, "#FFFFFF")
                style += f"background-color: {bg};"
                if pickup > 0:
                    style += "color:red; font-weight:bold; border: 1.5px solid red;"
                    content = f"+{pickup:.0f}"
                elif pickup < 0:
                    style += "color:blue; font-weight:bold;"
                    content = f"{pickup:.0f}"
                else:
                    content = "-"

            elif mode == "판도변화":
                curr_b_str = str(bar).strip() if bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                if prev_bar is not None and prev_b_str != curr_b_str:
                    try:
                        prev_num = int(prev_b_str.replace('BAR', ''))
                        curr_num = int(curr_b_str.replace('BAR', ''))
                        is_price_up = curr_num < prev_num  # BAR 숫자 낮을수록 고가
                    except Exception:
                        is_price_up = True
                    arrow = "▲" if is_price_up else "▼"
                    border_color = "#B71C1C" if is_price_up else "#0D47A1"
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid {border_color};"
                    content = (f"{arrow} <b style='font-size:13px;'>{curr_b_str}</b><br>"
                               f"<span style='font-size:9px;opacity:0.7;'>{prev_b_str}</span>")
                else:
                    content = f"<span style='color:#aaa; font-size:10px;'>{curr_b_str}</span>"

            elif mode == "판매가":
                try:
                    b_price = float(base_price) if base_price is not None else 0
                    d_rate = float(discount) if discount is not None else 0
                    a_price = float(add_price) if add_price is not None else 0
                    after_disc = b_price * (1 - (d_rate / 100))
                    final_p = int((math.floor(after_disc / 1000) * 1000) + a_price)
                    content = f"<b>{final_p:,}</b>"
                except (ValueError, TypeError, ZeroDivisionError):
                    content = "<b>-</b>"

                curr_b_str = str(bar).strip() if bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                if prev_bar is not None and prev_b_str != curr_b_str:
                    try:
                        _pn = int(prev_b_str.replace('BAR', ''))
                        _cn = int(curr_b_str.replace('BAR', ''))
                        _is_up = _cn < _pn
                    except Exception:
                        _is_up = True
                    _bc = "#B71C1C" if _is_up else "#0D47A1"
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid {_bc};"
                if is_manual:
                    style += "border: 2px dashed #FF0000;"
                    content = f"⭐ {content}"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html


# =============================================================================
# 4-A. 적용 요금 관리 (applied_rates)
# =============================================================================
@st.cache_data(ttl=60)
def load_applied_rates():
    try:
        docs = db.collection(COL_APPLIED).stream()
        result = {}
        for doc in docs:
            result[doc.id] = doc.to_dict()
        return result
    except Exception:
        return {}


def save_applied_rate(target_date_str, applied_data, memo="", rec_at_apply=None, prev_rooms=None, prev_rec_at_apply=None):
    """적용 저장 + 변경 이력(audit log) 자동 기록"""
    try:
        payload = {
            'applied_date': target_date_str,
            'applied_at': datetime.now().isoformat(),
            'applied_at_display': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'memo': memo,
            'rooms': applied_data,
        }
        if rec_at_apply:
            payload['rec_bar_at_apply'] = rec_at_apply
        db.collection(COL_APPLIED).document(target_date_str).set(payload)

        # 변경 이력 기록 (C 개선)
        log_audit(
            action="apply_save",
            target_date=target_date_str,
            new_rooms=applied_data,
            old_rooms=prev_rooms or {},
            memo=memo,
            new_rec_at_apply=rec_at_apply,
            old_rec_at_apply=prev_rec_at_apply,
        )

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"적용 저장 실패: {e}")
        return False


def delete_applied_rate(target_date_str, prev_rooms=None, prev_memo="", prev_rec_at_apply=None):
    try:
        db.collection(COL_APPLIED).document(target_date_str).delete()
        log_audit(
            action="apply_delete",
            target_date=target_date_str,
            new_rooms={},
            old_rooms=prev_rooms or {},
            memo=prev_memo or "",
            old_rec_at_apply=prev_rec_at_apply,
        )
        st.cache_data.clear()
        return True
    except:
        return False


def get_applied_bar(target_date_str, room_id, applied_rates):
    return applied_rates.get(target_date_str, {}).get('rooms', {}).get(room_id)


def get_bar_price(room_id, bar):
    """BAR 코드로 가격 조회."""
    if room_id in DYNAMIC_ROOMS:
        return PRICE_TABLE.get(room_id, {}).get(bar, 0)
    if room_id == "FPT":
        return FPT_TABLE.get(bar, 0)
    if room_id == "PPV":
        return PPV_TABLE.get(bar, 0)
    if room_id == "GDB":
        return GDB_TABLE.get(bar, 0)
    if room_id == "GDF":
        return GDF_TABLE.get(bar, 0)
    if room_id == "FFD":
        return FFD_TABLE.get(bar, 0)
    return 0

# =============================================================================
# 4-A-1-B. 예외 자동 갱신 (신규)
# =============================================================================
def auto_update_stale_exceptions(current_df):
    """새 파일 저장 시 기존 예외(applied_rates) 자동 갱신.

    규칙:
    - 권장 BAR 가격 > 예외 BAR 가격  →  권장 BAR로 자동 교체 (판도변화 인상 수용)
    - 예외 BAR 가격 >= 권장 BAR 가격  →  예외 유지 (더 비싼 예외 고수)

    반환: (갱신된 날짜 수, 상세 로그 리스트)
    """
    if current_df.empty:
        return 0, []

    st.cache_data.clear()
    applied = load_applied_rates()
    if not applied:
        return 0, []

    current_dates = set(current_df['Date'].unique())
    updated_count = 0
    log_items = []

    for date_str, rate_info in applied.items():
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            continue

        if d not in current_dates:
            continue

        existing_rooms = rate_info.get('rooms', {})
        if not existing_rooms:
            continue

        new_rooms = {}
        changed = False
        date_log = []

        for rid, exc_bar in existing_rooms.items():
            if rid not in DYNAMIC_ROOMS:
                new_rooms[rid] = exc_bar
                continue

            row = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if row.empty:
                new_rooms[rid] = exc_bar
                continue

            _, rec_bar, rec_price, _ = get_final_values(
                rid, d, row.iloc[0]['Available'], row.iloc[0]['Total']
            )
            exc_price = get_bar_price(rid, exc_bar)

            if rec_price > exc_price:
                new_rooms[rid] = rec_bar
                if rec_bar != exc_bar:
                    changed = True
                    date_log.append(f"{rid}: {exc_bar}→{rec_bar} (권장 {rec_price:,} > 예외 {exc_price:,})")
            else:
                new_rooms[rid] = exc_bar

        if changed:
            rec_at_apply = {}
            for rid in new_rooms:
                if rid in DYNAMIC_ROOMS:
                    row = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                    if not row.empty:
                        _, r, _, _ = get_final_values(
                            rid, d, row.iloc[0]['Available'], row.iloc[0]['Total']
                        )
                        rec_at_apply[rid] = r

            memo = rate_info.get('memo', '')
            auto_note = ("[자동갱신] " + memo).strip() if memo and not memo.startswith("[자동갱신]") else (memo or "[자동갱신]")

            save_applied_rate(
                date_str, new_rooms,
                memo=auto_note,
                rec_at_apply=rec_at_apply,
                prev_rooms=existing_rooms,
                prev_rec_at_apply=rate_info.get('rec_bar_at_apply', {}),
            )
            updated_count += 1
            log_items.append({'date': date_str, 'changes': date_log})

    return updated_count, log_items



# =============================================================================
# 4-A-2. 변경 이력 (Audit Log) - C 개선
# =============================================================================
def log_audit(action, target_date, new_rooms, old_rooms=None, memo="", new_rec_at_apply=None, old_rec_at_apply=None, extra=None):
    """변경 이력을 audit_log 컬렉션에 기록 (무제한 보존, 수동 정리만)"""
    try:
        old_rooms = old_rooms or {}
        # 변경 사항 diff 계산
        all_keys = set(old_rooms.keys()) | set(new_rooms.keys())
        diffs = []
        for k in sorted(all_keys):
            o = old_rooms.get(k)
            n = new_rooms.get(k)
            if o != n:
                diffs.append({'room': k, 'from': o, 'to': n})

        # 변경 없으면 기록 안 함 (스팸 방지)
        if action in ("apply_save",) and not diffs:
            return

        ts = datetime.now()
        payload = {
            'action': action,  # apply_save, apply_delete, bulk_delete, restore, etc.
            'target_date': target_date,
            'logged_at': ts.isoformat(),
            'logged_at_display': ts.strftime("%Y-%m-%d %H:%M:%S"),
            'memo': memo,
            'new_rooms': new_rooms,
            'old_rooms': old_rooms,
            'diffs': diffs,
            'new_rec_at_apply': new_rec_at_apply,
            'old_rec_at_apply': old_rec_at_apply,
        }
        if extra:
            payload['extra'] = extra
        db.collection(COL_AUDIT).add(payload)
    except Exception as e:
        # 로그 실패가 본 기능을 막으면 안 됨
        pass


@st.cache_data(ttl=30)
def load_audit_log(limit=200, action_filter=None, date_from_str=None, date_to_str=None):
    """변경 이력 조회"""
    try:
        q = db.collection(COL_AUDIT).order_by("logged_at", direction=firestore.Query.DESCENDING).limit(limit)
        result = []
        for doc in q.stream():
            d = doc.to_dict()
            d['_id'] = doc.id
            if action_filter and d.get('action') != action_filter:
                continue
            if date_from_str and d.get('target_date', '') < date_from_str:
                continue
            if date_to_str and d.get('target_date', '') > date_to_str:
                continue
            result.append(d)
        return result
    except Exception:
        return []


def cleanup_audit_log(before_date_str=None):
    """변경 이력 수동 정리 (특정 날짜 이전 또는 전체)"""
    try:
        deleted = 0
        if before_date_str:
            docs = db.collection(COL_AUDIT).where("logged_at", "<", before_date_str + "T00:00:00").stream()
        else:
            docs = db.collection(COL_AUDIT).stream()

        batch = db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 400:  # Firestore batch 제한
                batch.commit()
                deleted += count
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()
            deleted += count
        st.cache_data.clear()
        return deleted
    except Exception as e:
        st.error(f"정리 실패: {e}")
        return 0


# =============================================================================
# 4-A-3. 복원 지점 (Restore Points) - I 개선
# =============================================================================
def create_restore_point(label="자동 백업", trigger="manual"):
    """현재 applied_rates 전체를 스냅샷으로 백업"""
    try:
        current_applied = {}
        for doc in db.collection(COL_APPLIED).stream():
            current_applied[doc.id] = doc.to_dict()

        ts = datetime.now()
        payload = {
            'label': label,
            'trigger': trigger,  # manual, before_bulk_delete, before_shift, etc.
            'created_at': ts.isoformat(),
            'created_at_display': ts.strftime("%Y-%m-%d %H:%M:%S"),
            'applied_count': len(current_applied),
            'applied_snapshot': current_applied,
        }
        doc_ref = db.collection(COL_RESTORE).add(payload)
        st.cache_data.clear()
        return True, ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        st.error(f"복원 지점 생성 실패: {e}")
        return False, None


@st.cache_data(ttl=30)
def load_restore_points(limit=50):
    try:
        q = db.collection(COL_RESTORE).order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        result = []
        for doc in q.stream():
            d = doc.to_dict()
            d['_id'] = doc.id
            result.append(d)
        return result
    except Exception:
        return []


def restore_from_point(point_id):
    """복원 지점으로 되돌리기. 현재 적용 요금을 모두 지우고 스냅샷으로 덮어씀.
    되돌리기 직전에도 자동 백업을 생성해서 다중 안전망."""
    try:
        doc = db.collection(COL_RESTORE).document(point_id).get()
        if not doc.exists:
            return False, "복원 지점을 찾을 수 없습니다."
        snap = doc.to_dict()
        applied_snapshot = snap.get('applied_snapshot', {})

        # 0. 되돌리기 직전 현재 상태 백업
        create_restore_point(
            label=f"되돌리기 전 자동백업 ({snap.get('label','')[:20]})",
            trigger="before_restore",
        )

        # 1. 현재 applied_rates 전체 삭제 (배치)
        batch = db.batch()
        count = 0
        for d in db.collection(COL_APPLIED).stream():
            batch.delete(d.reference)
            count += 1
            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()

        # 2. 스냅샷으로 덮어쓰기 (배치)
        batch = db.batch()
        count = 0
        for date_id, payload in applied_snapshot.items():
            ref = db.collection(COL_APPLIED).document(date_id)
            batch.set(ref, payload)
            count += 1
            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()

        # 3. audit log 기록
        log_audit(
            action="restore",
            target_date="*",
            new_rooms={},
            old_rooms={},
            memo=f"복원 지점 사용: {snap.get('label','')}",
            extra={'restored_count': len(applied_snapshot)},
        )

        st.cache_data.clear()
        return True, f"{len(applied_snapshot)}개 날짜 복원 완료"
    except Exception as e:
        return False, f"복원 실패: {e}"


def delete_restore_point(point_id):
    try:
        db.collection(COL_RESTORE).document(point_id).delete()
        st.cache_data.clear()
        return True
    except:
        return False


def cleanup_restore_points(before_date_str=None):
    """복원 지점 수동 정리"""
    try:
        deleted = 0
        if before_date_str:
            docs = db.collection(COL_RESTORE).where("created_at", "<", before_date_str + "T00:00:00").stream()
        else:
            docs = db.collection(COL_RESTORE).stream()
        batch = db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 400:
                batch.commit()
                deleted += count
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()
            deleted += count
        st.cache_data.clear()
        return deleted
    except Exception as e:
        return 0


# =============================================================================
# 4-B. 권장 vs 적용 비교 표 (A 개선: 객실 필터 파라미터 추가)
# =============================================================================
def render_applied_vs_recommend_table(current_df, applied_rates, prev_df=None, prev_applied_rates=None,
                                      highlight_only_changes=True, focus_dates=None, room_filter=None):
    """room_filter: 표시할 객실 리스트 (None이면 DYNAMIC_ROOMS 전체)"""
    if current_df.empty:
        return "<div style='padding:20px;'>데이터를 업로드하세요.</div>"

    if prev_applied_rates is None:
        prev_applied_rates = applied_rates

    use_focus = bool(focus_dates)
    if use_focus:
        normalized_focus = set()
        for fd in focus_dates:
            if hasattr(fd, 'date') and callable(getattr(fd, 'date', None)):
                normalized_focus.add(fd.date())
            else:
                normalized_focus.add(fd)
        focus_dates = normalized_focus

    dates = sorted(current_df['Date'].unique())
    rooms_to_show = room_filter if room_filter else ALL_ROOMS

    # 재검토 필요 카운트 (DYNAMIC_ROOMS만 오버라이드 대상)
    review_map = build_review_map(current_df, applied_rates)
    review_count = sum(1 for (rid, _), info in review_map.items()
                       if info['needs'] and rid in rooms_to_show and rid in DYNAMIC_ROOMS)

    review_banner = ""
    if review_count > 0:
        review_banner = f"""
        <div style='background:#FFF3E0; border:2px solid #FF6F00; padding:8px 12px;
                    margin-top:5px; border-radius:6px; font-size:13px; color:#E65100;'>
            ⚠️ <b>재검토 필요 {review_count}건</b> — 적용 시점 이후 시스템 권장이 변경된 셀이 있습니다
        </div>
        """

    html = f"""
    <div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px;
                padding:10px; background:#f0f2f6; border-left:10px solid #FF8F00;'>
        🔍 4. 권장 vs 적용 비교 대조표 (CMS 관리용)
    </div>
    {review_banner}
    """
    html += "<div style='overflow-x:auto; white-space:nowrap; border:1px solid #ddd; margin-top:5px;'>"
    html += "<table style='width:100%; border-collapse:collapse; font-size:11px; min-width:1000px;'>"
    html += "<thead><tr style='background:#f9f9f9;'>"
    html += "<th rowspan='2' style='border:1px solid #ddd; width:180px; position:sticky; left:0; background:#f9f9f9; z-index:2; padding:5px;'>객실</th>"
    for d in dates:
        html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd == '일' else ("blue" if wd == '토' else "black")
        html += f"<th style='border:1px solid #ddd; padding:5px; color:{color};'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in rooms_to_show:
        is_fixed = rid in FIXED_ROOMS
        row_label = f"<b>{rid}</b>" + (" <span style='font-size:9px;color:#999;'>연동</span>" if is_fixed else "")
        html += f"<tr><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000; position:sticky; left:0; z-index:1;'>{row_label}</td>"

        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd; padding:8px; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            _, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total)

            d_key = d.date() if (hasattr(d, 'date') and callable(getattr(d, 'date', None))) else d
            if use_focus and d_key not in focus_dates:
                applied_bar_o = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
                bar_show = applied_bar_o if applied_bar_o else rec_bar
                style = "border:1px solid #eee; padding:8px; text-align:center; background-color: #FAFAFA; color: #BBB;"
                cell_content = f"<span style='font-size:9px;'>포커스외</span><br><span style='font-size:10px;'>{bar_show}</span>"
                html += f"<td style='{style}' title='5번 선택 외 날짜'>{cell_content}</td>"
                continue

            # ── 연동 객실 (GDB/GDF/FFD/FPT/PPV) ──
            if is_fixed:
                # 오버라이드 확인
                fixed_override = applied_rates.get(date_str, {}).get('rooms', {}).get(rid) if applied_rates else None
                _fovr_is_price = fixed_override and str(fixed_override).strip().isdigit()
                _fovr_is_bar = fixed_override and str(fixed_override).strip().upper().startswith('BAR')

                prev_rec_bar_f = None
                if prev_df is not None and not prev_df.empty:
                    prev_m_f = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                    if not prev_m_f.empty:
                        try:
                            _pf_all = compute_all_prices_for_date(d, prev_df, dict(st.session_state.get('manual_bars', {})))
                            prev_rec_bar_f = _pf_all.get(rid, {}).get('bar')
                        except Exception:
                            prev_rec_bar_f = None
                is_trend_f = (prev_rec_bar_f is not None and
                              str(prev_rec_bar_f).strip() != str(rec_bar).strip())

                if fixed_override:
                    # 오버라이드 있음 — 초록 테두리로 표시
                    bg_f = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    style = (f"border:2px solid #2E7D32; padding:8px; text-align:center;"
                             f"background-color:{bg_f}; font-weight:bold;")
                    if _fovr_is_price:
                        ovr_price = int(str(fixed_override).strip())
                        cell_content = (f"⭐ <b>직접가격</b><br>"
                                        f"<span style='font-size:9px;color:#1B5E20;'>{ovr_price:,}</span><br>"
                                        f"<span style='font-size:8px;color:#555;'>권장:{rec_price:,}</span>")
                    else:
                        ovr_bar = str(fixed_override).strip().upper()
                        ovr_price_f = get_bar_price(rid, ovr_bar) or rec_price
                        cell_content = (f"⭐ <b>{ovr_bar}</b><br>"
                                        f"<span style='font-size:9px;color:#1B5E20;'>{ovr_price_f:,}</span><br>"
                                        f"<span style='font-size:8px;color:#555;'>권장:{rec_bar}</span>")
                    tooltip_f = f"title='연동객실 수동오버라이드'"
                elif is_trend_f:
                    try:
                        _pnum = int(str(prev_rec_bar_f).replace('BAR',''))
                        _cnum = int(str(rec_bar).replace('BAR',''))
                        _farrow = "▲" if _cnum < _pnum else "▼"
                        _fborder = "#B71C1C" if _cnum < _pnum else "#0D47A1"
                    except Exception:
                        _farrow, _fborder = "▲", "#B71C1C"
                    bg_f = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    style = (f"border:1.5px solid {_fborder}; padding:8px; text-align:center;"
                             f"background-color: {bg_f}; font-weight:bold;")
                    cell_content = (f"{_farrow} <b style='font-size:13px;'>{rec_bar}</b><br>"
                                    f"<span style='font-size:9px;opacity:0.7;'>{prev_rec_bar_f}</span><br>"
                                    f"<span style='font-size:9px;'>{rec_price:,}</span>")
                    tooltip_f = f"title='이전 {prev_rec_bar_f} → 현재 {rec_bar}'"
                elif highlight_only_changes:
                    style = "border:1px solid #eee; padding:8px; text-align:center; background-color:#FAFAFA; color:#BBB;"
                    cell_content = f"<span style='font-size:10px;'>{rec_bar}</span>"
                    tooltip_f = ""
                else:
                    bg_f = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    style = f"border:1px solid #ddd; padding:8px; text-align:center; background-color:{bg_f};"
                    cell_content = f"<b>{rec_bar}</b><br><span style='font-size:9px;'>{rec_price:,}</span>"
                    tooltip_f = ""
                html += f"<td style='{style}' {tooltip_f}>{cell_content}</td>"
                continue

            # ── 기존 DYNAMIC 객실: 오버라이드 비교 로직 ──
            applied_info = applied_rates.get(date_str, {})
            applied_bar = applied_info.get('rooms', {}).get(rid)
            memo = applied_info.get('memo', '')
            applied_at = applied_info.get('applied_at_display', '')
            rec_at_apply = applied_info.get('rec_bar_at_apply', {}).get(rid)

            needs_review = bool(applied_bar and rec_at_apply and rec_at_apply != rec_bar)

            prev_rec_bar = None
            if prev_df is not None and not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    try:
                        _pd_all = compute_all_prices_for_date(d, prev_df, dict(st.session_state.get('manual_bars', {})))
                        prev_rec_bar = _pd_all.get(rid, {}).get('bar')
                    except Exception:
                        prev_rec_bar = None

            is_trend_changed = (prev_rec_bar is not None and
                                str(prev_rec_bar).strip() != str(rec_bar).strip())

            is_calm = (applied_bar and applied_bar == rec_bar and
                       not needs_review and not is_trend_changed)

            tip_parts = []
            if memo: tip_parts.append(f"📝 {memo}")
            if applied_at: tip_parts.append(f"⏰ {applied_at}")
            if needs_review: tip_parts.append(f"⚠️ 적용시점 권장: {rec_at_apply} → 현재 권장: {rec_bar}")
            if is_trend_changed: tip_parts.append(f"▲ 이전 권장: {prev_rec_bar} → 현재 권장: {rec_bar}")
            memo_text = " | ".join(tip_parts)
            tooltip = f"title='{memo_text}'" if memo_text else ""

            if not applied_bar:
                style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #FAFAFA; color: #999;"
                cell_content = f"<span style='font-size:9px;'>대기중</span><br>{rec_bar}"
            elif needs_review:
                style = "border:2px solid #FF6F00; padding:8px; text-align:center; background-color: #FFF3E0; color: #E65100; font-weight:bold;"
                cell_content = f"⚠️ <b>{applied_bar}</b><br><span style='font-size:9px; color:#FF6F00;'>권장→{rec_bar}</span>"
            elif applied_bar == rec_bar:
                if highlight_only_changes and is_calm:
                    style = "border:1px solid #eee; padding:8px; text-align:center; background-color: #FAFAFA; color: #BBB;"
                    cell_content = f"<span style='font-size:10px;'>✓ {applied_bar}</span>"
                elif is_trend_changed:
                    style = "border:1.5px solid #2E7D32; padding:8px; text-align:center; background-color: #C8E6C9; color: #1B5E20; font-weight:bold;"
                    try:
                        _tn_p = int(str(prev_rec_bar).replace('BAR',''))
                        _tn_c = int(str(applied_bar).replace('BAR',''))
                        _t_arrow = "▲" if _tn_c < _tn_p else "▼"
                    except Exception:
                        _t_arrow = "▲"
                    cell_content = (f"{_t_arrow} <b style='font-size:13px;'>{applied_bar}</b><br>"
                                    f"<span style='font-size:9px;opacity:0.7;'>{prev_rec_bar}</span>")
                else:
                    style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #E8F5E9; color: #2E7D32;"
                    cell_content = f"✅ <b>{applied_bar}</b>"
            else:
                # 오버라이드 방향 구분: 고가유지(파랑) vs 저가오버라이드(주황)
                try:
                    _app_n = int(applied_bar.replace('BAR', ''))
                    _rec_n = int(rec_bar.replace('BAR', ''))
                    _keeping_high = _app_n < _rec_n  # 낮은 BAR 번호 = 높은 가격
                except Exception:
                    _keeping_high = False
                if _keeping_high:
                    style = ("border:1.5px solid #1565C0; padding:8px; text-align:center; "
                             "background-color:#E3F2FD; color:#0D47A1; font-weight:bold;")
                    cell_content = (f"<span style='font-size:9px;color:#90CAF9;"
                                    f"text-decoration:line-through;'>{rec_bar}</span><br>"
                                    f"🏷️ <b>{applied_bar}</b><br>"
                                    f"<span style='font-size:8px;color:#1565C0;'>고가유지</span>")
                else:
                    style = ("border:1.5px dashed #FF8F00; padding:8px; text-align:center; "
                             "background-color:#FFF3E0; color:#C62828;")
                    cell_content = (f"<span style='font-size:10px;text-decoration:line-through;"
                                    f"color:#999;'>{rec_bar}</span><br>⭐ <b>{applied_bar}</b>")

            html += f"<td style='{style}' {tooltip}>{cell_content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html


# =============================================================================
# 4-C. 요금 적용 UI
# =============================================================================
def render_apply_rate_ui(current_df, applied_rates):
    if current_df.empty: return
    st.markdown("""<div style='margin-top:40px; margin-bottom:15px; font-weight:bold; font-size:18px; padding:10px; background:#FFF3E0; border-left:10px solid #FF6F00;'>⏰ 5. 예외 설정 — 특정 날짜 BAR 고정 (파일 재업로드 후에도 유지)</div>""", unsafe_allow_html=True)
    st.caption("🔧 특정 일자의 요금을 시스템 권장과 다르게 강제로 묶거나 인상할 때 사용합니다. "
               "여기서 설정한 예외는 이후 파일 재업로드·저장 시에도 유지되며, "
               "판도변화로 권장가가 예외가보다 높아질 경우 자동으로 권장가로 갱신됩니다.")

    all_dates_full = sorted(current_df['Date'].unique())
    today = date.today()

    # 필터 옵션
    st.markdown("##### 🎚️ 날짜 필터 옵션")
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        include_past = st.checkbox("📜 과거 날짜 포함", value=False, key="apply_include_past")
    with fcol2:
        only_overridden = st.checkbox("⭐ 오버라이드된 날짜만 보기", value=False, key="apply_only_overridden",
                                       help="이미 수동 적용된 날짜만 필터링 (재수정용)")
    with fcol3:
        only_review_needed = st.checkbox("⚠️ 재검토 필요한 날짜만 보기", value=False, key="apply_only_review",
                                          help="시스템 권장이 바뀐 오버라이드 날짜만 표시")

    dates = all_dates_full if include_past else [d for d in all_dates_full if d >= today]

    if only_overridden:
        overridden_dates = set()
        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            if applied_rates.get(date_str, {}).get('rooms'):
                overridden_dates.add(d)
        dates = sorted(overridden_dates)

    if only_review_needed:
        review_dates = set()
        for d in dates:
            for rid in DYNAMIC_ROOMS:
                needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)
                if needs_review:
                    review_dates.add(d)
                    break
        dates = sorted(review_dates)

    if not dates:
        if only_overridden:
            return st.info("✨ 오버라이드된 날짜가 없습니다.")
        if only_review_needed:
            return st.success("✅ 재검토가 필요한 날짜가 없습니다.")
        return st.warning("⚠️ 선택 가능한 날짜가 없습니다.")

    # 누적 날짜 선택
    st.markdown("##### 📅 적용할 날짜 누적 선택")
    st.caption("💡 아래 도구로 기간/일자를 **추가**하면 누적됩니다. 기간+기간, 기간+일자, 일자+일자 자유 조합 가능!")

    if '_picked_dates' not in st.session_state:
        st.session_state['_picked_dates'] = set()

    # 빠른 프리셋
    with st.container(border=True):
        st.markdown("**🎯 빠른 프리셋 (클릭 시 누적 추가)**")
        pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)

        def add_to_picked(new_dates):
            valid = []
            for d in new_dates:
                if d in dates:
                    if hasattr(d, 'date') and callable(getattr(d, 'date', None)):
                        valid.append(d.date())
                    else:
                        valid.append(d)
            st.session_state['_picked_dates'].update(valid)

        with pcol1:
            if st.button("➕ 이번 주", use_container_width=True, key="preset_thisweek"):
                monday = today - timedelta(days=today.weekday())
                add_to_picked([d for d in dates if monday <= d <= monday + timedelta(days=6)])
                st.rerun()
        with pcol2:
            if st.button("➕ 다음 주", use_container_width=True, key="preset_nextweek"):
                monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
                add_to_picked([d for d in dates if monday <= d <= monday + timedelta(days=6)])
                st.rerun()
        with pcol3:
            if st.button("➕ 이번 달 남은 날", use_container_width=True, key="preset_thismonth"):
                add_to_picked([d for d in dates if d >= today and d.month == today.month])
                st.rerun()
        with pcol4:
            if st.button("➕ 전체 (필터된)", use_container_width=True, key="preset_all"):
                add_to_picked(list(dates))
                st.rerun()
        with pcol5:
            if st.button("🗑️ 전체 비우기", use_container_width=True, key="preset_clear"):
                st.session_state['_picked_dates'] = set()
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.rerun()

    # 기간 추가
    with st.container(border=True):
        st.markdown("**📆 기간 추가 (시작일 ~ 종료일)** — 여러 번 누르면 여러 기간 누적!")
        rc1, rc2, rc3 = st.columns([2, 2, 1])
        with rc1:
            range_start = st.date_input("시작일", value=dates[0], min_value=dates[0], max_value=dates[-1], key="apply_range_start")
        with rc2:
            range_end = st.date_input("종료일", value=dates[-1], min_value=dates[0], max_value=dates[-1], key="apply_range_end")
        with rc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 이 기간 추가", use_container_width=True, key="apply_range_btn", type="primary"):
                if range_start > range_end:
                    st.error("시작일이 종료일보다 늦습니다.")
                else:
                    new_dates = [d for d in dates if range_start <= d <= range_end]
                    add_to_picked(new_dates)
                    st.rerun()

    # 개별 일자 추가
    with st.container(border=True):
        st.markdown("**📍 개별 일자 추가** — 점 찍듯이 골라서 누적!")
        ic1, ic2 = st.columns([3, 1])
        with ic1:
            single_pick = st.multiselect(
                "추가할 일자 선택 (여러 개 한번에 가능)",
                options=dates,
                format_func=lambda d: f"{d.strftime('%m-%d')} ({WEEKDAYS_KR[d.weekday()]})",
                key="apply_single_pick",
                label_visibility="collapsed"
            )
        with ic2:
            if st.button("➕ 일자 추가", use_container_width=True, key="apply_single_add", type="primary"):
                if single_pick:
                    add_to_picked(single_pick)
                    if "apply_single_pick" in st.session_state:
                        del st.session_state["apply_single_pick"]
                    st.rerun()
                else:
                    st.warning("일자를 먼저 선택하세요.")

    selected_dates = sorted(st.session_state['_picked_dates'])

    if not selected_dates:
        return st.info("👆 위 도구로 날짜를 먼저 추가하세요. (기간/일자/프리셋 자유 조합)")

    chips_html = "".join([
        f"<span style='background:#E3F2FD; border:1px solid #1976D2; color:#0D47A1; "
        f"padding:3px 8px; border-radius:12px; margin:2px; font-size:11px; "
        f"display:inline-block; font-weight:bold;'>"
        f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})</span>"
        for d in selected_dates
    ])
    st.markdown(f"""
    <div style='background:#F5F5F5; padding:8px 12px; border-radius:8px; margin:8px 0;
                border-left:4px solid #1976D2;'>
        <b style='color:#1976D2;'>✅ 누적 선택된 날짜 ({len(selected_dates)}일):</b><br>
        {chips_html}
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🔧 누적 목록 미세 조정 (제거하고 싶은 날짜 체크 해제)", expanded=False):
        adjusted = st.multiselect(
            "최종 적용할 날짜 (체크 해제하면 제외)",
            options=selected_dates,
            default=selected_dates,
            format_func=lambda d: f"{d.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[d.weekday()]})",
            key="apply_date_finetune"
        )
        if len(adjusted) != len(selected_dates):
            if st.button("✂️ 위 조정 사항 적용", key="apply_finetune_apply"):
                st.session_state['_picked_dates'] = set(adjusted)
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.rerun()

    if not selected_dates: return st.info("👆 위에서 날짜를 먼저 선택하세요.")

    bar_options = ["BAR0"] + [f"BAR{i}" for i in range(1, 9)]

    safe_date_str = "".join([d.strftime('%d') for d in selected_dates])
    matrix_key = f"apply_matrix_data_{len(selected_dates)}_{safe_date_str}"

    rec_bar_map = {}
    for rid in DYNAMIC_ROOMS:
        for d in selected_dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            rec_bar = "BAR5"
            if not curr_match.empty:
                _, rec_bar, _, _ = get_final_values(rid, d, curr_match.iloc[0]['Available'], curr_match.iloc[0]['Total'])
            rec_bar_map[(rid, date_str)] = rec_bar

    def build_initial_matrix():
        data = []
        for rid in DYNAMIC_ROOMS:
            row_data = {"객실": rid}
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                existing = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
                row_data[col_label] = existing if existing else rec_bar_map.get((rid, date_str), "BAR5")
            data.append(row_data)
        return data

    # 빠른 채우기
    st.markdown("**🔧 빠른 채우기**")
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
    with btn_col1:
        if st.button("🎯 권장 BAR 전체 채우기", use_container_width=True, key="fill_recommended"):
            data = []
            for rid in DYNAMIC_ROOMS:
                row_data = {"객실": rid}
                for d in selected_dates:
                    date_str = d.strftime('%Y-%m-%d')
                    col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    row_data[col_label] = rec_bar_map.get((rid, date_str), "BAR5")
                data.append(row_data)
            st.session_state[matrix_key] = data
            st.rerun()
    with btn_col2:
        bulk_bar = st.selectbox("일괄 BAR", bar_options, index=4, key="bulk_bar_select", label_visibility="collapsed")
    with btn_col3:
        if st.button(f"⚡ 전체 {bulk_bar}로", use_container_width=True, key="fill_bulk"):
            data = []
            for rid in DYNAMIC_ROOMS:
                row_data = {"객실": rid}
                for d in selected_dates:
                    col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    row_data[col_label] = bulk_bar
                data.append(row_data)
            st.session_state[matrix_key] = data
            st.rerun()
    with btn_col4:
        if st.button("🔄 저장된 값으로 리셋", use_container_width=True, key="reset_matrix"):
            if matrix_key in st.session_state: del st.session_state[matrix_key]
            st.rerun()

    # 일괄 시프트
    st.markdown("**📈 일괄 시프트 (오버라이드 한번에 조정)**")
    sft_col1, sft_col2, sft_col3, sft_col4 = st.columns(4)

    def shift_bar(bar_str, step):
        if not bar_str or bar_str == "BAR0":
            return bar_str
        try:
            n = int(bar_str.replace("BAR", ""))
            new_n = max(1, min(8, n + step))
            return f"BAR{new_n}"
        except:
            return bar_str

    with sft_col1:
        if st.button("⬆️ 한 단계 인상 (BAR↓)", use_container_width=True, key="shift_up_1"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, -1)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    with sft_col2:
        if st.button("⬇️ 한 단계 인하 (BAR↑)", use_container_width=True, key="shift_down_1"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, 1)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    with sft_col3:
        if st.button("⏫ 두 단계 인상", use_container_width=True, key="shift_up_2"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, -2)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    with sft_col4:
        if st.button("⏬ 두 단계 인하", use_container_width=True, key="shift_down_2"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, 2)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()

    if matrix_key not in st.session_state: st.session_state[matrix_key] = build_initial_matrix()
    matrix_df = pd.DataFrame(st.session_state[matrix_key])

    col_config = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
    for d in selected_dates:
        col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
        col_config[col_label] = st.column_config.SelectboxColumn(options=bar_options, required=True, width="small")

    edited_matrix = st.data_editor(matrix_df, column_config=col_config, use_container_width=True, hide_index=True, key="apply_matrix_editor_v2")

    applied_input = {}
    for idx, row in edited_matrix.iterrows():
        rid = row["객실"]
        for d in selected_dates:
            date_str = d.strftime('%Y-%m-%d')
            col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            raw_val = row.get(col_label)
            bar_val = str(raw_val).strip().upper() if raw_val and pd.notna(raw_val) else None
            if bar_val and bar_val in bar_options:
                if d not in applied_input: applied_input[d] = {}
                applied_input[d][rid] = bar_val

    # ── 연동 객실 수동 오버라이드 ──────────────────────────────────────────
    st.markdown("---")
    with st.expander("🔗 연동 객실 수동 오버라이드 (선택적)", expanded=False):
        st.caption(
            "GDB/GDF/FFD: 직접 가격(원) 입력. FPT/PPV: BAR 선택. "
            "비워두면 연동 산식 그대로. 저장 버튼은 아래 공통 버튼 사용."
        )

        price_rooms_fixed = ["GDB", "GDF", "FFD"]
        bar_rooms_fixed   = ["FPT", "PPV"]
        bar_options_with_empty = [""] + bar_options
        fixed_price_key = f"fxprice_{len(selected_dates)}_{safe_date_str}"
        fixed_bar_key   = f"fxbar_{len(selected_dates)}_{safe_date_str}"

        def _build_price_matrix():
            rows = []
            for rid in price_rooms_fixed:
                row = {"객실": rid}
                for d in selected_dates:
                    lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    existing = applied_rates.get(d.strftime('%Y-%m-%d'), {}).get('rooms', {}).get(rid)
                    row[lbl] = int(existing) if existing and str(existing).isdigit() else None
                rows.append(row)
            return rows

        def _build_bar_matrix():
            rows = []
            for rid in bar_rooms_fixed:
                row = {"객실": rid}
                for d in selected_dates:
                    lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    existing = applied_rates.get(d.strftime('%Y-%m-%d'), {}).get('rooms', {}).get(rid)
                    row[lbl] = existing if existing in bar_options else ""
                rows.append(row)
            return rows

        if fixed_price_key not in st.session_state:
            st.session_state[fixed_price_key] = _build_price_matrix()
        if fixed_bar_key not in st.session_state:
            st.session_state[fixed_bar_key] = _build_bar_matrix()

        st.markdown("**GDB / GDF / FFD — 직접 가격 (원)**")
        pcfg = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
        for d in selected_dates:
            lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            pcfg[lbl] = st.column_config.NumberColumn(min_value=0, max_value=3000000, step=1000, width="small", format="%d원")
        edited_price_fx = st.data_editor(
            pd.DataFrame(st.session_state[fixed_price_key]),
            column_config=pcfg, use_container_width=True, hide_index=True,
            key="fx_price_editor"
        )

        st.markdown("**FPT / PPV — BAR 선택**")
        bcfg = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
        for d in selected_dates:
            lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            bcfg[lbl] = st.column_config.SelectboxColumn(options=bar_options_with_empty, required=False, width="small")
        edited_bar_fx = st.data_editor(
            pd.DataFrame(st.session_state[fixed_bar_key]),
            column_config=bcfg, use_container_width=True, hide_index=True,
            key="fx_bar_editor"
        )

        # 파싱 → applied_input에 병합
        for _, row in edited_price_fx.iterrows():
            rid = row["객실"]
            for d in selected_dates:
                lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                val = row.get(lbl)
                if val is not None and pd.notna(val):
                    try:
                        pval = int(float(val))
                        if pval > 0:
                            if d not in applied_input: applied_input[d] = {}
                            applied_input[d][rid] = str(pval)
                    except Exception:
                        pass

        for _, row in edited_bar_fx.iterrows():
            rid = row["객실"]
            for d in selected_dates:
                lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                val = row.get(lbl)
                bval = str(val).strip().upper() if val and pd.notna(val) else ""
                if bval in bar_options:
                    if d not in applied_input: applied_input[d] = {}
                    applied_input[d][rid] = bval
    # ────────────────────────────────────────────────────────────────────────

    memo = st.text_area("📝 메모 (툴팁 표시용)", placeholder="예: 총지배인 지시로 유지 / 단체예약 있어서 조정 안함", key="apply_memo", height=70)

    # 저장 후 선택 초기화 옵션 (기본 ON → 순차 저장 편의)
    clear_after_save = st.checkbox(
        "💡 저장 후 날짜 선택 초기화 (다른 기간 이어서 저장할 때 편리)",
        value=True,
        key="apply_clear_after_save",
        help="ON: 저장 완료 후 선택 목록을 비워서 다음 기간을 새로 선택할 수 있습니다. "
             "OFF: 선택을 유지합니다."
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("💾 선택한 날짜 모두 적용 저장", type="primary", use_container_width=True, key="apply_save_btn"):
            # 저장 직전 복원 지점 자동 생성 (I 개선)
            try:
                if len(selected_dates) >= 3:  # 3일 이상 일괄 저장 시에만
                    create_restore_point(
                        label=f"적용 저장 직전 ({len(selected_dates)}일)",
                        trigger="before_apply_save",
                    )
            except: pass

            success_count, fail_count = 0, 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                if applied_input.get(d, {}):
                    rec_at_apply = {}
                    for rid in applied_input[d].keys():
                        rec_at_apply[rid] = rec_bar_map.get((rid, date_str), "BAR5")

                    prev_payload = applied_rates.get(date_str, {})
                    prev_rooms = prev_payload.get('rooms', {})
                    prev_rec_at_apply = prev_payload.get('rec_bar_at_apply', {})

                    if save_applied_rate(date_str, applied_input[d], memo, rec_at_apply,
                                         prev_rooms=prev_rooms, prev_rec_at_apply=prev_rec_at_apply):
                        success_count += 1
                    else:
                        fail_count += 1
            if success_count:
                _clear = st.session_state.get("apply_clear_after_save", True)
                if _clear:
                    st.success(f"✅ {success_count}일 저장 완료! 날짜 선택이 초기화됐습니다 — 다음 기간을 선택하세요.")
                    st.session_state['_picked_dates'] = set()
                else:
                    st.success(f"✅ {success_count}일 적용 완료! (선택 유지)")
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_") or k.startswith("_review_map_cache_"):
                        del st.session_state[k]
                st.rerun()
    with col2:
        if st.button("🗑️ 선택일 적용 기록 해제", use_container_width=True, key="apply_delete_btn"):
            try:
                if len(selected_dates) >= 3:
                    create_restore_point(
                        label=f"적용 해제 직전 ({len(selected_dates)}일)",
                        trigger="before_apply_delete",
                    )
            except: pass

            del_count = 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                prev_payload = applied_rates.get(date_str, {})
                if delete_applied_rate(date_str,
                                        prev_rooms=prev_payload.get('rooms', {}),
                                        prev_memo=prev_payload.get('memo', ''),
                                        prev_rec_at_apply=prev_payload.get('rec_bar_at_apply', {})):
                    del_count += 1
            if del_count:
                st.success(f"🗑️ {del_count}일 수동 적용 해제됨 (시스템 권장가로 원복) · 선택은 유지")
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_") or k.startswith("_review_map_cache_"):
                        del st.session_state[k]
                st.rerun()


# =============================================================================
# 4-D. 채널 판매가 (요청 1 적용: items_override 파라미터)
# =============================================================================
def render_channel_sale_table(current_df, prev_df, ch_name, applied_rates, prev_applied_rates=None,
                              highlight_only_changes=True, focus_dates=None, items_override=None):
    """items_override: 외부에서 필터된 items 리스트를 직접 주입 (None이면 promotions에서 로드)"""
    if current_df.empty:
        return ""

    if items_override is not None:
        items_to_show = items_override
    else:
        items_to_show = st.session_state.promotions.get(ch_name, {}).get("items", [])

    if not items_to_show:
        return f"<div style='padding:10px; color:gray;'>👉 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"

    if prev_applied_rates is None:
        prev_applied_rates = applied_rates

    use_focus = bool(focus_dates)
    if use_focus:
        normalized_focus = set()
        for fd in focus_dates:
            if hasattr(fd, 'date') and callable(getattr(fd, 'date', None)):
                normalized_focus.add(fd.date())
            else:
                normalized_focus.add(fd)
        focus_dates = normalized_focus

    dates = sorted(current_df['Date'].unique())

    html = f"""
    <div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px;
                padding:10px; background:#E8F5E9; border-left:10px solid #2E7D32;'>
        ✅ {ch_name} 판매가 산출 (최종 동기화 반영)
    </div>
    """
    html += "<div style='overflow-x:auto; white-space:nowrap; border:1px solid #ddd;'>"
    html += "<table style='width:100%; border-collapse:collapse; font-size:11px; min-width:1000px;'>"
    html += "<thead><tr style='background:#f9f9f9;'>"
    html += "<th rowspan='2' style='border:1px solid #ddd; width:200px; position:sticky; left:0; background:#f9f9f9; z-index:2; padding:5px;'>객실/프로모션</th>"
    for d in dates:
        html += f"<th style='border:1px solid #ddd; padding:3px; min-width:70px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd == '일' else ("blue" if wd == '토' else "black")
        html += f"<th style='border:1px solid #ddd; padding:3px; color:{color};'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for item in items_to_show:
        rid = item.get('객실타입', 'Unknown')
        label_text = item.get('상품명', 'No Name')
        label = f"<b>{rid}</b> <span style='color:blue; font-size:10px;'>: {label_text}</span>"

        try: discount = float(item.get('할인(%)') or 0)
        except: discount = 0.0
        try: add_price = int(item.get('추가금') or 0)
        except: add_price = 0

        border_thick = "border-bottom:3px solid #000;" if rid in ["HDF", "PPV"] else ""
        html += f"<tr style='{border_thick}'>"
        html += f"<td style='border:1px solid #ddd; padding:4px; background:#fff; border-right:3px solid #000; position:sticky; left:0; z-index:1; font-size:11px;'>{label}</td>"

        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]

            if curr_match.empty:
                html += "<td style='border:1px solid #ddd; padding:4px; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']

            _, rec_bar, _, _ = get_final_values(rid, d, avail, total)

            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
            is_applied = applied_bar is not None
            final_bar = applied_bar if is_applied else rec_bar
            base_price = get_bar_price(rid, final_bar)

            prev_rec_bar = None
            if prev_df is not None and not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    try:
                        _pch_all = compute_all_prices_for_date(d, prev_df, dict(st.session_state.get('manual_bars', {})))
                        prev_rec_bar = _pch_all.get(rid, {}).get('bar')
                    except Exception:
                        prev_rec_bar = None

            is_trend_changed = (prev_rec_bar is not None and
                                str(prev_rec_bar).strip() != str(rec_bar).strip())

            needs_review = False
            if is_applied and rid in DYNAMIC_ROOMS:
                needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)

            try:
                b_price = float(base_price) if base_price else 0
                after_disc = b_price * (1 - (discount / 100))
                final_p = int((math.floor(after_disc / 1000) * 1000) + add_price)

                is_strategic_override = is_applied and (applied_bar != rec_bar)
                is_calm = (not is_trend_changed and not needs_review and not is_strategic_override)

                d_key = d.date() if (hasattr(d, 'date') and callable(getattr(d, 'date', None))) else d
                is_out_of_focus = use_focus and (d_key not in focus_dates)

                if is_out_of_focus or (highlight_only_changes and is_calm):
                    tooltip = "title='수정 대상 외'" if is_out_of_focus else "title='수정 필요 없음'"
                    style = "background-color: #FAFAFA; color: #BBB; font-weight: normal; border: 1px solid #EEE; padding:4px; text-align:center;"
                    content = f"<span style='font-size:10px;'>{final_p:,}</span><br><span style='font-size:8px; color:#CCC;'>✓{final_bar}</span>"
                    html += f"<td style='{style}' {tooltip}>{content}</td>"
                    continue

                if is_trend_changed:
                    bg = BAR_GRADIENT_COLORS.get(final_bar, "#7000FF")
                    txt_color = "white"
                    font_weight = "bold"
                    trend_icon = "▲ "
                else:
                    bg = "#FFFFFF"
                    txt_color = "#000"
                    font_weight = "normal"
                    trend_icon = ""

                if is_applied and needs_review:
                    border_style = "border: 2px solid #FF6F00; box-shadow: inset 0 0 0 1px #FFD54F;"
                    icon = "⚠️"
                    label_color = "#FFF" if is_trend_changed else "#E65100"
                    bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>재검토:{final_bar}</span>"
                elif is_applied:
                    _memo_check = applied_rates.get(date_str, {}).get('memo', '')
                    _is_auto = isinstance(_memo_check, str) and _memo_check.startswith("[자동갱신]")
                    if _is_auto:
                        border_style = "border: 2px dashed #1565C0;"
                        icon = "🔄"
                        label_color = "#FFF" if is_trend_changed else "#1565C0"
                        bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>자동:{final_bar}</span>"
                    else:
                        border_style = "border: 2px dashed #D32F2F;"
                        icon = "⭐"
                        label_color = "#FFF" if is_trend_changed else "#D32F2F"
                        bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>수동:{final_bar}</span>"
                else:
                    border_style = "border: 1px solid #ddd;"
                    icon = ""
                    label_color = "#FFF" if is_trend_changed else "#999"
                    bar_label = f"<span style='font-size:9px; color:{label_color};'>{final_bar}</span>"

                style = f"background-color: {bg}; color: {txt_color}; font-weight: {font_weight}; {border_style}; padding:4px; text-align:center;"
                content = f"{icon}{trend_icon}{final_p:,}<br>{bar_label}"

                html += f"<td style='{style}'>{content}</td>"
            except:
                html += "<td style='border:1px solid #ddd; padding:4px; text-align:center;'>-</td>"

        html += "</tr>"

    html += "</tbody></table></div>"
    return html


# =============================================================================
# 4-E. 내일 적용될 요금 미리보기 (D 개선)
# =============================================================================
def render_tomorrow_preview(current_df, applied_rates):
    """내일/모레/글피 3일치 요금을 한눈에 카드 형태로"""
    if current_df.empty:
        return

    st.markdown("""
    <div style='margin-top:30px; margin-bottom:15px; font-weight:bold; font-size:18px;
                padding:10px; background:#E1F5FE; border-left:10px solid #0288D1;'>
        🌅 D-Day 요금 미리보기 (오늘·내일·모레 CMS 반영가)
    </div>
    """, unsafe_allow_html=True)
    st.caption("매일 아침 첫 확인용. 어떤 셀이 강조 표시되었는지 빠르게 체크하세요.")

    targets = []
    for offset, label in [(0, "오늘"), (1, "내일"), (2, "모레")]:
        d = TODAY + timedelta(days=offset)
        if d in set(current_df['Date'].unique()):
            targets.append((d, label, offset))

    if not targets:
        st.info("📭 오늘~모레 데이터가 없습니다. 리포트를 업로드하세요.")
        return

    cols = st.columns(len(targets))
    for (d, label, offset), col in zip(targets, cols):
        with col:
            date_str = d.strftime('%Y-%m-%d')
            wd = WEEKDAYS_KR[d.weekday()]
            wd_color = "#D32F2F" if wd == "일" else ("#1976D2" if wd == "토" else "#333")

            applied_info = applied_rates.get(date_str, {})
            has_applied = bool(applied_info.get('rooms'))
            memo = applied_info.get('memo', '')

            card_html = f"""
            <div style='border:2px solid {"#0288D1" if offset==0 else "#90CAF9"}; border-radius:10px;
                        padding:10px; background:{"#E1F5FE" if offset==0 else "#F5F9FF"};
                        margin-bottom:10px;'>
                <div style='font-size:13px; color:#666;'>{label}</div>
                <div style='font-size:20px; font-weight:bold;'>{d.strftime('%m월 %d일')}
                    <span style='color:{wd_color}; font-size:14px;'>({wd})</span></div>
            """
            if has_applied:
                card_html += f"<div style='margin-top:5px; padding:3px 6px; background:#FFF3E0; border-radius:4px; font-size:11px; color:#E65100;'>⭐ 오버라이드 적용됨</div>"
            else:
                card_html += f"<div style='margin-top:5px; padding:3px 6px; background:#F1F8E9; border-radius:4px; font-size:11px; color:#558B2F;'>📊 시스템 권장가</div>"
            if memo:
                card_html += f"<div style='margin-top:5px; font-size:11px; color:#666;'>📝 {memo[:40]}</div>"
            card_html += "</div>"
            st.markdown(card_html, unsafe_allow_html=True)

            # 객실별 가격 미니 테이블
            rows_html = "<table style='width:100%; font-size:11px; border-collapse:collapse;'>"
            for rid in ALL_ROOMS:
                cm = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                if cm.empty:
                    continue
                avail = cm.iloc[0]['Available']
                total = cm.iloc[0]['Total']
                _, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total)
                applied_bar = applied_info.get('rooms', {}).get(rid)
                if applied_bar:
                    final_bar = applied_bar
                    final_price = get_bar_price(rid, applied_bar)
                    star = "⭐"
                    color = "#D32F2F"
                else:
                    final_bar = rec_bar
                    final_price = rec_price
                    star = ""
                    color = "#333"
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFF")
                rows_html += f"<tr><td style='padding:3px; border-bottom:1px solid #EEE;'><b>{rid}</b></td>"
                rows_html += f"<td style='padding:3px; border-bottom:1px solid #EEE; text-align:center; background:{bg};'>{final_bar}</td>"
                rows_html += f"<td style='padding:3px; border-bottom:1px solid #EEE; text-align:right; color:{color};'>{star}{final_price:,}</td></tr>"
            rows_html += "</table>"
            st.markdown(rows_html, unsafe_allow_html=True)


# =============================================================================
# 4-F. 객실별 7일 픽업 스파크라인 (E 개선)
# =============================================================================
def render_pickup_sparklines(current_df):
    """최근 N일 픽업 추세를 작은 차트로 보여줌 (data_editor의 LineChartColumn 활용)"""
    if current_df.empty:
        return
    st.markdown("""
    <div style='margin-top:30px; margin-bottom:15px; font-weight:bold; font-size:18px;
                padding:10px; background:#F3E5F5; border-left:10px solid #7B1FA2;'>
        📈 객실별 점유 추세 (스파크라인)
    </div>
    """, unsafe_allow_html=True)
    st.caption("앞으로 14일 점유율 추이 — 픽업이 가속되는 객실/날짜 패턴을 한눈에 파악")

    # 향후 14일 데이터 추출
    future_dates = sorted([d for d in current_df['Date'].unique() if d >= TODAY])[:14]
    if not future_dates:
        st.info("미래 데이터가 없습니다.")
        return

    rows = []
    for rid in ALL_ROOMS:
        occ_series = []
        avail_series = []
        for d in future_dates:
            m = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if m.empty:
                occ_series.append(0)
                avail_series.append(0)
                continue
            avail = m.iloc[0]['Available']
            total = m.iloc[0]['Total']
            try:
                a = float(avail) if pd.notna(avail) else 0.0
                occ = ((total - a) / total * 100) if total > 0 else 0
            except:
                occ = 0
                a = 0
            occ_series.append(round(occ, 1))
            avail_series.append(int(a))
        rows.append({
            "객실": rid,
            "점유율 추이(%)": occ_series,
            "잔여실 추이": avail_series,
            "현재 점유율": occ_series[0] if occ_series else 0,
            "평균 점유율": round(sum(occ_series) / len(occ_series), 1) if occ_series else 0,
        })

    df_spark = pd.DataFrame(rows)
    st.data_editor(
        df_spark,
        use_container_width=True,
        hide_index=True,
        disabled=True,
        column_config={
            "객실": st.column_config.TextColumn(width="small"),
            "점유율 추이(%)": st.column_config.LineChartColumn(
                "점유율 추이(%)",
                width="medium",
                y_min=0,
                y_max=100,
            ),
            "잔여실 추이": st.column_config.LineChartColumn(
                "잔여실 추이",
                width="medium",
            ),
            "현재 점유율": st.column_config.NumberColumn(format="%.1f%%"),
            "평균 점유율": st.column_config.NumberColumn(format="%.1f%%"),
        },
        key="sparkline_editor",
    )


# =============================================================================
# 4-G. 모바일 카드 뷰 (G 개선)
# =============================================================================
def render_mobile_card_view(current_df, applied_rates):
    """모바일 친화적 3일 카드 뷰 (가로 스크롤 매트릭스 대안)"""
    if current_df.empty:
        return
    st.markdown("""
    <div style='margin-top:20px; margin-bottom:10px; font-weight:bold; font-size:16px;
                padding:8px; background:#FFF8E1; border-left:6px solid #FFA000;'>
        📱 모바일 뷰 (오늘부터 N일 카드 형태)
    </div>
    """, unsafe_allow_html=True)
    st.caption("출장지/회의 중 빠른 확인용. 표 대신 카드로 봅니다.")

    n_days = st.slider("표시 일수", 1, 7, 3, key="mobile_days_slider")

    target_dates = sorted([d for d in current_df['Date'].unique() if d >= TODAY])[:n_days]
    if not target_dates:
        st.info("표시할 미래 데이터가 없습니다.")
        return

    for d in target_dates:
        date_str = d.strftime('%Y-%m-%d')
        wd = WEEKDAYS_KR[d.weekday()]
        wd_color = "#D32F2F" if wd == "일" else ("#1976D2" if wd == "토" else "#333")
        is_today = (d == TODAY)
        applied_info = applied_rates.get(date_str, {})
        memo = applied_info.get('memo', '')

        st.markdown(f"""
        <div style='border:2px solid {"#0288D1" if is_today else "#CFD8DC"}; border-radius:10px;
                    padding:10px; margin:10px 0; background:{"#E1F5FE" if is_today else "#FAFAFA"};'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <span style='font-size:18px; font-weight:bold;'>
                    {d.strftime('%m월 %d일')} <span style='color:{wd_color};'>({wd})</span>
                    {"🌟 오늘" if is_today else ""}
                </span>
                <span style='font-size:11px; color:#666;'>{memo[:30] if memo else ""}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        for rid in ALL_ROOMS:
            cm = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if cm.empty: continue
            avail = cm.iloc[0]['Available']
            total = cm.iloc[0]['Total']
            occ, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total)
            applied_bar = applied_info.get('rooms', {}).get(rid)
            if applied_bar:
                final_bar = applied_bar
                final_price = get_bar_price(rid, applied_bar)
                mark = "⭐"
                badge_bg = "#FFEBEE"
                badge_color = "#C62828"
            else:
                final_bar = rec_bar
                final_price = rec_price
                mark = ""
                badge_bg = "#E8F5E9"
                badge_color = "#2E7D32"

            bg_bar = BAR_GRADIENT_COLORS.get(final_bar, "#F5F5F5")

            try:
                avail_int = int(float(avail)) if pd.notna(avail) else 0
            except:
                avail_int = 0

            st.markdown(f"""
            <div style='display:flex; justify-content:space-between; align-items:center;
                        padding:6px 12px; border-bottom:1px solid #EEE; background:white;'>
                <div style='font-weight:bold; min-width:50px;'>{rid}</div>
                <div style='background:{bg_bar}; padding:2px 8px; border-radius:4px; font-size:12px; min-width:50px; text-align:center;'>{final_bar}</div>
                <div style='font-size:13px;'>{mark}<b>{final_price:,}</b></div>
                <div style='background:{badge_bg}; color:{badge_color}; padding:2px 6px; border-radius:4px; font-size:11px;'>잔{avail_int}/점{occ:.0f}%</div>
            </div>
            """, unsafe_allow_html=True)


# =============================================================================
# 4-H. 변경 이력 조회 UI (C 개선)
# =============================================================================
def render_audit_log_ui():
    """변경 이력 조회 화면"""
    with st.expander("📋 변경 이력 (Audit Log)", expanded=False):
        st.caption("모든 적용/해제/일괄삭제/복원 기록이 무제한 보존됩니다.")

        col1, col2, col3 = st.columns(3)
        with col1:
            action_filter = st.selectbox(
                "액션 필터",
                ["전체", "apply_save", "apply_delete", "bulk_delete", "restore", "restore_create"],
                key="audit_action_filter"
            )
        with col2:
            date_from = st.date_input("대상 날짜 From", value=date.today() - timedelta(days=30),
                                       key="audit_date_from")
        with col3:
            date_to = st.date_input("대상 날짜 To", value=date.today() + timedelta(days=90),
                                     key="audit_date_to")

        limit = st.slider("최대 표시 건수", 50, 1000, 200, step=50, key="audit_limit")

        if st.button("🔍 이력 조회", use_container_width=True, key="audit_search_btn"):
            st.session_state['_audit_loaded'] = True

        if st.session_state.get('_audit_loaded'):
            logs = load_audit_log(
                limit=limit,
                action_filter=None if action_filter == "전체" else action_filter,
                date_from_str=date_from.strftime("%Y-%m-%d") if date_from else None,
                date_to_str=date_to.strftime("%Y-%m-%d") if date_to else None,
            )

            if not logs:
                st.info("조회된 이력이 없습니다.")
            else:
                st.success(f"📜 총 {len(logs)}건")

                # 표 형태로 변환
                table_rows = []
                for log in logs:
                    diffs_str = ""
                    for diff in log.get('diffs', [])[:5]:
                        diffs_str += f"{diff.get('room','')}:{diff.get('from','-')}→{diff.get('to','-')} | "
                    if len(log.get('diffs', [])) > 5:
                        diffs_str += f"...외 {len(log['diffs'])-5}건"
                    table_rows.append({
                        "시각": log.get('logged_at_display', ''),
                        "액션": log.get('action', ''),
                        "대상 날짜": log.get('target_date', ''),
                        "변경 내역": diffs_str[:200],
                        "메모": (log.get('memo') or '')[:60],
                    })
                df_log = pd.DataFrame(table_rows)
                st.dataframe(df_log, use_container_width=True, hide_index=True, height=400)

        st.divider()
        st.markdown("**🧹 이력 정리 (무제한 보존 → 수동 정리)**")
        cc1, cc2 = st.columns(2)
        with cc1:
            cleanup_before = st.date_input("이 날짜 이전 이력 삭제",
                                            value=date.today() - timedelta(days=180),
                                            key="audit_cleanup_before")
        with cc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ 정리 실행", key="audit_cleanup_btn"):
                cnt = cleanup_audit_log(before_date_str=cleanup_before.strftime("%Y-%m-%d"))
                st.success(f"✅ {cnt}건 정리 완료")
                st.rerun()


# =============================================================================
# 4-I. 복원 지점 UI (I 개선)
# =============================================================================
def render_restore_point_ui():
    """복원 지점 관리 화면"""
    with st.expander("🛟 복원 지점 (Restore Points)", expanded=False):
        st.caption("일괄 삭제·시프트·저장 직전에 자동 백업되며, 수동으로도 만들 수 있습니다.")

        # 수동 백업 생성
        col1, col2 = st.columns([3, 1])
        with col1:
            manual_label = st.text_input("백업 라벨 (수동 생성)",
                                          placeholder="예: 단체예약 반영 전 / 분기 시작 / ...",
                                          key="restore_manual_label")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📸 지금 백업", use_container_width=True, key="restore_create_btn"):
                ok, ts = create_restore_point(label=manual_label or "수동 백업", trigger="manual")
                if ok:
                    log_audit(action="restore_create", target_date="*",
                              new_rooms={}, memo=manual_label or "수동 백업")
                    st.success(f"✅ 백업 완료 ({ts})")
                    st.rerun()

        st.divider()

        # 백업 목록
        points = load_restore_points(limit=50)
        if not points:
            st.info("아직 저장된 복원 지점이 없습니다.")
        else:
            st.markdown(f"**💾 저장된 복원 지점 ({len(points)}개)**")
            for p in points[:20]:  # 최근 20개만 화면에
                with st.container(border=True):
                    pc1, pc2, pc3, pc4 = st.columns([3, 2, 1, 1])
                    with pc1:
                        st.markdown(f"**{p.get('label','(라벨 없음)')}**")
                        st.caption(f"트리거: {p.get('trigger','?')} · 적용 날짜 {p.get('applied_count',0)}개")
                    with pc2:
                        st.markdown(f"🕒 {p.get('created_at_display','')}")
                    with pc3:
                        if st.button("↩️ 복원", key=f"restore_btn_{p['_id']}", use_container_width=True):
                            st.session_state['_pending_restore'] = p['_id']
                            st.session_state['_pending_restore_label'] = p.get('label', '')
                            st.rerun()
                    with pc4:
                        if st.button("🗑️", key=f"restore_del_{p['_id']}", use_container_width=True,
                                      help="이 복원 지점 삭제"):
                            delete_restore_point(p['_id'])
                            st.rerun()

        # 복원 확인 다이얼로그
        if st.session_state.get('_pending_restore'):
            st.warning(f"⚠️ 정말 복원하시겠습니까? '{st.session_state.get('_pending_restore_label','')}'\n\n현재 적용 요금이 모두 백업 시점으로 덮어쓰여집니다. (직전 상태도 자동 백업됨)")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("✅ 예, 복원 실행", type="primary", use_container_width=True, key="restore_confirm"):
                    ok, msg = restore_from_point(st.session_state['_pending_restore'])
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(msg)
                    del st.session_state['_pending_restore']
                    if '_pending_restore_label' in st.session_state:
                        del st.session_state['_pending_restore_label']
                    st.rerun()
            with cc2:
                if st.button("❌ 취소", use_container_width=True, key="restore_cancel"):
                    del st.session_state['_pending_restore']
                    if '_pending_restore_label' in st.session_state:
                        del st.session_state['_pending_restore_label']
                    st.rerun()

        st.divider()
        st.markdown("**🧹 복원 지점 정리**")
        rc1, rc2 = st.columns(2)
        with rc1:
            rp_cleanup_before = st.date_input("이 날짜 이전 복원 지점 삭제",
                                               value=date.today() - timedelta(days=90),
                                               key="rp_cleanup_before")
        with rc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ 복원 지점 정리", key="rp_cleanup_btn"):
                cnt = cleanup_restore_points(before_date_str=rp_cleanup_before.strftime("%Y-%m-%d"))
                st.success(f"✅ {cnt}개 정리 완료")
                st.rerun()


# =============================================================================
# 5. 파서 및 DB 로직
# =============================================================================
def robust_date_parser(d_val):
    if pd.isna(d_val): return None
    try:
        if isinstance(d_val, (int, float)): return (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date()
        s = str(d_val).strip().replace('.', '-').replace('/', '-').replace(' ', '')
        match = re.search(r'(\d{1,2})-(\d{1,2})', s)
        if match: return date(2026, int(match.group(1)), int(match.group(2)))
    except: pass
    return None


def save_channel_configs():
    db.collection(COL_SETTINGS).document("channels").set({"channel_list": st.session_state.channel_list, "promotions": st.session_state.promotions})


def load_channel_configs():
    doc = db.collection(COL_SETTINGS).document("channels").get()
    if doc.exists:
        d = doc.to_dict()
        st.session_state.channel_list = d.get("channel_list", [])
        st.session_state.promotions = d.get("promotions", {})
    else:
        st.session_state.channel_list = []
        st.session_state.promotions = {}


def get_latest_snapshot():
    docs = db.collection(COL_SNAPSHOTS).order_by("save_time", direction=firestore.Query.DESCENDING).limit(1).stream()
    for doc in docs:
        d_dict = doc.to_dict()
        df = pd.DataFrame(d_dict['data'])
        if not df.empty and 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df, d_dict.get('work_date', '알수없음')
    return pd.DataFrame(), None


# =============================================================================
# 6. 메인 UI
# =============================================================================
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략 통합 수익관리 시스템")

# 가격 무결성 검증 (F 개선) - 앱 시작 시 1회
price_warnings = validate_price_tables()
if price_warnings:
    with st.expander(f"🚨 가격표 무결성 경고 {len(price_warnings)}건", expanded=False):
        for w in price_warnings:
            st.markdown(w)
        st.caption("⚠️ PRICE_TABLE 또는 FIXED_PRICE_TABLE을 점검하세요.")

if 'channel_list' not in st.session_state: load_channel_configs()
if 'today_df' not in st.session_state: st.session_state.today_df = pd.DataFrame()
if 'prev_df' not in st.session_state: st.session_state.prev_df = pd.DataFrame()
if 'compare_label' not in st.session_state: st.session_state.compare_label = ""
if 'manual_bars' not in st.session_state: st.session_state.manual_bars = {}
# 신규 5객실 추가 후 세션 캐시 리셋: room_filter_4가 FIXED_ROOMS를 포함하지 않으면 ALL_ROOMS로 재초기화
if 'room_filter_4' in st.session_state:
    cached = st.session_state.get('room_filter_4', [])
    if not any(r in cached for r in FIXED_ROOMS):
        del st.session_state['room_filter_4']

# =============================================================================
# 사이드바
# =============================================================================
with st.sidebar:
    # 모바일 뷰 토글 (G 개선)
    with st.container(border=True):
        st.markdown("### 📱 디스플레이 모드")
        view_mode = st.radio(
            "뷰 선택",
            ["💻 데스크탑 (전체 매트릭스)", "📱 모바일 (카드 뷰)"],
            key="view_mode",
            help="모바일에서는 카드 뷰가 보기 편해요"
        )

    # 포커스 모드
    picked_count = len(st.session_state.get('_picked_dates', set()))
    with st.container(border=True):
        st.markdown("### 🎯 포커스 모드")
        if picked_count > 0:
            st.markdown(f"<span style='color:#2E7D32; font-weight:bold;'>✅ 5번에서 {picked_count}일 선택됨</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color:#999; font-size:12px;'>⚪ 5번에서 날짜 선택 시 활성화</span>", unsafe_allow_html=True)

        focus_for_4 = st.checkbox(
            "4번 권장vs적용표에 적용",
            value=st.session_state.get('focus_for_4', True),
            key='focus_for_4',
            disabled=(picked_count == 0)
        )
        focus_for_easy = st.checkbox(
            "이지에디터(채널)에 적용",
            value=st.session_state.get('focus_for_easy', True),
            key='focus_for_easy',
            disabled=(picked_count == 0)
        )

        if picked_count > 0:
            if st.button("🗑️ 포커스 선택 비우기", use_container_width=True):
                st.session_state['_picked_dates'] = set()
                st.rerun()

    st.divider()

    st.header("📅 수정 내역 조회 (History)")

    try:
        all_docs = db.collection(COL_SNAPSHOTS).select(["work_date"]).stream()
        saved_dates = sorted(list(set([d.to_dict().get('work_date', '') for d in all_docs if d.to_dict().get('work_date')])))
        if saved_dates:
            st.markdown("**📌 데이터가 저장된 날짜 (최근 14일)**")
            tags = "".join([f"<span style='background:#E8F5E9; border:1px solid #4CAF50; color:#2E7D32; padding:3px 8px; border-radius:12px; margin:2px; font-size:12px; display:inline-block; font-weight:bold;'>{d[5:]} ✅</span>" for d in saved_dates[-14:]])
            st.markdown(f"<div style='margin-bottom: 10px;'>{tags}</div>", unsafe_allow_html=True)
    except Exception:
        pass

    work_day = st.date_input("조회 날짜", value=date.today())
    if st.button("📂 과거 기록 불러오기"):
        docs = db.collection(COL_SNAPSHOTS).where("work_date", "==", work_day.strftime("%Y-%m-%d")).limit(1).stream()
        found = False
        for doc in docs:
            d_dict = doc.to_dict()
            st.session_state.today_df = pd.DataFrame(d_dict['data'])
            if not st.session_state.today_df.empty and 'Date' in st.session_state.today_df.columns:
                st.session_state.today_df['Date'] = pd.to_datetime(st.session_state.today_df['Date']).dt.date

            if 'prev_data' in d_dict and d_dict['prev_data']:
                st.session_state.prev_df = pd.DataFrame(d_dict['prev_data'])
                if not st.session_state.prev_df.empty and 'Date' in st.session_state.prev_df.columns:
                    st.session_state.prev_df['Date'] = pd.to_datetime(st.session_state.prev_df['Date']).dt.date
            else:
                st.session_state.prev_df = pd.DataFrame()

            if 'saved_promotions' in d_dict:
                st.session_state.promotions = d_dict['saved_promotions']
                st.session_state.channel_list = d_dict.get('saved_channel_list', [])

            st.session_state.manual_bars = d_dict.get('saved_manual_bars', {})
            st.session_state.compare_label = f"불러온 과거 기록: {work_day}"
            found = True
        if found: st.success("역사적 스냅샷 로드 완료")
        else: st.warning("해당 날짜의 데이터가 없습니다.")

    # 특정일 데이터 삭제
    with st.expander("🗑️ 특정일 데이터 삭제 (위험)", expanded=False):
        st.warning("⚠️ 이 작업은 되돌릴 수 없습니다. 신중히 사용하세요.")

        del_day = st.date_input("삭제할 날짜", value=date.today(), key="del_target_date")
        del_day_str = del_day.strftime("%Y-%m-%d")

        try:
            snap_count = sum(1 for _ in db.collection(COL_SNAPSHOTS).where("work_date", "==", del_day_str).stream())
        except Exception:
            snap_count = 0

        applied_doc = db.collection(COL_APPLIED).document(del_day_str).get()
        has_applied = applied_doc.exists

        st.markdown(f"""
        <div style='background:#FAFAFA; padding:8px 12px; border-radius:6px;
                    border:1px solid #E0E0E0; font-size:12px; margin:8px 0;'>
            <b>📋 {del_day_str}에 저장된 데이터:</b><br>
            • 일일 스냅샷 (리포트): <b style='color:#1976D2;'>{snap_count}건</b><br>
            • 적용 요금 (오버라이드): <b style='color:#D32F2F;'>{'있음' if has_applied else '없음'}</b>
        </div>
        """, unsafe_allow_html=True)

        target_options = []
        if snap_count > 0:
            target_options.append(f"📂 일일 스냅샷 ({snap_count}건)")
        if has_applied:
            target_options.append("⭐ 적용 요금 오버라이드")
        if snap_count > 0 and has_applied:
            target_options.append("💥 둘 다 (전부 삭제)")

        if not target_options:
            st.info(f"✨ {del_day_str}에 저장된 데이터가 없습니다.")
        else:
            del_target = st.radio("삭제 대상", target_options, key="del_target_radio")

            confirm = st.checkbox(
                f"☑️ 정말로 **{del_day_str}**의 데이터를 삭제하겠습니다",
                key="del_confirm_check"
            )

            if st.button("🗑️ 영구 삭제 실행",
                         type="primary",
                         disabled=not confirm,
                         use_container_width=True,
                         key="del_execute_btn"):
                deleted_snap = 0
                deleted_applied = False

                try:
                    # 적용 요금 삭제 전 자동 백업 (I 개선)
                    if has_applied and ("적용 요금" in del_target or "둘 다" in del_target):
                        create_restore_point(label=f"{del_day_str} 단일 삭제 직전", trigger="before_single_delete")

                    if "스냅샷" in del_target or "둘 다" in del_target:
                        snap_docs = db.collection(COL_SNAPSHOTS).where("work_date", "==", del_day_str).stream()
                        batch = db.batch()
                        bc = 0
                        for doc in snap_docs:
                            batch.delete(doc.reference)
                            deleted_snap += 1
                            bc += 1
                            if bc >= 400:
                                batch.commit(); batch = db.batch(); bc = 0
                        if bc > 0: batch.commit()

                    if "적용 요금" in del_target or "둘 다" in del_target:
                        if has_applied:
                            prev_payload = applied_doc.to_dict()
                            db.collection(COL_APPLIED).document(del_day_str).delete()
                            deleted_applied = True
                            log_audit(action="apply_delete", target_date=del_day_str,
                                      new_rooms={}, old_rooms=prev_payload.get('rooms', {}),
                                      memo="단일일 직접 삭제 (사이드바)")

                    st.cache_data.clear()
                    msg_parts = []
                    if deleted_snap > 0:
                        msg_parts.append(f"📂 스냅샷 {deleted_snap}건")
                    if deleted_applied:
                        msg_parts.append("⭐ 적용 요금")

                    if msg_parts:
                        st.success(f"🗑️ 삭제 완료: {', '.join(msg_parts)}")
                        if del_day == date.today():
                            st.session_state.today_df = pd.DataFrame()
                            st.session_state.prev_df = pd.DataFrame()
                            st.session_state.compare_label = ""
                            st.info("화면을 초기화합니다. 새 리포트를 업로드하세요.")
                        st.rerun()
                    else:
                        st.warning("삭제할 데이터를 찾지 못했습니다.")
                except Exception as e:
                    st.error(f"삭제 실패: {e}")

    # 일괄 삭제
    with st.expander("💥 일괄 삭제 (기간/전체) - 매우 위험", expanded=False):
        st.error("🚨 이 기능은 여러 날짜의 데이터를 한꺼번에 삭제합니다. 매우 신중히 사용하세요.")
        st.info("💡 일괄 삭제 실행 직전에 자동으로 복원 지점이 만들어집니다. (적용 요금 한정)")

        bulk_mode = st.radio(
            "삭제 방식",
            ["📆 기간 (시작일 ~ 종료일)", "🌍 전체 데이터 (모든 날짜)"],
            key="bulk_del_mode"
        )

        bulk_target_type = st.radio(
            "삭제 대상",
            ["⭐ 적용 요금만 (오버라이드)", "📂 일일 스냅샷만 (리포트)", "💥 둘 다 (전부)"],
            key="bulk_del_type",
        )

        if bulk_mode == "📆 기간 (시작일 ~ 종료일)":
            bcol1, bcol2 = st.columns(2)
            with bcol1:
                bulk_start = st.date_input("시작일", value=date.today(), key="bulk_del_start")
            with bcol2:
                bulk_end = st.date_input("종료일", value=date.today() + timedelta(days=60), key="bulk_del_end")

        if st.button("🔍 삭제 대상 미리 보기", use_container_width=True, key="bulk_preview_btn"):
            try:
                count_snap = 0
                count_applied = 0

                if bulk_mode == "🌍 전체 데이터 (모든 날짜)":
                    if "스냅샷" in bulk_target_type or "둘 다" in bulk_target_type:
                        count_snap = sum(1 for _ in db.collection(COL_SNAPSHOTS).stream())
                    if "적용 요금" in bulk_target_type or "둘 다" in bulk_target_type:
                        count_applied = sum(1 for _ in db.collection(COL_APPLIED).stream())
                else:
                    s_str = bulk_start.strftime("%Y-%m-%d")
                    e_str = bulk_end.strftime("%Y-%m-%d")
                    if "스냅샷" in bulk_target_type or "둘 다" in bulk_target_type:
                        snap_docs = db.collection(COL_SNAPSHOTS).where("work_date", ">=", s_str).where("work_date", "<=", e_str).stream()
                        count_snap = sum(1 for _ in snap_docs)
                    if "적용 요금" in bulk_target_type or "둘 다" in bulk_target_type:
                        applied_docs = db.collection(COL_APPLIED).stream()
                        for doc in applied_docs:
                            if s_str <= doc.id <= e_str:
                                count_applied += 1

                st.session_state['_bulk_preview'] = {
                    'snap': count_snap,
                    'applied': count_applied,
                    'mode': bulk_mode,
                    'target_type': bulk_target_type,
                    'range': (bulk_start, bulk_end) if bulk_mode == "📆 기간 (시작일 ~ 종료일)" else None
                }
                st.rerun()
            except Exception as e:
                st.error(f"미리보기 실패: {e}")

        preview = st.session_state.get('_bulk_preview')
        if preview:
            range_info = ""
            if preview.get('range'):
                s, e = preview['range']
                range_info = f"({s.strftime('%Y-%m-%d')} ~ {e.strftime('%Y-%m-%d')})"
            else:
                range_info = "(전체 데이터)"

            st.markdown(f"""
            <div style='background:#FFEBEE; padding:10px; border-radius:6px;
                        border:2px solid #D32F2F; margin:8px 0;'>
                <b style='color:#B71C1C;'>🎯 삭제 예정 데이터 {range_info}:</b><br>
                • 📂 일일 스냅샷: <b>{preview['snap']}건</b><br>
                • ⭐ 적용 요금: <b>{preview['applied']}건</b><br>
                <span style='font-size:11px; color:#666;'>{preview['target_type']} / {preview['mode']}</span>
            </div>
            """, unsafe_allow_html=True)

            total = preview['snap'] + preview['applied']
            if total > 0:
                confirm_text = st.text_input(
                    f"⚠️ 정말 삭제하려면 아래에 **삭제확인**이라고 입력하세요",
                    key="bulk_del_confirm_text",
                    placeholder="삭제확인"
                )

                if st.button("💀 일괄 영구 삭제 실행",
                             type="primary",
                             disabled=(confirm_text != "삭제확인"),
                             use_container_width=True,
                             key="bulk_del_execute"):
                    try:
                        # 일괄 삭제 직전 자동 백업 (I 개선)
                        if ("적용 요금" in preview['target_type'] or "둘 다" in preview['target_type']) and preview['applied'] > 0:
                            create_restore_point(
                                label=f"일괄삭제 직전 ({preview['applied']}건)",
                                trigger="before_bulk_delete",
                            )

                        deleted_snap = 0
                        deleted_applied = 0

                        # H 개선: 배치 삭제로 최적화
                        if preview['mode'] == "🌍 전체 데이터 (모든 날짜)":
                            if "스냅샷" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                for doc in db.collection(COL_SNAPSHOTS).stream():
                                    batch.delete(doc.reference); deleted_snap += 1; bc += 1
                                    if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()
                            if "적용 요금" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                for doc in db.collection(COL_APPLIED).stream():
                                    batch.delete(doc.reference); deleted_applied += 1; bc += 1
                                    if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()
                        else:
                            s, e = preview['range']
                            s_str = s.strftime("%Y-%m-%d")
                            e_str = e.strftime("%Y-%m-%d")

                            if "스냅샷" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                snap_docs = db.collection(COL_SNAPSHOTS).where("work_date", ">=", s_str).where("work_date", "<=", e_str).stream()
                                for doc in snap_docs:
                                    batch.delete(doc.reference); deleted_snap += 1; bc += 1
                                    if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()

                            if "적용 요금" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                applied_docs = db.collection(COL_APPLIED).stream()
                                for doc in applied_docs:
                                    if s_str <= doc.id <= e_str:
                                        batch.delete(doc.reference); deleted_applied += 1; bc += 1
                                        if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()

                        log_audit(action="bulk_delete", target_date="*", new_rooms={},
                                  memo=f"{preview['target_type']} / {preview['mode']}",
                                  extra={'deleted_snap': deleted_snap, 'deleted_applied': deleted_applied, 'range': str(preview.get('range'))})

                        st.cache_data.clear()
                        del st.session_state['_bulk_preview']

                        st.session_state.today_df = pd.DataFrame()
                        st.session_state.prev_df = pd.DataFrame()
                        st.session_state.compare_label = ""
                        st.session_state.manual_bars = {}
                        if '_picked_dates' in st.session_state:
                            st.session_state['_picked_dates'] = set()
                        # 캐시 정리
                        for k in list(st.session_state.keys()):
                            if k.startswith("_review_map_cache_"):
                                del st.session_state[k]

                        st.success(f"🗑️ 일괄 삭제 완료! 스냅샷 {deleted_snap}건, 적용 요금 {deleted_applied}건")
                        st.info("화면을 초기화했습니다. 새 리포트를 업로드하세요.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"일괄 삭제 실패: {e}")
            else:
                st.success("✨ 삭제할 데이터가 없습니다.")

        if preview:
            if st.button("🔄 미리보기 리셋", use_container_width=True, key="bulk_preview_reset"):
                del st.session_state['_bulk_preview']
                st.rerun()

    st.divider()
    st.header("🎯 채널 & 상품 관리 (이지 에디터)")
    new_ch = st.text_input("새 채널 명칭")
    if st.button("➕ 채널 추가"):
        if new_ch and new_ch not in st.session_state.channel_list:
            st.session_state.channel_list.append(new_ch)
            st.session_state.promotions[new_ch] = {"items": []}
            save_channel_configs(); st.rerun()

    for ch in st.session_state.channel_list:
        with st.expander(f"📦 {ch} 상품 편집"):
            if st.button(f"❌ {ch} 채널 삭제", key=f"del_{ch}"):
                st.session_state.channel_list.remove(ch)
                st.session_state.promotions.pop(ch, None)
                save_channel_configs(); st.rerun()

            st.info("표에서 바로 수정/추가/삭제 하세요.")
            current_items = st.session_state.promotions[ch].get("items", [])
            df_editor = pd.DataFrame(current_items)

            if df_editor.empty:
                df_editor = pd.DataFrame(columns=["객실타입", "상품명", "할인(%)", "추가금"])

            edited_df = st.data_editor(
                df_editor,
                num_rows="dynamic",
                column_config={
                    "객실타입": st.column_config.SelectboxColumn(options=ALL_ROOMS, required=True),
                    "상품명": st.column_config.TextColumn(required=True),
                    "할인(%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=1),
                    "추가금": st.column_config.NumberColumn(step=1000, format="%d")
                },
                key=f"editor_{ch}",
                use_container_width=True
            )

            if st.button(f"💾 {ch} 설정 저장", key=f"save_{ch}"):
                updated_items = edited_df.to_dict(orient="records")
                st.session_state.promotions[ch]["items"] = updated_items
                save_channel_configs()
                st.success("저장 완료! 표에 즉시 반영됩니다.")

    st.divider()
    files = st.file_uploader("리포트 업로드 (부분 수정 가능)", accept_multiple_files=True)
    if st.button("🚀 오늘 내역 저장"):
        if not st.session_state.today_df.empty:
            t_df = st.session_state.today_df.copy()
            t_df['Date'] = t_df['Date'].apply(lambda x: x.isoformat())
            p_df_dict = []
            if not st.session_state.prev_df.empty:
                p_df = st.session_state.prev_df.copy()
                p_df['Date'] = p_df['Date'].apply(lambda x: x.isoformat())
                p_df_dict = p_df.to_dict(orient='records')
            db.collection(COL_SNAPSHOTS).add({
                "work_date": date.today().strftime("%Y-%m-%d"),
                "save_time": datetime.now().isoformat(),
                "data": t_df.to_dict(orient='records'),
                "prev_data": p_df_dict,
                "saved_promotions": st.session_state.promotions,
                "saved_channel_list": st.session_state.channel_list,
                "saved_manual_bars": st.session_state.manual_bars
            })
            st.cache_data.clear()
            # ── 신규: 예외 자동 갱신 (권장가 > 예외가인 경우 자동 인상) ──
            auto_cnt, auto_log = auto_update_stale_exceptions(st.session_state.today_df)
            if auto_cnt > 0:
                changes_html = "".join(
                    f"<li><b>{item['date']}</b>: {', '.join(item['changes'])}</li>"
                    for item in auto_log
                )
                st.info(f"🔄 예외 {auto_cnt}건 자동 갱신 완료 (권장가 인상 적용)\n\n"
                        f"아래 이지에디터에 반영되었습니다.")
                with st.expander(f"📋 자동 갱신 상세 ({auto_cnt}건)", expanded=False):
                    st.markdown(f"<ul>{changes_html}</ul>", unsafe_allow_html=True)
            st.success("저장 완료!")

# =============================================================================
# 7. 파일 로직 (스마트 병합)
# =============================================================================
if files:
    new_extracted = []
    ROW_MAP = {4: "GDB", 5: "GDF", 6: "FDB", 7: "FDE", 8: "FPT", 9: "FFD", 10: "HDP", 11: "HDT", 12: "HDF", 13: "PPV"}

    for f in files:
        date_tag = re.search(r'\d{8}', f.name).group() if re.search(r'\d{8}', f.name) else f.name
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values

        for r_idx, rid in ROW_MAP.items():
            if r_idx < len(df_raw):
                tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
                for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                    d_obj = robust_date_parser(d_val)
                    if d_obj is None: continue
                    new_extracted.append({"Date": d_obj, "RoomID": rid, "Available": pd.to_numeric(av, errors='coerce'), "Total": tot, "Tag": date_tag})

    if new_extracted:
        new_df = pd.DataFrame(new_extracted)

        if st.session_state.prev_df.empty:
            latest_db, save_dt = get_latest_snapshot()
            if not latest_db.empty:
                combined = pd.concat([new_df, latest_db]).drop_duplicates(subset=['Date', 'RoomID'], keep='first')
                st.session_state.today_df = combined.sort_values(by=['Date', 'RoomID'])
                st.session_state.prev_df = latest_db
                st.session_state.compare_label = f"자동 DB 병합/비교: {save_dt} 기준"
            else:
                st.session_state.today_df = new_df
                st.session_state.prev_df = pd.DataFrame()
                st.session_state.compare_label = "비교 대상 없음 (신규)"
        else:
            combined = pd.concat([new_df, st.session_state.today_df]).drop_duplicates(subset=['Date', 'RoomID'], keep='first')
            st.session_state.today_df = combined.sort_values(by=['Date', 'RoomID'])

    # 새 파일 업로드 시 리뷰 캐시 정리
    for k in list(st.session_state.keys()):
        if k.startswith("_review_map_cache_"):
            del st.session_state[k]

# =============================================================================
# 8. 메인 출력
# =============================================================================
if not st.session_state.today_df.empty:
    curr, prev = st.session_state.today_df, st.session_state.prev_df

    if st.session_state.compare_label:
        st.info(f"ℹ️ {st.session_state.compare_label}")

    # 모바일 뷰면 카드만 보여주고 끝 (G 개선)
    if st.session_state.get('view_mode', "").startswith("📱"):
        applied_rates_data = load_applied_rates()
        render_mobile_card_view(curr, applied_rates_data)
        st.divider()
        render_tomorrow_preview(curr, applied_rates_data)
        st.divider()
        st.caption("💡 데스크탑 뷰로 전환하면 전체 매트릭스, 5번 오버라이드, 채널 판매가 등을 모두 볼 수 있습니다.")
    else:
        all_dates = sorted(curr['Date'].unique())
        st.markdown(f"""
        <div style='background:#E3F2FD; padding:10px 15px; border-radius:8px; margin:15px 0;
                    border-left:5px solid #1976D2;'>
            📅 <b>오늘 기준:</b> {TODAY.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[TODAY.weekday()]}) ·
            기본적으로 <b>오늘 이후</b>만 표시됩니다. 과거 보려면 아래 체크박스 활성화하세요.
        </div>
        """, unsafe_allow_html=True)

        visible_dates = date_filter_toggle("main", all_dates, default_show_past=False)

        curr_filtered = filter_df_by_dates(curr, visible_dates)
        prev_filtered = filter_df_by_dates(prev, visible_dates) if not prev.empty else prev

        if curr_filtered.empty:
            st.warning("⚠️ 표시할 날짜가 없습니다. 위 체크박스를 활성화하거나 파일을 업로드하세요.")
        else:
            applied_rates_data = load_applied_rates()

            # D 개선: 내일 미리보기 (최상단)
            render_tomorrow_preview(curr_filtered, applied_rates_data)
            st.divider()

            # E 개선: 스파크라인
            render_pickup_sparklines(curr_filtered)
            st.divider()

            # 재검토 알림 배너
            review_map = build_review_map(curr_filtered, applied_rates_data)
            review_alerts = []
            for (rid, d), info in review_map.items():
                if info['needs']:
                    review_alerts.append({
                        '날짜': d.strftime('%m-%d'),
                        '요일': WEEKDAYS_KR[d.weekday()],
                        '객실': rid,
                        '적용 BAR': info['applied'],
                        '신규 권장': info['rec'],
                    })

            if review_alerts:
                st.markdown(f"""
                <div style='background:#FFF3E0; border:2px solid #FF6F00; padding:15px;
                            border-radius:8px; margin:15px 0; font-size:14px;'>
                    <b style='color:#E65100; font-size:16px;'>⚠️ 재검토 필요 {len(review_alerts)}건 발견!</b><br>
                    오버라이드된 날짜에서 시스템 권장이 변경되었습니다. 5번 섹션에서 '⚠️ 재검토 필요한 날짜만 보기' 필터를 사용하세요.
                </div>
                """, unsafe_allow_html=True)

                with st.expander("📋 재검토 대상 상세 보기", expanded=False):
                    df_alerts = pd.DataFrame(review_alerts)
                    st.dataframe(df_alerts, use_container_width=True, hide_index=True)

            # 1. 시장 분석
            st.markdown(render_master_table(curr_filtered, prev_filtered, title="📊 1. 시장 분석 (시스템 권장 기준)", mode="기준"), unsafe_allow_html=True)

            # 1-A. 최종 확정
            st.markdown(render_master_table(curr_filtered, prev_filtered, applied_rates=applied_rates_data, title="🎯 1-A. 최종 확정 요금 상태 (시스템 + 전략 적용)", mode="최종결과"), unsafe_allow_html=True)

            st.markdown(render_master_table(curr_filtered, prev_filtered, title="📈 2. 예약 변화량", mode="변화"), unsafe_allow_html=True)
            st.markdown(render_master_table(curr_filtered, prev_filtered, title="🔔 3. 판도 변화", mode="판도변화"), unsafe_allow_html=True)

            # 3-B. 예외 현황 요약 (신규: 현재 활성 예외 한눈에)
            with st.expander("📌 현재 활성 예외 현황 (파일 저장 시 자동 갱신됨)", expanded=False):
                st.caption(
                    "5번에서 설정한 예외들입니다. "
                    "파일을 저장하면 권장가 > 예외가인 경우 자동으로 권장가로 갱신됩니다."
                )
                _exc_applied = load_applied_rates()
                _exc_dates = sorted(
                    [ds for ds in _exc_applied if _exc_applied[ds].get('rooms')],
                    key=lambda x: x
                )
                if not _exc_dates:
                    st.info("현재 설정된 예외가 없습니다. 5번에서 추가하세요.")
                else:
                    _exc_rows = []
                    for _ds in _exc_dates:
                        try:
                            _d = datetime.strptime(_ds, '%Y-%m-%d').date()
                        except Exception:
                            continue
                        _info = _exc_applied[_ds]
                        _rooms_str = ", ".join(
                            f"{r}={b}" for r, b in sorted(_info.get('rooms', {}).items())
                        )
                        _memo = _info.get('memo', '')
                        _at = _info.get('applied_at_display', '')
                        _past = "📜" if _d < TODAY else "🔮"
                        _exc_rows.append({
                            "": _past,
                            "날짜": _ds,
                            "요일": WEEKDAYS_KR[_d.weekday()],
                            "적용 BAR": _rooms_str,
                            "메모": _memo[:40],
                            "갱신일시": _at,
                        })
                    _exc_df = pd.DataFrame(_exc_rows)
                    st.dataframe(_exc_df, use_container_width=True, hide_index=True, height=300)
                    st.caption(f"총 {len(_exc_rows)}건 활성 예외")

            # 4. 권장 vs 적용 비교 (A 개선: 행 필터)
            st.markdown("---")
            tcol1, tcol2, tcol3 = st.columns([2, 2, 3])
            with tcol1:
                highlight_changes = st.checkbox(
                    "🎯 변동된 셀만 강조 (4번 + 이지에디터)",
                    value=True,
                    key="highlight_only_changes",
                    help="ON: 권장과 같고 이전과도 동일한 '평온한' 셀은 회색 / OFF: 모든 적용 셀 진하게"
                )
            with tcol2:
                room_filter_4 = st.multiselect(
                    "🔍 4번 표 객실 필터",
                    options=ALL_ROOMS,
                    default=ALL_ROOMS,
                    key="room_filter_4",
                    help="비교표에 보고 싶은 객실만 선택 (연동객실은 읽기전용)"
                )
            with tcol3:
                picked_now = st.session_state.get('_picked_dates', set())
                f4_on = st.session_state.get('focus_for_4', True) and len(picked_now) > 0

                tip_parts = []
                if highlight_changes:
                    tip_parts.append("✅ 진짜 손댈 셀만 도드라짐")
                else:
                    tip_parts.append("📋 모든 적용 셀 진하게")
                if f4_on:
                    tip_parts.append(f"🎯 <b>포커스: {len(picked_now)}일만 활성</b>")
                elif len(picked_now) > 0:
                    tip_parts.append("⚪ 포커스 OFF")
                st.markdown(f"<div style='font-size:12px; color:#666;'>{' · '.join(tip_parts)}</div>", unsafe_allow_html=True)

            focus_for_4_table = picked_now if f4_on else None

            st.markdown(render_applied_vs_recommend_table(
                curr_filtered, applied_rates_data,
                prev_df=prev_filtered,
                prev_applied_rates=applied_rates_data,
                highlight_only_changes=highlight_changes,
                focus_dates=focus_for_4_table,
                room_filter=room_filter_4,
            ), unsafe_allow_html=True)

            # 5. 요금 적용 UI (접기/펼치기)
            with st.expander("⏰ 5. 예외 설정 — 특정 날짜 BAR 고정", expanded=False):
                render_apply_rate_ui(curr, applied_rates_data)

        # 전략적 판도 오버라이드
        with st.expander("🛠️ 전략적 판도 오버라이드 (Admin Only)", expanded=False):
            st.write("※ 여기서 수정한 내용은 오직 하단의 '✅ 판매가 산출' 표와 엑셀 다운로드에만 반영되며, 상단의 시장 분석 데이터는 원본 시스템 계산값을 유지합니다.")
            dates_list = sorted(st.session_state.today_df['Date'].unique())
            matrix_data = []

            for rid in ALL_ROOMS:
                row_data = {"객실": rid}
                for d in dates_list:
                    o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                    row_data[d.strftime('%m-%d')] = st.session_state.get('manual_bars', {}).get(o_key, "")
                matrix_data.append(row_data)

            ed_df = pd.DataFrame(matrix_data)
            col_config = {"객실": st.column_config.TextColumn(disabled=True)}
            edited_matrix = st.data_editor(ed_df, use_container_width=True, hide_index=True, column_config=col_config)

            if st.button("💾 전략 적용 및 새로고침", use_container_width=True):
                new_manual_bars = {}
                for idx, row in edited_matrix.iterrows():
                    rid = row["객실"]
                    for d in dates_list:
                        val = str(row[d.strftime('%m-%d')]).strip()
                        if val and val.upper() not in ["NONE", "NAN", ""]:
                            key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                            new_manual_bars[key] = val.upper()
                st.session_state.manual_bars = new_manual_bars
                st.success("수동 오버라이드가 하단 판매가 리포트에 적용되었습니다.")
                st.rerun()

        st.divider()

        # 채널 판매가 (요청 1 + A 개선)
        if st.session_state.channel_list:
            hlc = st.session_state.get("highlight_only_changes", True)
            picked = st.session_state.get('_picked_dates', set())
            easy_focus_on = st.session_state.get('focus_for_easy', True) and len(picked) > 0
            focus_dates = picked if easy_focus_on else None

            focus_info = ""
            if focus_dates:
                focus_info = f"🎯 <b>포커스 모드 ON</b>: 5번에서 선택한 <b>{len(focus_dates)}일</b>만 색칠"
            elif len(picked) > 0:
                focus_info = "⚪ <b>포커스 모드 OFF</b>: 사이드바 토글로 켤 수 있음"
            else:
                focus_info = "🌐 <b>전체 모드</b>: 5번에서 날짜 선택 시 그 기간만 집중 표시 가능"

            st.markdown(f"""
            <div style='background:#FFF3E0; padding:10px 15px; border-radius:8px; margin:15px 0;'>
                💡 <b>채널 판매가 표기 규칙</b> {'(🎯 변동만 강조 ON)' if hlc else '(📋 전체 보기)'}<br>
                <span style='color:#1976D2;'>{focus_info}</span>
            </div>
            """, unsafe_allow_html=True)

            # ===== 요청 1: 채널별 객실/상품 행 필터 =====
            for ch in st.session_state.channel_list:
                items_all = st.session_state.promotions.get(ch, {}).get("items", [])
                if not items_all:
                    st.markdown(render_channel_sale_table(
                        curr_filtered, prev_filtered, ch, applied_rates_data, applied_rates_data,
                        highlight_only_changes=hlc, focus_dates=focus_dates,
                    ), unsafe_allow_html=True)
                    continue

                with st.container(border=True):
                    fc1, fc2, fc3 = st.columns([2, 2, 1])
                    with fc1:
                        rooms_in_ch = sorted({it.get('객실타입') for it in items_all if it.get('객실타입')})
                        picked_rooms = st.multiselect(
                            f"🔍 [{ch}] 객실타입 필터",
                            options=rooms_in_ch,
                            default=rooms_in_ch,
                            key=f"filter_rooms_{ch}",
                            help="보고 싶은 객실타입만 선택"
                        )
                    with fc2:
                        items_by_room = [it for it in items_all if it.get('객실타입') in picked_rooms]
                        product_labels = [f"{it.get('객실타입')} · {it.get('상품명')}" for it in items_by_room]
                        picked_products = st.multiselect(
                            f"🎁 [{ch}] 개별 상품 필터",
                            options=product_labels,
                            default=product_labels,
                            key=f"filter_products_{ch}",
                            help="특정 상품만 보고 싶을 때"
                        )
                    with fc3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("전체 보기", key=f"reset_filter_{ch}", use_container_width=True):
                            for k in [f"filter_rooms_{ch}", f"filter_products_{ch}"]:
                                if k in st.session_state:
                                    del st.session_state[k]
                            st.rerun()

                filtered_items = [it for it in items_by_room
                                  if f"{it.get('객실타입')} · {it.get('상품명')}" in picked_products]

                if not filtered_items:
                    st.info(f"🔍 [{ch}] 필터 조건에 맞는 상품이 없습니다.")
                    continue

                # items_override 파라미터로 안전하게 주입 (원본 보호)
                st.markdown(render_channel_sale_table(
                    curr_filtered, prev_filtered, ch, applied_rates_data, applied_rates_data,
                    highlight_only_changes=hlc, focus_dates=focus_dates,
                    items_override=filtered_items,
                ), unsafe_allow_html=True)

        st.divider()

        # 변경 이력 & 복원 지점 UI
        render_audit_log_ui()
        render_restore_point_ui()

        st.divider()

        # 엑셀 다운로드
        st.subheader("📥 데이터 엑셀 다운로드")
        st.write("현재 화면에 계산된(수동 변경 포함) 최종 데이터 리스트를 엑셀 파일로 다운로드합니다.")

        def generate_excel():
            output = io.BytesIO()
            export_data = []
            applied_rates_export = load_applied_rates()

            for idx, row in st.session_state.today_df.iterrows():
                d = row['Date']
                rid = row['RoomID']
                date_str = d.strftime('%Y-%m-%d')

                occ, rec_bar, rec_price, _ = get_final_values(rid, d, row['Available'], row['Total'])

                applied_bar = applied_rates_export.get(date_str, {}).get('rooms', {}).get(rid)
                applied_memo = applied_rates_export.get(date_str, {}).get('memo', '')
                applied_at = applied_rates_export.get(date_str, {}).get('applied_at_display', '')
                rec_at_apply = applied_rates_export.get(date_str, {}).get('rec_bar_at_apply', {}).get(rid, '')

                if applied_bar:
                    applied_price = get_bar_price(rid, applied_bar)
                    status = "✅ 적용됨"
                    is_diff = "⚠️ 다름" if applied_bar != rec_bar else "일치"
                    needs_review = "⚠️ 재검토" if (rec_at_apply and rec_at_apply != rec_bar) else "OK"
                else:
                    applied_price = None
                    status = "⚪ 대기중"
                    is_diff = "-"
                    needs_review = "-"

                is_past = "📜 과거" if d < TODAY else "🔮 미래"

                export_data.append({
                    "날짜": date_str,
                    "요일": WEEKDAYS_KR[d.weekday()],
                    "과거/미래": is_past,
                    "객실타입": rid,
                    "잔여객실": row['Available'],
                    "전체객실": row['Total'],
                    "점유율(%)": round(occ, 1),
                    "🎯권장BAR": rec_bar,
                    "🎯권장가": rec_price,
                    "⭐적용BAR": applied_bar if applied_bar else "-",
                    "⭐적용가": applied_price if applied_price else "-",
                    "적용시점권장": rec_at_apply if rec_at_apply else "-",
                    "재검토": needs_review,
                    "상태": status,
                    "권장vs적용": is_diff,
                    "메모": applied_memo,
                    "반영일시": applied_at
                })
            df_export = pd.DataFrame(export_data)
            with pd.ExcelWriter(output) as writer:
                df_export.to_excel(writer, index=False, sheet_name='권장vs적용')
            return output.getvalue()

        st.download_button(
            label="📊 엑셀 다운로드 실행",
            data=generate_excel(),
            file_name=f"AmberPureHill_Report_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
