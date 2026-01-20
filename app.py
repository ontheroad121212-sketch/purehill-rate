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

# --- 2. 상세 요금표 및 객실 설정 ---
PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

# 2026년 특수 기간 설정 (주말 금, 토 기준)
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
    is_weekend = date_obj.weekday() in [4, 5] # 금, 토
    final_bar = get_bar_by_occ(occ)
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
            
    base_price = PRICE_TABLE[room_id][final_bar]
    return final_bar, base_price, label

def apply_color(val):
    if pd.isna(val) or val == 0: return ""
    color_hash = hashlib.md5(str(val).encode()).hexdigest()[:6]
    return f'background-color: #{color_hash}; color: black; font-weight: bold;'

# --- 엑셀 로드 함수 (정밀 타격 버전) ---
def load_custom_excel(file):
    df_raw = pd.read_excel(file, header=None)
    
    # 3행(index 2)의 C열(index 2)부터 날짜 데이터 추출
    dates_raw = df_raw.iloc[2, 2:].values
    
    # 7, 8, 11, 12, 13행 (index 6, 7, 10, 11, 12)
    target_row_indices = [6, 7, 10, 11, 12]
    
    all_data = []
    for row_idx in target_row_indices:
        if row_idx >= len(df_raw): continue
        
        room_id = str(df_raw.iloc[row_idx, 0]).strip() # A열: 영문 코드
        total_inv = pd.to_numeric(df_raw.iloc[row_idx, 1], errors='coerce') # B열: 객실수
        avails = df_raw.iloc[row_idx, 2:].values # C열부터 잔여량
        
        for date_val, avail in zip(dates_raw, avails):
            if pd.isna(date_val) or pd.isna(avail): continue
            
            try:
                # 날짜 처리 (01-20 -> 2026-01-20 강제 변환)
                if isinstance(date_val, str) and '-' in date_val:
                    d_obj = datetime.strptime(f"2026-{date_val}", "%Y-%m-%d").date()
                elif isinstance(date_val, (datetime, pd.Timestamp)):
                    d_obj = date_val.date().replace(year=2026)
                else:
                    # 엑셀 숫자 형식일 경우
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
st.set_page_config(layout="wide")
st.title("🏨 호텔 요금 관리 마스터 (2026)")

with st.sidebar:
    mode = st.radio("작업 선택", ["요금 수정", "과거 기록 조회"])
    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=['xlsx', 'xls'])

tabs = st.tabs([f"{i}월" for i in range(1, 13)])

if mode == "요금 수정" and uploaded_file:
    df = load_custom_excel(uploaded_file)
    
    if not df.empty:
        calc_results = []
        for _, row in df.iterrows():
            # 점유율 계산: (전체 - 잔여) / 전체 * 100
            occ = ((row['Total'] - row['Available']) / row['Total'] * 100) if row['Total'] > 0 else 0
            bar, price, label = determine_price(row['RoomID'], row['Date'], occ)
            calc_results.append({"OCC": round(occ, 1), "BAR": bar, "Price": price, "Type": label})
        
        final_df = pd.concat([df, pd.DataFrame(calc_results)], axis=1)

        for i, tab in enumerate(tabs):
            with tab:
                m = i + 1
                m_df = final_df[final_df['Date'].apply(lambda x: x.month == m)]
                if not m_df.empty:
                    view_df = m_df.pivot(index='RoomID', columns='Date', values='Price')
                    st.subheader(f"📊 {m}월 요금 제안 (단위: 원)")
                    st.dataframe(view_df.style.applymap(apply_color), use_container_width=True)
                    
                    if st.button(f"{m}월 데이터 저장", key=f"btn_{m}"):
                        doc_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                        db.collection("daily_snapshots").document(doc_id).set({
                            "work_date": datetime.now().strftime("%Y-%m-%d"),
                            "data": m_df.to_dict(orient='records'),
                            "month": m
                        })
                        st.success("저장 완료!")
                else:
                    st.info(f"{m}월 데이터 없음")
    else:
        st.error("데이터를 읽지 못했습니다. 엑셀 행/열 위치를 확인하세요.")

elif mode == "과거 기록 조회":
    target = st.sidebar.date_input("조회일", datetime.now())
    docs = db.collection("daily_snapshots").where("work_date", "==", target.strftime("%Y-%m-%d")).stream()
    for doc in docs:
        d = doc.to_dict()
        st.write(f"🕒 {doc.id} ({d.get('month')}월분)")
        hist_df = pd.DataFrame(d['data'])
        v_df = hist_df.pivot(index='RoomID', columns='Date', values='Price')
        st.dataframe(v_df.style.applymap(apply_color), use_container_width=True)
