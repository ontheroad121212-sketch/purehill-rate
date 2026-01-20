import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib

# --- 1. 파이어베이스 연결 설정 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# --- 2. 상세 요금표 및 객실 설정 (업데이트 완료) ---
# 주말 가산금 설정 (필요 없으면 0으로 수정하세요)
WEEKEND_SURCHARGE = 50000 

PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

# 엑셀 A열의 텍스트와 위 ID를 매칭 (실제 엑셀 이름에 맞춰 수정하세요)
ROOM_MAPPING = {
    "패밀리 더블": "FDB",
    "패밀리 디럭스": "FDE",
    "한실 디럭스 펫": "HDP",
    "한실 디럭스 트윈": "HDT",
    "한실 디럭스 패밀리": "HDF"
}

# 객실별 전체 재고
ROOM_CONFIG = {
    "FDB": 32, "FDE": 20, "HDP": 10, "HDT": 15, "HDF": 12
}

# 특수 기간 설정
SPECIAL_PERIODS = [
    {"start": "2026-02-13", "end": "2026-02-18", "base_bar": "BAR4", "label": "성수기 연휴"},
    {"start": "2026-03-01", "end": "2026-03-01", "base_bar": "BAR7", "label": "비수기 삼일절"},
    {"start": "2026-05-03", "end": "2026-05-05", "base_bar": "BAR6", "label": "평수기 어린이날"},
    {"start": "2026-07-17", "end": "2026-08-29", "base_bar": "SUMMER", "label": "여름 성수기"},
    {"start": "2026-12-21", "end": "2026-12-31", "base_bar": "BAR5", "label": "연말 성수기"}
]

# --- 3. 로직 함수 ---
def get_bar_by_occ(occ):
    if occ >= 90: return "BAR1"
    elif occ >= 80: return "BAR2"
    elif occ >= 70: return "BAR3"
    elif occ >= 60: return "BAR4"
    elif occ >= 50: return "BAR5"
    elif occ >= 40: return "BAR6"
    elif occ >= 30: return "BAR7"
    else: return "BAR8"

def determine_price(room_id, date_obj, occ):
    is_weekend = date_obj.weekday() in [4, 5] # 금토
    
    # 1. BAR 결정
    final_bar = get_bar_by_occ(occ) # 기본은 점유율 기준
    label = "일반"
    
    for period in SPECIAL_PERIODS:
        start = datetime.strptime(period["start"], "%Y-%m-%d").date()
        end = datetime.strptime(period["end"], "%Y-%m-%d").date()
        if start <= date_obj <= end:
            if period["base_bar"] == "SUMMER":
                final_bar = "BAR4" if is_weekend else "BAR5"
            else:
                final_bar = period["base_bar"]
            label = period["label"]
            break
            
    # 2. 요금 추출
    base_price = PRICE_TABLE[room_id][final_bar]
    if is_weekend: base_price += WEEKEND_SURCHARGE # 주말 가산 적용
    
    return final_bar, base_price, label

def apply_color(val):
    if pd.isna(val) or val == 0: return ""
    color_hash = hashlib.md5(str(val).encode()).hexdigest()[:6]
    return f'background-color: #{color_hash}; color: black; font-weight: bold;'

def load_custom_excel(file):
    df_raw = pd.read_excel(file, header=None)
    dates_raw = df_raw.iloc[2, 2:].values
    target_rows = [6, 7, 10, 11, 12]
    
    all_data = []
    for row_idx in target_rows:
        room_display_name = df_raw.iloc[row_idx, 0]
        room_id = ROOM_MAPPING.get(room_display_name, "FDB")
        total_inv = ROOM_CONFIG.get(room_id, 30)
        avails = df_raw.iloc[row_idx, 2:].values
        
        for date, avail in zip(dates_raw, avails):
            if pd.isna(date) or pd.isna(avail): continue
            d_obj = pd.to_datetime('1899-12-30') + pd.to_timedelta(date, 'D') if isinstance(date, (int, float)) else pd.to_datetime(date)
            all_data.append({"Date": d_obj.date(), "RoomID": room_id, "RoomName": room_display_name, "Available": avail, "Total": total_inv})
    return pd.DataFrame(all_data)

# --- 4. Streamlit UI ---
st.set_page_config(layout="wide")
st.title("🏨 객실별 맞춤 BAR 요금 관리 시스템")

with st.sidebar:
    mode = st.radio("메뉴", ["요금 수정", "기록 조회"])
    uploaded_file = st.file_uploader("가용객실 엑셀 업로드", type=['xlsx', 'xls'])

tabs = st.tabs([f"{i}월" for i in range(1, 13)])

if mode == "요금 수정" and uploaded_file:
    df = load_custom_excel(uploaded_file)
    
    calc_results = []
    for _, row in df.iterrows():
        occ = ((row['Total'] - row['Available']) / row['Total'] * 100)
        bar, price, label = determine_price(row['RoomID'], row['Date'], occ)
        calc_results.append({"OCC": round(occ, 1), "BAR": bar, "Price": price, "Type": label})
    
    final_df = pd.concat([df, pd.DataFrame(calc_results)], axis=1)

    for i, tab in enumerate(tabs):
        with tab:
            m = i + 1
            m_df = final_df[final_df['Date'].apply(lambda x: x.month == m)]
            if not m_df.empty:
                # 피벗 테이블: 객실별 날짜별 요금 확인
                view_df = m_df.pivot(index='RoomName', columns='Date', values='Price')
                st.dataframe(view_df.style.applymap(apply_color), use_container_width=True)
                
                if st.button(f"{m}월 데이터 스냅샷 저장", key=f"btn_{m}"):
                    doc_id = datetime.now().strftime("%Y-%m-%d_%H%M")
                    db.collection("daily_snapshots").document(doc_id).set({
                        "work_date": datetime.now().strftime("%Y-%m-%d"),
                        "data": m_df.to_dict(orient='records'),
                        "month": m
                    })
                    st.success("Firebase 저장 완료!")
            else:
                st.info("해당 월 데이터 없음")
