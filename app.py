import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import hashlib

# --- 1. 파이어베이스 및 상태 초기화 ---
# 파이어베이스 연결 (최초 1회 실행)
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# 여러 파일을 누적해서 관리하기 위한 세션 상태 변수 설정
if 'all_data_df' not in st.session_state:
    st.session_state.all_data_df = pd.DataFrame()

# --- 2. 상세 요금표 설정 ---
# 객실별/BAR별 기본 요금 (평일 기준)
PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

# 2026년 특수 기간 및 공휴일 설정
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

# --- 3. 로직 함수 ---
def determine_price_and_occ(room_id, date_obj, avail, total):
    # 1. 점유율 계산
    occ = ((total - avail) / total * 100) if total > 0 else 0
    is_weekend = date_obj.weekday() in [4, 5] # 금, 토
    
    # 2. 기본 BAR 등급 결정 (점유율 기준)
    final_bar = "BAR8"
    if occ >= 90: final_bar = "BAR1"
    elif occ >= 80: final_bar = "BAR2"
    elif occ >= 70: final_bar = "BAR3"
    elif occ >= 60: final_bar = "BAR4"
    elif occ >= 50: final_bar = "BAR5"
    elif occ >= 40: final_bar = "BAR6"
    elif occ >= 30: final_bar = "BAR7"

    # 3. 특수 기간/성수기 덮어쓰기
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
            
    # 4. 최종 요금 추출 (PRICE_TABLE에 해당 객실이 없을 경우 대비)
    if room_id in PRICE_TABLE:
        price = PRICE_TABLE[room_id].get(final_bar, 0)
    else:
        price = 0
        
    # 표시용 텍스트 생성: BAR 번호 | 가격 (점유율%)
    display_text = f"{final_bar} | {price:,}원\n({occ:.1f}%)"
    return final_bar, price, occ, display_text, label

def load_custom_excel(file):
    # 엔진 자동 선택 (구버전 .xls 대응을 위해 xlrd 필요)
    df_raw = pd.read_excel(file, header=None)
    
    # 날짜 행 찾기 (3행 = index 2)
    dates_raw = df_raw.iloc[2, 2:].values
    # 객실 행 찾기 (7,8,11,12,13행 = index 6,7,10,11,12)
    target_row_indices = [6, 7, 10, 11, 12]
    
    all_data = []
    for row_idx in target_row_indices:
        if row_idx >= len(df_raw): continue
        
        room_id = str(df_raw.iloc[row_idx, 0]).strip().upper() # A열: 객실코드
        total_inv = pd.to_numeric(df_raw.iloc[row_idx, 1], errors='coerce') # B열: 전체객실수
        avails = df_raw.iloc[row_idx, 2:].values # C열부터: 날짜별 잔여객실
        
        for date_val, avail in zip(dates_raw, avails):
            if pd.isna(date_val) or pd.isna(avail): continue
            
            try:
                # 날짜가 '01-20' 형태일 경우 2026년으로 보정
                if isinstance(date_val, str):
                    d_obj = datetime.strptime(f"2026-{date_val}", "%Y-%m-%d").date()
                else:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(date_val, 'D')).date().replace(year=2026)
                
                all_data.append({
                    "Date": d_obj,
                    "RoomID": room_id,
                    "Available": pd.to_numeric(avail, errors='coerce'),
                    "Total": total_inv
                })
            except: continue
                
    return pd.DataFrame(all_data)

# --- 4. Streamlit UI ---
st.set_page_config(layout="wide", page_title="AmberPureHill Revenue")
st.title("🏨 엠버퓨어힐 요금/점유율 통합 관리 시스템")

with st.sidebar:
    st.header("📂 엑셀 데이터 업로드")
    uploaded_file = st.file_uploader("월별 파일을 하나씩 올려주세요 (누적 가능)", type=['xlsx', 'xls'])
    
    if st.button("🔄 전체 데이터 초기화"):
        st.session_state.all_data_df = pd.DataFrame()
        st.success("데이터가 초기화되었습니다.")
        st.rerun()
    
    st.info("파일을 올릴 때마다 기존 데이터에 추가됩니다. 중복 날짜는 최신 파일로 갱신됩니다.")

