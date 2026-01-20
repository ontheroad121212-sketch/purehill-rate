import streamlit as st
import pandas as pd
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import math

# --- 1. 파이어베이스 초기화 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# --- 2. 전역 설정 및 데이터 ---
# 판도 변화(BAR 변경) 시 적용할 유채색 팔레트
ALERT_BAR_COLORS = {
    "BAR1": "#FF0000", "BAR2": "#FF8C00", "BAR3": "#FFD700", "BAR4": "#DAF7A6",
    "BAR5": "#2ECC71", "BAR6": "#3498DB", "BAR7": "#0000FF", "BAR8": "#BDC3C7",
}
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
DYNAMIC_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF"]
FIXED_ROOMS = ["GDB", "GDF", "FFD", "FPT", "PPV"]
ALL_ROOMS = DYNAMIC_ROOMS + FIXED_ROOMS

# [유동 객실] 요금표
PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

# [고정 객실] 시즌/요일별 요금표 (UND1~UPP2)
FIXED_PRICE_TABLE = {
    "GDB": {"UND1": 180000, "UND2": 180000, "MID1": 225000, "MID2": 225000, "UPP1": 285000, "UPP2": 315000},
    "GDF": {"UND1": 375000, "UND2": 375000, "MID1": 410000, "MID2": 410000, "UPP1": 488000, "UPP2": 488000},
    "FFD": {"UND1": 353000, "UND2": 353000, "MID1": 445000, "MID2": 445000, "UPP1": 567000, "UPP2": 567000},
    "FPT": {"UND1": 500000, "UND2": 550000, "MID1": 600000, "MID2": 650000, "UPP1": 700000, "UPP2": 750000},
    "PPV": {"UND1": 1100000, "UND2": 1100000, "MID1": 1250000, "MID2": 1250000, "UPP1": 1400000, "UPP2": 1400000},
}

# --- 3. 핵심 판별 로직 ---
def get_season_details(date_obj):
    """시즌 및 주말 여부를 판별하여 BAR 체계와 고정가 타입을 동기화"""
    m, d = date_obj.month, date_obj.day
    md = f"{m:02d}.{d:02d}"
    
    # 1. 성수기 주말 강제 적용 (명절)
    holiday_upp_weekends = ["02.13", "02.14", "02.15", "02.16", "02.17", "02.18", 
                            "09.23", "09.24", "09.25", "09.26", "09.27", "09.28"]
    
    # 2. 평수기 주말 강제 적용 (특정 연휴)
    holiday_mid_weekends = ["03.01", "05.03", "05.04", "05.05", "06.05", "06.06", "06.07"]
    
    # 3. 성수기 기간 (여름 성수기 및 연말 12/21~31 포함)
    upp_period_dates = ["10.01", "10.02", "10.03", "10.04", "10.05", "10.06", "10.07", "10.08"]
    for i in range(21, 32): upp_period_dates.append(f"12.{i}")

    is_weekend = date_obj.weekday() in [4, 5] # 기본 금,토
    
    if md in holiday_upp_weekends:
        season, is_weekend = "UPP", True
    elif ("07.17" <= md <= "08.29") or (md in upp_period_dates):
        season = "UPP"
        # 성수기 기간 내 실제 요일 적용 (단, 12월 말 주중은 UPP1, 주말은 UPP2)
    elif md in holiday_mid_weekends:
        season, is_weekend = "MID", True # 요일 상관없이 주말 바 체계 적용
    elif (1 <= m <= 3) or (11 <= m <= 12):
        season = "UND"
    else:
        season = "MID"

    type_code = f"{season}{'2' if is_weekend else '1'}"
    return season, is_weekend, type_code

def determine_bar(season, is_weekend, occ):
    """시즌/요일별 바 체계 규칙 적용"""
    if season == "UPP":
        if is_weekend: # 성수기 주말 (BAR 4 ~ BAR 1)
            if occ >= 81: return "BAR1"
            elif occ >= 51: return "BAR2"
            elif occ >= 31: return "BAR3"
            else: return "BAR4"
        else: # 성수기 주중 (BAR 5 ~ BAR 2)
            if occ >= 81: return "BAR2"
            elif occ >= 51: return "BAR3"
            elif occ >= 31: return "BAR4"
            else: return "BAR5"
    elif season == "MID":
        if is_weekend: # 평수기 주말 (BAR 6 ~ BAR 3)
            if occ >= 81: return "BAR3"
            elif occ >= 51: return "BAR4"
            elif occ >= 31: return "BAR5"
            else: return "BAR6"
        else: # 평수기 주중 (BAR 7 ~ BAR 4)
            if occ >= 81: return "BAR4"
            elif occ >= 51: return "BAR5"
            elif occ >= 31: return "BAR6"
            else: return "BAR7"
    else: # UND (비수기)
        if is_weekend: # 비수기 주말 (BAR 7 ~ BAR 4)
            if occ >= 81: return "BAR4"
            elif occ >= 51: return "BAR5"
            elif occ >= 31: return "BAR6"
            else: return "BAR7"
        else: # 비수기 주중 (BAR 8 ~ BAR 5)
            if occ >= 81: return "BAR5"
            elif occ >= 51: return "BAR6"
            elif occ >= 31: return "BAR7"
            else: return "BAR8"

