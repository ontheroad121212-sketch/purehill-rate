import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 파이어베이스 및 상태 초기화 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

if 'all_data_df' not in st.session_state:
    st.session_state.all_data_df = pd.DataFrame()

# --- 2. 설정 데이터 ---
PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

BAR_COLORS = {
    "BAR1": "#FF4B4B", "BAR2": "#FF7E7E", "BAR3": "#FFD166", "BAR4": "#FFFC99",
    "BAR5": "#D1FFBD", "BAR6": "#99FF99", "BAR7": "#BAE1FF", "BAR8": "#A0C4FF",
}

SPECIAL_PERIODS = [
    {"start": "2026-02-13", "end": "2026-02-18", "base_bar": "BAR4"},
    {"start": "2026-03-01", "end": "2026-03-01", "base_bar": "BAR7"},
    {"start": "2026-05-03", "end": "2026-05-05", "base_bar": "BAR6"},
    {"start": "2026-07-17", "end": "2026-08-29", "base_bar": "SUMMER"},
    {"start": "2026-12-21", "end": "2026-12-31", "base_bar": "BAR5"}
]

# --- 3. 로직 함수 ---
def determine_values(room_id, date_obj, avail, total):
    occ = ((total - avail) / total * 100) if total > 0 else 0
    is_weekend = date_obj.weekday() in [4, 5]
    final_bar = "BAR8"
    if occ >= 90: final_bar = "BAR1"
    elif occ >= 80: final_bar = "BAR2"
    elif occ >= 70: final_bar = "BAR3"
    elif occ >= 60: final_bar = "BAR4"
    elif occ >= 50: final_bar = "BAR5"
    elif occ >= 40: final_bar = "BAR6"
    elif occ >= 30: final_bar = "BAR7"

    for period in SPECIAL_PERIODS:
        start = datetime.strptime(period["start"], "%Y-%m-%d").date()
        end = datetime.strptime(period["end"], "%Y-%m-%d").date()
        if start <= date_obj <= end:
            if period["base_bar"] == "SUMMER":
                final_bar = "BAR4" if is_weekend else "BAR5"
            else:
                final_bar = period["base_bar"]
            break
    price = PRICE_TABLE.get(room_id, {}).get(final_bar, 0)
    return occ, final_bar, price

def load_custom_excel(file):
    df_raw = pd.read_excel(file, header=None)
    dates_raw = df_raw.iloc[2, 2:].values
    target_row_indices = [6, 7, 10, 11, 12]
    all_data = []
    for row_idx in target_row_indices:
        if row_idx >= len(df_raw): continue
        room_id = str(df_raw.iloc[row_idx, 0]).strip().upper()
        total_inv = pd.to_numeric(df_raw.iloc[row_idx, 1], errors='coerce')
        avails = df_raw.iloc[row_idx, 2:].values
        for d_val, av in zip(dates_raw, avails):
            if pd.isna(d_val) or pd.isna(av): continue
            try:
                if isinstance(d_val, str): d_obj = datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                else: d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date().replace(year=2026)
                all_data.append({"Date": d_obj, "RoomID": room_id, "Available": pd.to_numeric(av, errors='coerce'), "Total": total_inv})
            except: continue
    return pd.DataFrame(all_data)

# ⭐ HTML/CSS 기반의 커스텀 병합 테이블 생성 함수
def render_custom_table(m_df):
    room_ids = ["FDB", "FDE", "HDP", "HDT", "HDF"]
    dates = sorted(m_df['Date'].unique())
    
    html = """
    <style>
        .hotel-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px; }
        .hotel-table th, .hotel-table td { border: 1px solid #ddd; text-align: center; padding: 4px; }
        .hotel-table th { background-color: #f4f4f4; position: sticky; top: 0; }
        .room-id-cell { font-weight: bold; background-color: #ffffff; width: 80px; border-right: 2px solid #333 !important; }
        .occ-row { font-size: 10px; color: #888; height: 15px; }
        .bar-row { font-weight: bold; font-size: 14px; }
        .price-row { border-bottom: 1px solid #000 !important; } /* 객실 사이 굵은 줄 */
    </style>
    <table class='hotel-table'>
        <thead>
            <tr>
                <th>Room ID</th>
                <th>구분</th>
    """
    for d in dates:
        html += f"<th>{d.strftime('%m-%d')}</th>"
    html += "</tr></thead><tbody>"

    for rid in room_ids:
        # 각 RoomID당 3행 (점유율, BAR, 요금)
        for i, category in enumerate(["점유율", "BAR", "요금"]):
            row_class = "occ-row" if i==0 else ("bar-row" if i==1 else "price-row")
            html += f"<tr class='{row_class}'>"
            
            # 첫 번째 행에서만 RoomID를 병합(rowspan=3)해서 출력
            if i == 0:
                html += f"<td rowspan='3' class='room-id-cell'>{rid}</td>"
            
            html += f"<td style='background-color:#fafafa;'>{category}</td>"
            
            for d in dates:
                match = m_df[(m_df['RoomID'] == rid) & (m_df['Date'] == d)]
                if not match.empty:
                    occ, bar, price = determine_values(rid, d, match.iloc[0]['Available'], match.iloc[0]['Total'])
                    if i == 0: val = f"{occ:.1f}%"
                    elif i == 1: 
                        bg = BAR_COLORS.get(bar, "#fff")
                        val = f"<div style='background-color:{bg}; padding:1px;'>{bar}</div>"
                    else: val = f"{price:,}"
                    html += f"<td>{val}</td>"
                else:
                    html += "<td>-</td>"
            html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 4. UI ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 프리미엄 요금 대시보드")

with st.sidebar:
    uploaded_files = st.file_uploader("파일 업로드 (여러 개 가능)", type=['xlsx', 'xls'], accept_multiple_files=True)
    if st.button("🔄 초기화"):
        st.session_state.all_data_df = pd.DataFrame()
        st.rerun()

if uploaded_files:
    for f in uploaded_files:
        new_df = load_custom_excel(f)
        if not st.session_state.all_data_df.empty:
            combined = pd.concat([st.session_state.all_data_df, new_df])
            st.session_state.all_data_df = combined.drop_duplicates(subset=['Date', 'RoomID'], keep='last')
        else:
            st.session_state.all_data_df = new_df

if not st.session_state.all_data_df.empty:
    tabs = st.tabs([f"{i}월" for i in range(1, 13)])
    for i, tab in enumerate(tabs):
        with tab:
            m = i + 1
            month_df = st.session_state.all_data_df[st.session_state.all_data_df['Date'].apply(lambda x: x.month == m)]
            if not month_df.empty:
                # 커스텀 HTML 테이블 렌더링
                st.markdown(render_custom_table(month_df), unsafe_allow_html=True)
            else:
                st.info(f"{m}월 데이터 없음")
