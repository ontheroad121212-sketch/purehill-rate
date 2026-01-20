import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 파이어베이스 초기화 ---
if not firebase_admin._apps:
    fb_dict = st.secrets["firebase"]
    cred = credentials.Certificate(dict(fb_dict))
    firebase_admin.initialize_app(cred)
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

# --- 3. 로직 함수 ---
def determine_values(room_id, date_obj, avail, total):
    occ = ((total - avail) / total * 100) if total > 0 else 0
    final_bar = "BAR8"
    if occ >= 90: final_bar = "BAR1"
    elif occ >= 80: final_bar = "BAR2"
    elif occ >= 70: final_bar = "BAR3"
    elif occ >= 60: final_bar = "BAR4"
    elif occ >= 50: final_bar = "BAR5"
    elif occ >= 40: final_bar = "BAR6"
    elif occ >= 30: final_bar = "BAR7"
    price = PRICE_TABLE.get(room_id, {}).get(final_bar, 0)
    return occ, final_bar, price

# 직전 스냅샷 가져오기
def get_last_snapshot():
    docs = db.collection("daily_snapshots").order_by("save_time", direction=firestore.Query.DESCENDING).limit(1).stream()
    for doc in docs: return pd.DataFrame(doc.to_dict()['data'])
    return pd.DataFrame()

# --- 4. 요일/Pick-up/사이트별 커스텀 요금이 포함된 최종 렌더러 ---
def render_master_table(current_df, prev_df, sites):
    room_ids = ["FDB", "FDE", "HDP", "HDT", "HDF"]
    dates = sorted(current_df['Date'].unique())
    
    html = """
    <style>
        .m-table { width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 11px; }
        .m-table th, .m-table td { border: 1px solid #ddd; text-align: center; padding: 4px; }
        .sun { color: red; } .sat { color: blue; }
        .pickup-cell { background-color: #FFEBEE; color: red; font-weight: bold; }
        .bar-cell { font-weight: bold; border: 2px solid #333; font-size: 13px; }
        .site-row { color: #2E7D32; font-weight: bold; }
        .thick-border { border-bottom: 4px solid black !important; }
    </style>
    <table class='m-table'>
        <thead>
            <tr><th rowspan='2'>Room ID</th><th rowspan='2'>구분</th>
    """
    for d in dates: html += f"<th>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in room_ids:
        # 고정 항목들
        categories = ["점유율", "Pick-up", "추천BAR"] + [s['name'] for s in sites]
        
        for i, cat in enumerate(categories):
            is_last = (i == len(categories) - 1)
            html += f"<tr class='{'thick-border' if is_last else ''}'>"
            if i == 0: html += f"<td rowspan='{len(categories)}' style='font-weight:bold; border-right:2px solid #333; background:#fff;'>{rid}</td>"
            
            html += f"<td style='background:#f9f9f9;'>{cat}</td>"
            
            for d in dates:
                curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                if curr_match.empty:
                    html += "<td>-</td>"
                    continue
                
                curr_row = curr_match.iloc[0]
                occ, bar, price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
                
                if cat == "점유율": val = f"{occ:.0f}%"
                elif cat == "Pick-up":
                    pickup = 0
                    if not prev_df.empty:
                        prev_match = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                        if not prev_match.empty: pickup = prev_match.iloc[0]['Available'] - curr_row['Available']
                    val = f"<div class='{'pickup-cell' if pickup > 0 else ''}'>{f'+{pickup}' if pickup > 0 else (pickup if pickup < 0 else '-')}</div>"
                elif cat == "추천BAR":
                    val = f"<div class='bar-cell' style='background:{BAR_COLORS.get(bar, '#fff')}'>{bar}</div>"
                else:
                    # 사이트별 요금 계산 (BAR 요금 - 할인액)
                    offset = next((s['offset'] for s in sites if s['name'] == cat), 0)
                    val = f"<div class='site-row'>{(price - offset):,}</div>"
                
                html += f"<td>{val}</td>"
            html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI 및 커스텀 사이트 설정 ---
st.set_page_config(layout="wide")
st.title("📊 엠버퓨어힐 실시간 수익관리(RMS) 시스템")

if 'sites' not in st.session_state:
    st.session_state.sites = [{"name": "네이버", "offset": 10000}, {"name": "아고다", "offset": 15000}]

with st.sidebar:
    st.header("🛠️ 사이트별 요금 수식")
    for i, site in enumerate(st.session_state.sites):
        col1, col2 = st.columns([2, 1])
        site['name'] = col1.text_input(f"사이트 {i+1}", value=site['name'], key=f"name_{i}")
        site['offset'] = col2.number_input(f"할인액", value=site['offset'], step=1000, key=f"off_{i}")
    
    if st.button("➕ 사이트 추가"):
        st.session_state.sites.append({"name": "신규", "offset": 0})
        st.rerun()

    st.divider()
    files = st.file_uploader("오늘자 엑셀 리포트", accept_multiple_files=True)
    if st.button("🚀 데이터 스냅샷 저장"):
        if not st.session_state.all_data_df.empty:
            db.collection("daily_snapshots").add({
                "save_time": datetime.now(),
                "data": st.session_state.all_data_df.to_dict(orient='records')
            })
            st.success("오늘 데이터 저장 완료! 내일 비교 기준이 됩니다.")

# 데이터 로드 및 렌더링
if files:
    # (load_custom_excel 로직 생략 없이 데이터 로드...)
    # [코드 지면상 이전에 작성한 load_custom_excel 함수가 그대로 들어갑니다]
    all_new_data = []
    for f in files:
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values
        for r_idx in [6, 7, 10, 11, 12]:
            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()
            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                if pd.isna(d_val) or pd.isna(av): continue
                try:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date().replace(year=2026) if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                    all_new_data.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot})
                except: continue
    st.session_state.all_data_df = pd.DataFrame(all_new_data)

if not st.session_state.all_data_df.empty:
    prev_snapshot = get_last_snapshot()
    st.markdown(render_master_table(st.session_state.all_data_df, prev_snapshot, st.session_state.sites), unsafe_allow_html=True)
