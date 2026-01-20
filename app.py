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

# 데이터 누적을 위한 세션 상태 유지 (파일 여러 개 업로드용)
if 'all_data_df' not in st.session_state:
    st.session_state.all_data_df = pd.DataFrame()

# --- 2. 상세 요금표 및 객실 설정 ---
PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

# 2026년 특수 기간 설정
SPECIAL_PERIODS = [
    {"start": "2026-02-13", "end": "2026-02-18", "base_bar": "BAR4", "label": "성수기 연휴"},
    {"start": "2026-03-01", "end": "2026-03-01", "base_bar": "BAR7", "label": "비수기 삼일절"},
    {"start": "2026-05-03", "end": "2026-05-05", "base_bar": "BAR6", "label": "평수기 어린이날"},
    {"start": "2026-05-24", "end": "2026-05-26", "base_bar": "BAR6", "label": "평수기 석가탄신일"},
    {"start": "2026-06-05", "end": "2026-06-07", "base_bar": "BAR6", "label": "평수기 현충일"},
    {"start": "2026-07-17", "end": "2026-08-29", "base_bar": "SUMMER", "label": "여름 성수기"},
    {"start": "2026-09-23", "end": "2026-09-28", "base_bar": "BAR4", "label": "추석 연휴"},
    {"start": "2026-10-01", "end": "2026-10-08", "base_bar": "BAR5", "label": "10월 성수기"},
    {"start": "2026-12-21", "end": "2026-12-31", "base_bar": "BAR5", "label": "연말 성수기"}
]

# --- 3. 핵심 로직 함수 ---
def determine_values(room_id, date_obj, avail, total):
    # 1. 점유율 계산
    occ = ((total - avail) / total * 100) if total > 0 else 0
    is_weekend = date_obj.weekday() in [4, 5] # 금토
    
    # 2. BAR 등급 결정 (점유율 기준)
    final_bar = "BAR8"
    if occ >= 90: final_bar = "BAR1"
    elif occ >= 80: final_bar = "BAR2"
    elif occ >= 70: final_bar = "BAR3"
    elif occ >= 60: final_bar = "BAR4"
    elif occ >= 50: final_bar = "BAR5"
    elif occ >= 40: final_bar = "BAR6"
    elif occ >= 30: final_bar = "BAR7"

    # 3. 특수 기간 덮어쓰기
    for period in SPECIAL_PERIODS:
        start = datetime.strptime(period["start"], "%Y-%m-%d").date()
        end = datetime.strptime(period["end"], "%Y-%m-%d").date()
        if start <= date_obj <= end:
            if period["base_bar"] == "SUMMER":
                final_bar = "BAR4" if is_weekend else "BAR5"
            else:
                final_bar = period["base_bar"]
            break
            
    # 4. 요금 추출
    price = PRICE_TABLE.get(room_id, {}).get(final_bar, 0)
    
    # 각각의 값 반환 (문자열 형식)
    return f"{occ:.1f}%", final_bar, f"{price:,}"

def load_custom_excel(file):
    df_raw = pd.read_excel(file, header=None)
    # 3행 날짜(index 2), 7,8,11,12,13행 객실(index 6,7,10,11,12)
    dates_raw = df_raw.iloc[2, 2:].values
    target_row_indices = [6, 7, 10, 11, 12]
    
    all_data = []
    for row_idx in target_row_indices:
        if row_idx >= len(df_raw): continue
        room_id = str(df_raw.iloc[row_idx, 0]).strip().upper()
        total_inv = pd.to_numeric(df_raw.iloc[row_idx, 1], errors='coerce')
        avails = df_raw.iloc[row_idx, 2:].values
        
        for date_val, avail in zip(dates_raw, avails):
            if pd.isna(date_val) or pd.isna(avail): continue
            try:
                if isinstance(date_val, str):
                    d_obj = datetime.strptime(f"2026-{date_val}", "%Y-%m-%d").date()
                else:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(date_val, 'D')).date().replace(year=2026)
                all_data.append({"Date": d_obj, "RoomID": room_id, "Available": pd.to_numeric(avail, errors='coerce'), "Total": total_inv})
            except: continue
    return pd.DataFrame(all_data)

# --- 4. Streamlit UI ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 반자동 원클릭 요금 관리 시스템")

with st.sidebar:
    st.header("📂 엑셀 파일 업로드")
    # 멀티 파일 업로드 허용
    uploaded_files = st.file_uploader("12개월 파일을 한꺼번에 드래그하거나 하나씩 올리세요", type=['xlsx', 'xls'], accept_multiple_files=True)
    if st.button("🔄 모든 데이터 초기화"):
        st.session_state.all_data_df = pd.DataFrame()
        st.rerun()

# 업로드된 파일들을 누적 처리
if uploaded_files:
    for f in uploaded_files:
        new_df = load_custom_excel(f)
        if not st.session_state.all_data_df.empty:
            combined = pd.concat([st.session_state.all_data_df, new_df])
            st.session_state.all_data_df = combined.drop_duplicates(subset=['Date', 'RoomID'], keep='last')
        else:
            st.session_state.all_data_df = new_df

# 데이터가 존재할 경우 탭별 표시
if not st.session_state.all_data_df.empty:
    df = st.session_state.all_data_df.copy()
    
    # 복사를 위해 한 객실당 3행(점유율, BAR, 요금) 구조로 변환
    rows_for_pivot = []
    for _, row in df.iterrows():
        occ_val, bar_val, price_val = determine_values(row['RoomID'], row['Date'], row['Available'], row['Total'])
        
        # 날짜/객실별로 3개의 행 생성
        rows_for_pivot.append({"Date": row['Date'], "RoomID": row['RoomID'], "항목": "1.점유율", "데이터": occ_val})
        rows_for_pivot.append({"Date": row['Date'], "RoomID": row['RoomID'], "항목": "2.BAR", "데이터": bar_val})
        rows_for_pivot.append({"Date": row['Date'], "RoomID": row['RoomID'], "항목": "3.요금", "데이터": price_val})
    
    final_display_df = pd.DataFrame(rows_for_pivot)

    # 1월~12월 탭 생성
    tabs = st.tabs([f"{i}월" for i in range(1, 13)])
    for i, tab in enumerate(tabs):
        with tab:
            m = i + 1
            m_df = final_display_df[final_display_df['Date'].apply(lambda x: x.month == m)]
            
            if not m_df.empty:
                # 피벗: 인덱스를 [객실ID, 항목]으로 설정하여 3행 구조 구현
                pivot_table = m_df.pivot(index=['RoomID', '항목'], columns='Date', values='데이터')
                st.subheader(f"📊 {m}월 요금 대시보드 (복사용 3행 구조)")
                st.dataframe(pivot_table, use_container_width=True)
                
                if st.button(f"{m}월 데이터 저장", key=f"save_{m}"):
                    doc_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                    db.collection("daily_snapshots").document(doc_id).set({
                        "month": m,
                        "save_time": datetime.now().isoformat(),
                        "data": m_df.to_dict(orient='records')
                    })
                    st.success(f"{m}월 데이터가 저장되었습니다.")
            else:
                st.info(f"{m}월 데이터를 업로드해 주세요.")
else:
    st.warning("왼쪽 사이드바에서 파일을 업로드해 주세요.")