def get_final_values(room_id, date_obj, avail, total):
    season, is_weekend, type_code = get_season_details(date_obj)
    occ = ((total - avail) / total * 100) if total > 0 else 0
    if room_id in DYNAMIC_ROOMS:
        bar = determine_bar(season, is_weekend, occ)
        price = PRICE_TABLE.get(room_id, {}).get(bar, 0)
    else:
        bar = type_code # 고정객실은 시즌코드를 표시
        price = FIXED_PRICE_TABLE.get(room_id, {}).get(type_code, 0)
    return occ, bar, price

# --- 4. 데이터 로드 및 저장 함수 ---
def get_snapshot_by_date(selected_date):
    date_str = selected_date.strftime("%Y-%m-%d")
    docs = db.collection("daily_snapshots").where("work_date", "==", date_str).limit(1).stream()
    for doc in docs:
        df = pd.DataFrame(doc.to_dict()['data'])
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df
    return pd.DataFrame()

# --- 5. 테이블 렌더러 (HTML/CSS) ---
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준"):
    dates = sorted(current_df['Date'].unique())
    # 판매가 모드일 때는 채널에서 선택한 객실만, 아니면 전체 10개 표시
    rooms_to_show = ALL_ROOMS if mode != "판매가" else st.session_state.promotions[ch_name]["selected_rooms"]
    
    html = f"<div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; padding:10px; background:#f0f2f6; border-left:10px solid #000;'>{title}</div>"
    html += "<table style='width:100%; border-collapse:collapse; font-family:sans-serif; font-size:11px;'><thead>"
    html += "<tr style='background:#f9f9f9;'><th rowspan='2' style='border:1px solid #ddd; width:150px;'>객실/프로모션</th>"
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th style='border:1px solid #ddd; padding:5px;' class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in rooms_to_show:
        label = rid
        if mode == "판매가":
            p_name = st.session_state.promotions[ch_name]["config"][rid]['name']
            label = f"<b>{rid}</b><br><small style='color:blue;'>{p_name}</small>"
        
        # 블록 구분선 (HDF 다음, PPV 다음 굵게)
        border_thick = "border-bottom:3px solid #000;" if rid in ["HDF", "PPV"] else ""
        html += f"<tr style='{border_thick}'><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000;'>{label}</td>"
        
        for d in dates:
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty and rid in DYNAMIC_ROOMS:
                html += "<td style='border:1px solid #ddd;'>-</td>"; continue
            
            # 가용데이터 없으면 만실 혹은 기본값 처리 (고정가 객실용)
            avail = curr_match.iloc[0]['Available'] if not curr_match.empty else 0
            total = curr_match.iloc[0]['Total'] if not curr_match.empty else 10
            
            occ, bar, base_price = get_final_values(rid, d, avail, total)
            style = "border:1px solid #ddd; padding:8px; text-align:center; background-color:white;"
            content = "-"

            prev_bar = None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                if not prev_m.empty: _, prev_bar, _ = get_final_values(rid, d, prev_m.iloc[0]['Available'], prev_m.iloc[0]['Total'])
            
            is_changed = prev_bar and prev_bar != bar

            if mode == "기준":
                content = f"<b>{bar}</b><br>{occ:.0f}%"
            elif mode == "변화":
                pickup = 0
                if not prev_df.empty:
                    prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                    if not prev_m.empty: pickup = prev_m.iloc[0]['Available'] - curr_row['Available'] if 'curr_row' in locals() else prev_m.iloc[0]['Available'] - avail
                content = f"+{pickup}" if pickup > 0 else (pickup if pickup < 0 else "-")
                if pickup > 0: style += "color:red; font-weight:bold; background:#FFEBEE;"
            elif mode == "판도변화":
                if is_changed:
                    bg = ALERT_BAR_COLORS.get(bar, "#7000FF") # BAR면 유채색, 아니면 보라색
                    text_c = "white" if bar in ["BAR1", "BAR2", "BAR5", "BAR6", "BAR7"] or "BAR" not in str(bar) else "black"
                    style += f"background-color: {bg}; color: {text_c}; font-weight: bold; border: 2.5px solid #000;"
                    content = f"▲ {bar}"
                else: content = bar
            elif mode == "판매가":
                conf = st.session_state.promotions[ch_name]["config"][rid]
                # (기준가 * 할인율) -> 1000원 단위 절삭 -> 추가금
                after_disc = base_price * (1 - (conf['discount_rate'] / 100))
                floored = math.floor(after_disc / 1000) * 1000
                final_p = int(floored + conf['add_price'])
                content = f"<b>{final_p:,}</b>"
                if is_changed:
                    bg = ALERT_BAR_COLORS.get(bar, "#7000FF")
                    text_c = "white" if bar in ["BAR1", "BAR2", "BAR5", "BAR6", "BAR7"] or "BAR" not in str(bar) else "black"
                    style += f"background-color: {bg}; color: {text_c}; font-weight: bold; border: 2.5px solid #333;"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 6. UI 및 메인 로직 ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 통합 수익관리 시스템")

