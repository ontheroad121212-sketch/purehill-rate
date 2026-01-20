import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 파이버베이스 및 상태 초기화 ---
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

# --- 3. 핵심 로직: 비교 및 수식 계산 ---
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
    # (성수기 로직 생략 없이 PRICE_TABLE 기준으로 매칭)
    price = PRICE_TABLE.get(room_id, {}).get(final_bar, 0)
    return occ, final_bar, price

# Firebase에서 가장 최근 저장된 데이터 가져오기
def get_last_snapshot():
    try:
        docs = db.collection("daily_snapshots").order_by("work_date", direction=firestore.Query.DESCENDING).limit(1).stream()
        for doc in docs:
            return pd.DataFrame(doc.to_dict()['data'])
    except: return pd.DataFrame()
    return pd.DataFrame()

# --- 4. 요일/Pickup/커스텀 수식 포함된 HTML 렌더러 ---
def render_rms_table(current_df, prev_df, custom_fee):
    room_ids = ["FDB", "FDE", "HDP", "HDT", "HDF"]
    dates = sorted(current_df['Date'].unique())
    
    html = """
    <style>
        .rms-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 12px; }
        .rms-table th, .rms-table td { border: 1px solid #ddd; text-align: center; padding: 5px; }
        .room-col { font-weight: bold; background: #fff; border-right: 3px solid #333 !important; }
        .sun { color: red; font-weight: bold; } .sat { color: blue; font-weight: bold; }
        .pickup-alert { background-color: #FFEBEE; color: #D32F2F; font-weight: bold; }
        .last-row { border-bottom: 4px solid #000 !important; }
        .formula-price { color: #2E7D32; font-weight: bold; }
    </style>
    <table class='rms-table'>
        <thead>
            <tr><th rowspan='2'>Room ID</th><th rowspan='2'>구분</th>
    """
    for d in dates: html += f"<th>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        cls = "sun" if wd == '일' else ("sat" if wd == '토' else "")
        html += f"<th class='{cls}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in room_ids:
        for i, category in enumerate(["점유율", "Pick-up", "추천BAR", "최종판매가"]):
            html += f"<tr class='{'last-row' if i==3 else ''}'>"
            if i == 0: html += f"<td rowspan='4' class='room-col'>{rid}</td>"
            html += f"<td style='background:#f9f9f9;'>{category}</td>"
            
            for d in dates:
                curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                if curr_match.empty:
                    html += "<td>-</td>"
                    continue
                
                curr_row = curr_match.iloc[0]
                occ, bar, price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
                
                if i == 0: val = f"{occ:.0f}%"
                elif i == 1: # Pick-up 분석
                    pickup = 0
                    if not prev_df.empty:
                        prev_match = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                        if not prev_match.empty:
                            pickup = prev_match.iloc[0]['Available'] - curr_row['Available']
                    p_cls = "pickup-alert" if pickup > 0 else ""
                    val = f"<div class='{p_cls}'>{f'+{pickup}' if pickup > 0 else (pickup if pickup < 0 else '-')}</div>"
                elif i == 2:
                    bg = BAR_COLORS.get(bar, "#fff")
                    val = f"<div style='background:{bg}; font-weight:bold;'>{bar}</div>"
                else: # 커스텀 수식 적용
                    final_price = price - custom_fee
                    val = f"<div class='formula-price'>{final_price:,}</div>"
                html += f"<td>{val}</td>"
            html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. 메인 UI ---
st.set_page_config(layout="wide")
st.title("📊 엠버퓨어힐 실시간 수익관리(RMS) - Pick-up 분석")

with st.sidebar:
    st.header("⚙️ 수식 설정 (커스텀)")
    fee = st.number_input("채널 할인액 (BAR - N)", value=0, step=1000)
    uploaded_files = st.file_uploader("엑셀 리포트 업로드", accept_multiple_files=True)
    if st.button("🔄 데이터 초기화"): st.session_state.all_data_df = pd.DataFrame(); st.rerun()

if uploaded_files:
    for f in uploaded_files:
        # load_custom_excel 로직 (이전 대화에서 확정된 3행 날짜/7,8,11,12,13행 객실 기준)
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values
        data = []
        for r_idx in [6, 7, 10, 11, 12]:
            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()
            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                if pd.isna(d_val) or pd.isna(av): continue
                try:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date().replace(year=2026) if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                    data.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot})
                except: continue
        new_df = pd.DataFrame(data)
        st.session_state.all_data_df = pd.concat([st.session_state.all_data_df, new_df]).drop_duplicates(subset=['Date', 'RoomID'], keep='last')

if not st.session_state.all_data_df.empty:
    prev_snapshot = get_last_snapshot() # 비교 대상(어제 데이터) 로드
    
    tab_list = st.tabs([f"{i}월" for i in range(1, 13)])
    for i, tab in enumerate(tab_list):
        with tab:
            m = i + 1
            m_df = st.session_state.all_data_df[st.session_state.all_data_df['Date'].apply(lambda x: x.month == m)]
            if not m_df.empty:
                st.markdown(render_rms_table(m_df, prev_snapshot, fee), unsafe_allow_html=True)
                if st.button(f"🚀 {m}월 스냅샷 저장 (내일 비교 기준점)", key=f"sv_{m}"):
                    db.collection("daily_snapshots").add({"work_date": datetime.now().strftime("%Y-%m-%d"), "data": m_df.to_dict(orient='records'), "month": m})
                    st.success("저장 완료!")
