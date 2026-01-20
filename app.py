import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
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

# 요일 표시용 한글 매핑
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']

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

# 어제 데이터 가져오기 (Firebase)
def get_yesterday_data():
    docs = db.collection("daily_snapshots").order_by("work_date", direction=firestore.Query.DESCENDING).limit(1).stream()
    for doc in docs:
        return pd.DataFrame(doc.to_dict()['data'])
    return pd.DataFrame()

# --- 4. 요일/변화량/커스텀 수식이 들어간 HTML 테이블 ---
def render_rms_table(current_df, prev_df, custom_fee):
    room_ids = ["FDB", "FDE", "HDP", "HDT", "HDF"]
    dates = sorted(current_df['Date'].unique())
    
    html = """
    <style>
        .rms-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 12px; }
        .rms-table th, .rms-table td { border: 1px solid #ddd; text-align: center; padding: 3px; }
        .rms-table th { background-color: #f2f2f2; }
        .room-col { font-weight: bold; width: 70px; border-right: 2px solid #333 !important; background: #fff; }
        .sun { color: red; } .sat { color: blue; }
        .pickup-plus { background-color: #FFEBEE; color: #D32F2F; font-weight: bold; }
        .pickup-minus { background-color: #E3F2FD; color: #1976D2; }
        .last-row { border-bottom: 3px solid #000 !important; }
        .custom-price { font-weight: bold; color: #2E7D32; }
    </style>
    <table class='rms-table'>
        <thead>
            <tr>
                <th rowspan='2'>Room ID</th>
                <th rowspan='2'>구분</th>
    """
    # 날짜 헤더
    for d in dates:
        html += f"<th>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr>"
    
    # 요일 헤더
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        cls = "sun" if wd == '일' else ("sat" if wd == '토' else "")
        html += f"<th class='{cls}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in room_ids:
        for i, category in enumerate(["점유율", "Pick-up", "추천BAR", "판매가(커스텀)"]):
            is_last = (i == 3)
            html += f"<tr class='{'last-row' if is_last else ''}'>"
            if i == 0: html += f"<td rowspan='4' class='room-col'>{rid}</td>"
            html += f"<td style='background:#fcfcfc;'>{category}</td>"
            
            for d in dates:
                curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                if curr_match.empty:
                    html += "<td>-</td>"
                    continue
                
                curr_row = curr_match.iloc[0]
                occ, bar, price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
                
                if i == 0: # 점유율
                    html += f"<td>{occ:.0f}%</td>"
                elif i == 1: # Pick-up (전날 대비 변화)
                    pickup = 0
                    if not prev_df.empty:
                        # Date가 string으로 저장되었을 수 있으므로 변환 처리
                        prev_match = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                        if not prev_match.empty:
                            pickup = prev_match.iloc[0]['Available'] - curr_row['Available']
                    
                    p_class = "pickup-plus" if pickup > 0 else ("pickup-minus" if pickup < 0 else "")
                    p_text = f"+{pickup}" if pickup > 0 else (str(pickup) if pickup < 0 else "-")
                    html += f"<td class='{p_class}'>{p_text}</td>"
                elif i == 2: # BAR
                    bg = BAR_COLORS.get(bar, "#fff")
                    html += f"<td style='background:{bg}; font-weight:bold;'>{bar}</td>"
                else: # 커스텀 수식 (판매가)
                    final_price = price - custom_fee
                    html += f"<td class='custom-price'>{final_price:,}</td>"
            html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI 및 실행 ---
st.set_page_config(layout="wide")
st.title("📊 엠버퓨어힐 RMS - 변화량 추적 대시보드")

with st.sidebar:
    st.header("⚙️ 수식 커스텀")
    # 수기로 관리할 채널 수식 (예: BAR 가격에서 고정 할인액 차감)
    fee = st.number_input("채널별 고정 할인액 설정 (BAR - N)", value=0, step=1000)
    
    st.divider()
    uploaded_files = st.file_uploader("오늘자 리포트 업로드", accept_multiple_files=True)
    if st.button("🔄 데이터 초기화"):
        st.session_state.all_data_df = pd.DataFrame()
        st.rerun()

# 오늘 데이터 처리
if uploaded_files:
    for f in uploaded_files:
        new_df = load_custom_excel(f)
        if not st.session_state.all_data_df.empty:
            st.session_state.all_data_df = pd.concat([st.session_state.all_data_df, new_df]).drop_duplicates(subset=['Date', 'RoomID'], keep='last')
        else:
            st.session_state.all_data_df = new_df

# 메인 분석 화면
if not st.session_state.all_data_df.empty:
    # 1. 과거 스냅샷 데이터 로드 (비교용)
    prev_data = get_yesterday_data()
    
    tabs = st.tabs([f"{i}월" for i in range(1, 13)])
    for i, tab in enumerate(tabs):
        with tab:
            m = i + 1
            month_df = st.session_state.all_data_df[st.session_state.all_data_df['Date'].apply(lambda x: x.month == m)]
            if not month_df.empty:
                st.info(f"💡 **Pick-up**: 어제(직전 저장본) 대비 예약 증감입니다. (빨간색: 예약 증가)")
                # 테이블 렌더링
                st.markdown(render_rms_table(month_df, prev_data, fee), unsafe_allow_html=True)
                
                if st.button(f"🚀 {m}월 데이터 스냅샷 저장", key=f"save_{m}"):
                    save_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                    db.collection("daily_snapshots").document(save_id).set({
                        "work_date": datetime.now().strftime("%Y-%m-%d"),
                        "data": month_df.to_dict(orient='records'),
                        "month": m
                    })
                    st.success("데이터가 저장되었습니다. 내일 업로드 시 오늘 데이터와 비교됩니다.")
            else:
                st.info("데이터 없음")
