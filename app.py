import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# --- 1. 파이어베이스 연결 (보안 설정) ---
if not firebase_admin._apps:
    # 깃허브 배포 시에는 st.secrets를 사용하고, 로컬 테스트 시에는 json 파일을 사용하도록 설정
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    except:
        # 스트림릿 클라우드 배포용 세팅
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)

db = firestore.client()

# 특수 기간 설정 (시작일, 종료일, 기준 BAR)
SPECIAL_PERIODS = [
    {"start": "2026-02-13", "end": "2026-02-18", "base_bar": "BAR 4", "label": "성수기 연휴"},
    {"start": "2026-03-01", "end": "2026-03-01", "base_bar": "BAR 7", "label": "삼일절"},
    {"start": "2026-05-03", "end": "2026-05-05", "base_bar": "BAR 6", "label": "어린이날 연휴"},
    {"start": "2026-05-24", "end": "2026-05-26", "base_bar": "BAR 6", "label": "석가탄신일 연휴"},
    {"start": "2026-06-05", "end": "2026-06-07", "base_bar": "BAR 6", "label": "현충일 연휴"},
    {"start": "2026-07-17", "end": "2026-08-29", "base_bar": "PEAK", "label": "여름 성수기"}, # 주중/주말 별도 처리
    {"start": "2026-09-23", "end": "2026-09-28", "base_bar": "BAR 4", "label": "추석 연휴"},
    {"start": "2026-10-01", "end": "2026-10-08", "base_bar": "BAR 5", "label": "10월 황금연휴"},
    {"start": "2026-12-21", "end": "2026-12-31", "base_bar": "BAR 5", "label": "연말 성수기"}
]

# --- 2. 설정 데이터 (이 부분을 본인 호텔 수치에 맞게 수정하세요) ---
ROOM_CONFIG = {
    "FDB": {"total": 32},
    "DBL": {"total": 20}
}

# BAR 요금표 (예시: 실제 데이터로 교체 가능)
PRICE_TABLE = {
    "BAR 1": 300000, "BAR 2": 280000, "BAR 3": 260000, "BAR 4": 240000,
    "BAR 5": 220000, "BAR 6": 200000, "BAR 7": 180000, "BAR 8": 160000
}

# --- 3. 로직 함수 ---
def get_bar_level(occ):
    if occ >= 90: return "BAR 1"
    elif occ >= 80: return "BAR 2"
    elif occ >= 70: return "BAR 3"
    elif occ >= 60: return "BAR 4"
    elif occ >= 50: return "BAR 5"
    elif occ >= 40: return "BAR 6"
    elif occ >= 30: return "BAR 7"
    else: return "BAR 8"

def apply_color(val):
    # 같은 요금에 같은 색을 입히는 함수
    colors = {
        300000: 'background-color: #FFCDD2', # BAR 1
        280000: 'background-color: #F8BBD0', # BAR 2
        # ... 요금별 색상 지정
    }
    return colors.get(val, '')

# --- 4. 대시보드 UI ---
st.set_page_config(layout="wide")
st.title("🏨 호텔 동적 요금 관리 시스템")

# 월별 탭 생성
tabs = st.tabs([f"{i}월" for i in range(1, 13)])

with st.sidebar:
    st.header("⚙️ 컨트롤 패널")
    mode = st.radio("작업 모드", ["오늘의 수정", "과거 기록 조회"])
    
    if mode == "오늘의 수정":
        uploaded_file = st.file_uploader("재고 현황 엑셀 업로드", type=['xlsx'])
    else:
        target_date = st.date_input("조회할 날짜 선택", datetime.now())

# --- 5. 메인 로직 실행 ---
if mode == "오늘의 수정" and uploaded_file:
    df = pd.read_excel(uploaded_file)
    
    # 점유율 및 BAR 계산
    df['OCC'] = ((ROOM_CONFIG["FDB"]["total"] - df['Available']) / ROOM_CONFIG["FDB"]["total"] * 100).round(1)
    df['BAR'] = df['OCC'].apply(get_bar_level)
    df['Final_Price'] = df['BAR'].map(PRICE_TABLE)
    
    # 색상 적용 및 출력
    st.subheader("📊 실시간 계산 결과")
    st.dataframe(df.style.applymap(apply_color, subset=['Final_Price']))
    
    if st.button("현재 상태 Firebase에 스냅샷 저장"):
        doc_id = datetime.now().strftime("%Y-%m-%d_%H%M")
        db.collection("daily_snapshots").document(doc_id).set({
            "work_date": datetime.now().strftime("%Y-%m-%d"),
            "data": df.to_dict(orient='records')
        })
        st.success(f"저장 완료! (ID: {doc_id})")

elif mode == "과거 기록 조회":
    search_date = target_date.strftime("%Y-%m-%d")
    docs = db.collection("daily_snapshots").where("work_date", "==", search_date).stream()
    
    for doc in docs:
        st.write(f"🕒 기록 시각: {doc.id}")
        hist_df = pd.DataFrame(doc.to_dict()['data'])
        st.dataframe(hist_df.style.applymap(apply_color, subset=['Final_Price']))
