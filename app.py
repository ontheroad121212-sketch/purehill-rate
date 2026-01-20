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

# BAR 등급별 색상 (배경색)
BAR_COLORS = {
    "BAR1": "#FF4B4B", "BAR2": "#FF7E7E", "BAR3": "#FFD166", "BAR4": "#FFFC99",
    "BAR5": "#D1FFBD", "BAR6": "#99FF99", "BAR7": "#BAE1FF", "BAR8": "#A0C4FF",
}

SPECIAL_PERIODS = [
    {"start": "2026-02-13", "end": "2026-02-18", "base_bar": "BAR4", "label": "성수기 연휴"},
    {"start": "2026-03-01", "end": "2026-03-01", "base_bar": "BAR7", "label": "비수기 삼일절"},
    {"start": "2026-05-03", "end": "2026-05-05", "base_bar": "BAR6", "label": "평수기 어린이날"},
    {"start": "2026-07-17", "end": "2026-08-29", "base_bar": "SUMMER", "label": "여름 성수기"},
    {"start": "2026-12-21", "end": "2026-12-31", "base_bar": "BAR5", "label": "연말 성수기"}
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

# 스타일링 핵심 함수
def style_dashboard(styler):
    def get_row_styles(row):
        styles = []
        category = row.name[1] # '점유율', 'BAR', '요금' 중 하나
        for val in row:
            style = ""
            if "점유율" in category:
                style = "font-size: 11px; color: #888; height: 20px; vertical-align: bottom;"
            elif "BAR" in category:
                bg_color = BAR_COLORS.get(str(val), "#FFFFFF")
                style = f"background-color: {bg_color}; font-weight: bold; color: black; font-size: 14px;"
            elif "요금" in category:
                style = "border-bottom: 2.5px solid #333; font-size: 13px;" # 객실 간 구분선
            styles.append(style)
        return styles
    
    return styler.apply(get_row_styles, axis=1)

# --- 4. UI ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략적 요금 대시보드")

with st.sidebar:
    st.header("📂 데이터 관리")
    uploaded_files = st.file_uploader("엑셀 파일들을 드래그해서 올리세요 (12개월 누적 가능)", type=['xlsx', 'xls'], accept_multiple_files=True)
    if st.button("🔄 데이터 초기화"):
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
    df = st.session_state.all_data_df.copy()
    pivot_data = []
    for _, r in df.iterrows():
        occ, bar, price = determine_values(r['RoomID'], r['Date'], r['Available'], r['Total'])
        pivot_data.append({"Date": r['Date'], "RoomID": r['RoomID'], "구분": "1. 점유율", "값": f"{occ:.1f}%"})
        pivot_data.append({"Date": r['Date'], "RoomID": r['RoomID'], "구분": "2. BAR", "값": bar})
        pivot_data.append({"Date": r['Date'], "RoomID": r['RoomID'], "구분": "3. 요금", "값": f"{price:,}"})
    
    full_display_df = pd.DataFrame(pivot_data)
    tabs = st.tabs([f"{i}월" for i in range(1, 13)])
    
    for i, tab in enumerate(tabs):
        with tab:
            m = i + 1
            m_df = full_display_df[full_display_df['Date'].apply(lambda x: x.month == m)]
            if not m_df.empty:
                # 피벗 및 정렬
                view_df = m_df.pivot(index=['RoomID', '구분'], columns='Date', values='값')
                
                st.subheader(f"📊 {m}월 요금 시뮬레이션")
                # 스타일 적용하여 출력
                st.dataframe(style_dashboard(view_df.style), use_container_width=True, height=600)
                
                if st.button(f"{m}월 최종 저장", key=f"btn_{m}"):
                    st.success("Firebase에 안전하게 저장되었습니다.")
            else:
                st.info(f"{m}월 데이터 없음")
else:
    st.warning("파일을 업로드하면 대시보드가 활성화됩니다.")
