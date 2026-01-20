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
# 주말(금, 토) 가산금 (주신 요금표가 평일 기준이라면 설정, 아니면 0)
WEEKEND_SURCHARGE = 0  

PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

# 엑셀 A열의 텍스트와 위 ID 매칭 (엑셀에 적힌 이름과 똑같이 맞춰주세요)
ROOM_MAPPING = {
    "FDB": "FDB",
    "FDE": "FDE",
    "HDP": "HDP",
    "HDT": "HDT",
    "HDF": "HDF"
}

# 객실별 전체 재고량
ROOM_CONFIG = {
    "FDB": 32, "FDE": 8, "HDP": 19, "HDT": 34, "HDF": 18
}

# 특수 기간 설정
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
    day_type = "WE" if is_weekend else "WD"
    
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
    if is_weekend: base_price += WEEKEND_SURCHARGE
    
    return final_bar, base_price, label

def apply_color(val):
    if pd.isna(val) or val == 0: return ""
    color_hash = hashlib.md5(str(val).encode()).hexdigest()[:6]
    return f'background-color: #{color_hash}; color: black; font-weight: bold;'

def load_custom_excel(file):
    # 엔진 자동 선택 및 모든 시트 읽기 시도
    df_raw = pd.read_excel(file, header=None)
    
    # 3행(index 2)에서 날짜 데이터 추출 (공백 제거)
    dates_raw = df_raw.iloc[2, 2:].values
    
    # 우리가 찾는 객실 키워드 리스트
    target_keywords = list(ROOM_MAPPING.keys())
    
    all_data = []
    
    # 엑셀의 모든 행을 훑으며 객실 이름이 있는지 확인 (더 안전한 방식)
    for row_idx in range(len(df_raw)):
        cell_value = str(df_raw.iloc[row_idx, 0]).strip()
        
        # 엑셀 칸에 우리가 설정한 객실 이름이 포함되어 있는지 체크
        matched_room = None
        for k in target_keywords:
            if k in cell_value:
                matched_room = k
                break
        
        if matched_room:
            room_id = ROOM_MAPPING[matched_room]
            total_inv = ROOM_CONFIG.get(room_id, 30)
            avails = df_raw.iloc[row_idx, 2:].values
            
            for date, avail in zip(dates_raw, avails):
                if pd.isna(date) or pd.isna(avail): continue
                
                try:
                    # 날짜 변환 로직
                    if isinstance(date, (int, float)):
                        d_obj = pd.to_datetime('1899-12-30') + pd.to_timedelta(date, 'D')
                    else:
                        d_obj = pd.to_datetime(str(date).strip(), errors='coerce')
                    
                    if pd.isna(d_obj): continue
                    
                    all_data.append({
                        "Date": d_obj.date(),
                        "RoomID": room_id,
                        "RoomName": matched_room,
                        "Available": pd.to_numeric(avail, errors='coerce'),
                        "Total": total_inv
                    })
                except:
                    continue
                    
    result_df = pd.DataFrame(all_data)
    # 데이터가 비었는지 확인용 로그 (스트림릿 로그에서 확인 가능)
    if result_df.empty:
        st.error(f"매칭된 객실이 없습니다. 엑셀 A열 이름을 확인해주세요. (찾는 이름: {target_keywords})")
        
    return result_df
# --- 4. Streamlit UI ---
st.set_page_config(layout="wide")
st.title("🏨 호텔 요금 관리 및 히스토리 대시보드")

with st.sidebar:
    mode = st.radio("작업 선택", ["요금 수정", "과거 기록 조회"])
    uploaded_file = st.file_uploader("엑셀 파일 업로드 (.xls, .xlsx)", type=['xlsx', 'xls'])

tabs = st.tabs([f"{i}월" for i in range(1, 13)])

if mode == "요금 수정" and uploaded_file:
    df = load_custom_excel(uploaded_file)
    
    if not df.empty:
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
                    view_df = m_df.pivot(index='RoomName', columns='Date', values='Price')
                    st.dataframe(view_df.style.applymap(apply_color), use_container_width=True)
                    
                    if st.button(f"{m}월 데이터 저장", key=f"btn_{m}"):
                        doc_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                        db.collection("daily_snapshots").document(doc_id).set({
                            "work_date": datetime.now().strftime("%Y-%m-%d"),
                            "data": m_df.to_dict(orient='records'),
                            "month": m
                        })
                        st.success(f"{m}월 기록이 Firebase에 저장되었습니다.")
                else:
                    st.info(f"{m}월 데이터가 없습니다.")
    else:
        st.error("엑셀 파일에서 데이터를 읽어오지 못했습니다. 형식을 확인해주세요.")

elif mode == "과거 기록 조회":
    target = st.sidebar.date_input("조회할 날짜 선택", datetime.now())
    docs = db.collection("daily_snapshots").where("work_date", "==", target.strftime("%Y-%m-%d")).stream()
    
    found = False
    for doc in docs:
        found = True
        d = doc.to_dict()
        st.write(f"🕒 저장 시각: {doc.id} ({d.get('month', '')}월분)")
        hist_df = pd.DataFrame(d['data'])
        v_df = hist_df.pivot(index='RoomName', columns='Date', values='Price')
        st.dataframe(v_df.style.applymap(apply_color), use_container_width=True)
    
    if not found:
        st.warning("해당 날짜에 저장된 기록이 없습니다.")