# 파일 업로드 시 세션 데이터에 추가
if uploaded_file:
    new_data = load_custom_excel(uploaded_file)
    if not st.session_state.all_data_df.empty:
        # 기존 데이터와 합치고 '날짜+객실ID' 기준으로 중복 제거 (마지막에 올린 파일 우선)
        combined = pd.concat([st.session_state.all_data_df, new_data])
        st.session_state.all_data_df = combined.drop_duplicates(subset=['Date', 'RoomID'], keep='last')
    else:
        st.session_state.all_data_df = new_data
    st.success(f"{uploaded_file.name} 반영 완료!")

# 데이터가 있을 경우 탭별 표시
if not st.session_state.all_data_df.empty:
    df_to_calc = st.session_state.all_data_df.copy()
    
    # 전체 행에 대해 요금 및 점유율 계산
    final_results = []
    for _, row in df_to_calc.iterrows():
        bar_id, price_val, occ_val, display_txt, label_txt = determine_price_and_occ(
            row['RoomID'], row['Date'], row['Available'], row['Total']
        )
        final_results.append({
            "BAR": bar_id, 
            "Price": price_val, 
            "OCC": occ_val, 
            "Display": display_txt, 
            "PeriodType": label_txt
        })
    
    # 원본 데이터와 계산 결과 합치기
    full_df = pd.concat([df_to_calc.reset_index(drop=True), pd.DataFrame(final_results)], axis=1)

    # 1월부터 12월까지 탭 생성
    tabs = st.tabs([f"{i}월" for i in range(1, 13)])
    
    for i, tab in enumerate(tabs):
        with tab:
            month_num = i + 1
            # 해당 월의 데이터만 필터링
            month_df = full_df[full_df['Date'].apply(lambda x: x.month == month_num)]
            
            if not month_df.empty:
                st.subheader(f"📊 {month_num}월 요금 대시보드 (BAR | 요금 | 점유율)")
                
                # 피벗 테이블 생성 (행: 객실, 열: 날짜, 값: 표시 텍스트)
                # 날짜순 정렬을 위해 피벗 전에 정렬
                month_df = month_df.sort_values(by='Date')
                pivot_df = month_df.pivot(index='RoomID', columns='Date', values='Display')
                
                # 데이터프레임 출력
                st.dataframe(pivot_df, use_container_width=True)
                
                # Firebase 저장 버튼
                if st.button(f"💾 {month_num}월 데이터 최종 저장 (Firebase)", key=f"save_btn_{month_num}"):
                    doc_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                    db.collection("daily_snapshots").document(doc_id).set({
                        "save_time": datetime.now().isoformat(),
                        "month": month_num,
                        "data": month_df.to_dict(orient='records')
                    })
                    st.success(f"{month_num}월 데이터가 파이어베이스에 기록되었습니다.")
            else:
                st.info(f"{month_num}월 데이터가 없습니다. 파일을 업로드해 주세요.")

else:
    st.warning("데이터가 없습니다. 사이드바에서 엑셀 파일을 업로드해 주세요.")

# --- 5. 과거 기록 조회 모드 (별도 섹션) ---
st.divider()
st.subheader("🔍 과거 저장 기록 조회")
with st.expander("이전 저장 내역 확인하기"):
    search_date = st.date_input("기록을 찾을 날짜 선택", datetime.now())
    if st.button("조회하기"):
        # 해당 날짜에 저장된 모든 스냅샷 쿼리 (work_date 기준이 아니라 저장 시점 날짜 기준)
        date_str = search_date.strftime("%Y-%m-%d")
        docs = db.collection("daily_snapshots").stream()
        
        found = False
        for doc in docs:
            d = doc.to_dict()
            if d.get('save_time', '').startswith(date_str):
                found = True
                st.write(f"📌 저장 시각: {doc.id} ({d.get('month')}월분 데이터)")
                hist_df = pd.DataFrame(d['data'])
                hist_pivot = hist_df.pivot(index='RoomID', columns='Date', values='Display')
                st.dataframe(hist_pivot, use_container_width=True)
        
        if not found:
            st.info("해당 날짜에 저장된 기록이 없습니다.")
