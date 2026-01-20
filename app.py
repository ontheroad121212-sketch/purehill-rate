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

# --- 2. 호텔 요금 및 규칙 설정 ---
ROOM_CONFIG = {"FDB": {"total": 32}, "DBL": {"total": 20}}

# 특수 기간 리스트 (성수기/연휴)
SPECIAL_PERIODS = [
    {"start": "2026-02-13", "end": "2026-02-18", "base_bar": "BAR 4", "label": "성수기 연휴"},
    {"start": "2026-03-01", "end": "2026-03-01", "base_bar": "BAR 7", "label": "비수기 삼일절"},
    {"start": "2026-05-03", "end": "2026-05-05", "base_bar": "BAR 6", "label": "평수기 어린이날"},
    {"start": "2026-05-24", "end": "2026-05-26", "base_bar": "BAR 6", "label": "평수기 석가탄신일"},
    {"start": "2026-06-05", "end": "2026-06-07", "base_bar": "BAR 6", "label": "평수기 현충일"},
    {"start": "2026-07-17", "end": "2026-08-29", "base_bar": "SUMMER", "label": "여름 성수기"},
    {"start": "2026-09-23", "end": "2026-09-28", "base_bar": "BAR 4", "label": "추석 연휴"},
    {"start": "2026-10-01", "end": "2026-10-08", "base_bar": "BAR 5", "label": "10월 성수기"},
    {"start": "2026-12-21", "end": "2026-12-31", "base_bar": "BAR 5", "label": "연말 성수기"}
]

# 요금표 (실제 금액으로 수정 필요)
PRICE_TABLE = {
    "BAR 1": {"WD": 300000, "WE": 350000},
    "BAR 2": {"WD": 280000, "WE": 330000},
    "BAR 3": {"WD": 260000, "WE": 310000},
    "BAR 4": {"WD": 240000, "WE": 290000},
    "BAR 5": {"WD": 220000, "WE": 270000},
    "BAR 6": {"WD": 200000, "WE": 250000},
    "BAR 7": {"WD": 180000, "WE": 230000},
    "BAR 8": {"WD": 160000, "WE": 210000},
}

# --- 3. 핵심 로직 함수 ---
def get_bar_by_occ(occ):
    if occ >= 90: return "BAR 1"
    elif occ >= 80: return "BAR 2"
    elif occ >= 70: return "BAR 3"
    elif occ >= 60: return "BAR 4"
    elif occ >= 50: return "BAR 5"
    elif occ >= 40: return "BAR 6"
    elif occ >= 30: return "BAR 7"
    else: return "BAR 8"

def determine_bar_and_price(date_obj, occ):
    is_weekend = date_obj.weekday() in [4, 5] # 금(4), 토(5)
    day_type = "WE" if is_weekend else "WD"
    
    # 1순위: 특수 기간 체크
    for period in SPECIAL_PERIODS:
        start = datetime.strptime(period["start"], "%Y-%m-%d").date()
        end = datetime.strptime(period["end"], "%Y-%m-%d").date()
        if start <= date_obj <= end:
            if period["base_bar"] == "SUMMER":
                final_bar = "BAR 4" if is_weekend else "BAR 5"
            else:
                final_bar = period["base_bar"]
            return final_bar, PRICE_TABLE[final_bar][day_type], period["label"]
            
    # 2순위: 일반 점유율 체크
    final_bar = get_bar_by_occ(occ)
    return final_bar, PRICE_TABLE[final_bar][day_type], "일반"

def apply_color(val):
    if pd.isna(val) or val == 0: return ""
    # 금액별 고유 색상 생성 (해시 활용)
    color_hash = hashlib.md5(str(val).encode()).hexdigest()[:6]
    return f'background-color: #{color_hash}; color: black; font-weight: bold;'

# --- 4. Streamlit UI ---
st.set_page_config(layout="wide", page_title="Hotel Revenue Master")
st.title("🏨 호텔 동적 요금 관리 & 히스토리 시스템")

with st.sidebar:
    st.header("📍 메뉴")
    mode = st.radio("작업 선택", ["요금 수정 (엑셀 업로드)", "과거 내역 조회"])
    uploaded_file = st.file_uploader("재고 현황 파일(.xlsx)", type=['xlsx'])

if mode == "요금 수정 (엑셀 업로드)" and uploaded_file:
    # 데이터 로드 (날짜 컬럼이 'Date', 잔여객실이 'Available'이라고 가정)
    df = pd.read_excel(uploaded_file)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    
    # 계산 적용
    results = []
    for _, row in df.iterrows():
        occ = ((ROOM_CONFIG["FDB"]["total"] - row['Available']) / ROOM_CONFIG["FDB"]["total"] * 100)
        bar, price, label = determine_bar_and_price(row['Date'], occ)
        results.append({"OCC": round(occ, 1), "BAR": bar, "Price": price, "Type": label})
    
    res_df = pd.concat([df, pd.DataFrame(results)], axis=1)
    
    st.subheader("📊 오늘의 자동 요금 제안")
    st.dataframe(res_df.style.applymap(apply_color, subset=['Price']))
    
    if st.button("💾 현재 대시보드 스냅샷 저장 (Firebase)"):
        doc_id = datetime.now().strftime("%Y-%m-%d_%H%M")
        db.collection("daily_snapshots").document(doc_id).set({
            "work_date": datetime.now().strftime("%Y-%m-%d"),
            "data": res_df.to_dict(orient='records')
        })
        st.success(f"{doc_id} 기록이 성공적으로 저장되었습니다.")

elif mode == "과거 내역 조회":
    search_date = st.date_input("조회하고 싶은 날짜를 선택하세요")
    docs = db.collection("daily_snapshots").where("work_date", "==", search_date.strftime("%Y-%m-%d")).stream()
    
    found = False
    for doc in docs:
        found = True
        st.write(f"🕒 저장 시각: {doc.id}")
        hist_df = pd.DataFrame(doc.to_dict()['data'])
        st.dataframe(hist_df.style.applymap(apply_color, subset=['Price']))
    
    if not found:
        st.warning("해당 날짜에 저장된 기록이 없습니다.")