if 'promotions' not in st.session_state:
    st.session_state.promotions = {}
if 'channel_list' not in st.session_state:
    st.session_state.channel_list = []

with st.sidebar:
    st.header("📅 데이터 관리")
    comp_date = st.date_input("비교할 과거 날짜 선택", value=date.today())
    if st.button("📂 과거 데이터 로드"):
        st.session_state.prev_df = get_snapshot_by_date(comp_date)
        if not st.session_state.prev_df.empty: st.success(f"{comp_date} 로드 완료!")
        else: st.warning("저장된 데이터가 없습니다.")
    
    st.divider()
    st.header("🎯 채널 관리")
    new_ch = st.text_input("새 채널 추가")
    if st.button("➕ 채널 추가"):
        if new_ch and new_ch not in st.session_state.channel_list:
            st.session_state.channel_list.append(new_ch)
            st.session_state.promotions[new_ch] = {
                "selected_rooms": ALL_ROOMS.copy(),
                "config": {rid: {"name": f"{new_ch}_{rid}", "discount_rate": 0, "add_price": 0} for rid in ALL_ROOMS}
            }
            st.rerun()

    for ch in st.session_state.channel_list:
        with st.expander(f"📦 {ch} 설정"):
            st.session_state.promotions[ch]["selected_rooms"] = [r for r in ALL_ROOMS if st.checkbox(r, value=r in st.session_state.promotions[ch]["selected_rooms"], key=f"sel_{ch}_{r}")]
            for rid in st.session_state.promotions[ch]["selected_rooms"]:
                st.markdown(f"**{rid} 설정**")
                st.session_state.promotions[ch]["config"][rid]['name'] = st.text_input("프로모션명", st.session_state.promotions[ch]["config"][rid]['name'], key=f"n_{ch}_{rid}")
                c1, c2 = st.columns(2)
                st.session_state.promotions[ch]["config"][rid]['discount_rate'] = c1.number_input("할인(%)", value=st.session_state.promotions[ch]["config"][rid]['discount_rate'], key=f"d_{ch}_{rid}")
                st.session_state.promotions[ch]["config"][rid]['add_price'] = c2.number_input("추가금", value=st.session_state.promotions[ch]["config"][rid]['add_price'], step=1000, key=f"a_{ch}_{rid}")

    st.divider()
    files = st.file_uploader("엑셀 업로드", accept_multiple_files=True)
    if st.button("🚀 오늘 스냅샷 저장"):
        if 'today_df' in st.session_state:
            save_df = st.session_state.today_df.copy()
            save_df['Date'] = save_df['Date'].apply(lambda x: x.isoformat())
            db.collection("daily_snapshots").add({
                "work_date": date.today().strftime("%Y-%m-%d"),
                "save_time": datetime.now(),
                "data": save_df.to_dict(orient='records')
            })
            st.success("오늘 데이터 저장 완료!")

# 데이터 처리
if files:
    all_temp = []
    for f in files:
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values
        for r_idx in [6, 7, 10, 11, 12]:
            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()
            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                if pd.isna(d_val) or pd.isna(av): continue
                try:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date() if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                    all_temp.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot})
                except: continue
    st.session_state.today_df = pd.DataFrame(all_temp)

# 메인 렌더링
if 'today_df' in st.session_state:
    curr = st.session_state.today_df
    prev = st.session_state.get('prev_df', pd.DataFrame())
    
    st.markdown(render_master_table(curr, prev, title="📊 1. 시장 분석 (전체 10종)", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="🔔 2. 판도 변화 (BAR 변경 알림)", mode="판도변화"), unsafe_allow_html=True)
    
    st.divider()
    for ch in st.session_state.channel_list:
        st.markdown(render_master_table(curr, prev, ch_name=ch, title=f"✅ {ch} 판매가", mode="판매가"), unsafe_allow_html=True)
