import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 파이어베이스 연결 ---
if not firebase_admin._apps:
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

# --- 2. 호텔 설정 (이 값을 실제 규칙으로 수정하세요) ---
ROOM_INFO = {
    "FDB": {"total": 32},
    "DBL": {"total": 20}
}

# BAR별 요금표 (평일/주말 구분)
RATE_TABLE = {
    "FDB": {
        "BAR 1": {"WD": 300000, "WE": 350000},
        "BAR 2": {"WD": 280000, "WE": 330000},
        # ... BAR 8까지 입력
    }
}

# --- 3. 핵심 함수 ---
def determine_final_rate(stay_date, occ):
    # 1. 특수 기간인지 먼저 확인
    for period in SPECIAL_PERIODS:
        start = datetime.strptime(period["start"], "%Y-%m-%d").date()
        end = datetime.strptime(period["end"], "%Y-%m-%d").date()
        
        if start <= stay_date <= end:
            # 여름 성수기 등 주중/주말 구분이 필요한 특수 케이스
            if period["label"] == "여름 성수기":
                return "BAR 4" if stay_date.weekday() >= 4 else "BAR 5"
            return period["base_bar"]

    # 2. 특수 기간이 아니면 점유율 로직 적용
    return get_bar_by_occ(occ)

def get_bar(occ):
    if occ >= 90: return "BAR 1"
    elif occ >= 80: return "BAR 2"
    # ... 규칙대로 추가
    else: return "BAR 8"

def apply_price_color(val):
    # 같은 가격은 같은 색으로! (해시 기반 자동 생성)
    import hashlib
    if pd.isna(val) or val == 0: return ""
    color_hash = hashlib.md5(str(val).encode()).hexdigest()[:6]
    return f'background-color: #{color_hash}; color: black;'

# --- 4. 대시보드 화면 ---
st.set_page_config(layout="wide", page_title="호텔 요금 관리 시스템")
st.title("🏨 객실 점유율 기반 동적 요금 대시보드")

with st.sidebar:
    menu = st.radio("메뉴", ["요금 수정 작업", "과거 기록 조회"])
    uploaded_file = st.file_uploader("월간 재고 현황 업로드", type=['xlsx'])

if menu == "요금 수정 작업" and uploaded_file:
    # 엑셀 데이터 로드 (월별 탭 처리 가능)
    df = pd.read_excel(uploaded_file)
    
    # 1. 점유율 및 BAR 자동 계산
    df['OCC'] = ((ROOM_INFO["FDB"]["total"] - df['Available']) / ROOM_INFO["FDB"]["total"] * 100).round(1)
    df['BAR'] = df['OCC'].apply(get_bar)
    
    # 2. 요일 확인 및 요금 매칭
    # 날짜 컬럼을 기준으로 평일(WD)/주말(WE) 구분 로직 추가 필요
    df['Final_Price'] = df.apply(lambda row: RATE_TABLE["FDB"][row['BAR']]["WD"], axis=1)

    # 3. 화면 출력 (색상 자동화)
    st.subheader("📊 오늘의 요금 제안")
    st.dataframe(df.style.applymap(apply_price_color, subset=['Final_Price']))

    # 4. 저장 버튼
    if st.button("현재 대시보드 스냅샷 저장"):
        doc_id = datetime.now().strftime("%Y-%m-%d_%H%M")
        db.collection("daily_snapshots").document(doc_id).set({
            "work_date": datetime.now().strftime("%Y-%m-%d"),
            "data": df.to_dict(orient='records')
        })
        st.success("파이어베이스에 기록되었습니다!")

elif menu == "과거 기록 조회":
    target_date = st.date_input("조회 날짜 선택")
    # 파이어베이스 쿼리 및 결과 출력 로직 (생략)
