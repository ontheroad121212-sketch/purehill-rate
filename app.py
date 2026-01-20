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
ROOM_IDS = ["FDB", "FDE", "HDP", "HDT", "HDF"]

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

def get_last_snapshot():
    docs = db.collection("daily_snapshots").order_by("save_time", direction=firestore.Query.DESCENDING).limit(1).stream()
    for doc in docs: return pd.DataFrame(doc.to_dict()['data'])
    return pd.DataFrame()

# --- 4. 통 구조 렌더러 (HTML) ---
def render_block_table(current_df, prev_df, sites, title, mode):
    dates = sorted(current_df['Date'].unique())
    html = f"""
    <div style='margin-top:25px; margin-bottom:10px; font-weight:bold; font-size:16px; color:#333; padding-left:5px; border-left:5px solid #000;'>{title}</div>
    <table style='width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 11px; margin-bottom:30px;'>
        <thead>
            <tr style='background:#f2f2f2;'>
                <th style='border:1px solid #ddd; padding:5px;' rowspan='2'>Room ID</th>
    """
    if mode == "판매가": html += "<th style='border:1px solid #ddd; padding:5px;' rowspan='2'>채널</th>"
    
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f2f2f2;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th style='border:1px solid #ddd; padding:5px;' class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in ROOM_IDS:
        rows_in_block = sites if mode == "판매가" else [title]
        for idx, item in enumerate(rows_in_block):
            is_last_row = (idx == len(rows_in_block) - 1)
            border_style = "border-bottom: 3px solid black !important;" if is_last_row else ""
            html += f"<tr style='{border_style}'>"
            
            if idx == 0:
                html += f"<td rowspan='{len(rows_in_block)}' style='border:1px solid #ddd; font-weight:bold; background:#fff; width:80px;'>{rid}</td>"
            
            if mode == "판매가":
                html += f"<td style='border:1px solid #ddd; background:#f9f9f9; width:80px;'>{item['name']}</td>"
            
            for d in dates:
                curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                if curr_match.empty:
                    html += "<td style='border:1px solid #ddd;'>-</td>"
                    continue
                
                curr_row = curr_match.iloc[0]
                occ, bar, price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
                
                content = "-"
                style = "border:1px solid #ddd;"
                
                if mode == "기준":
                    bg = BAR_COLORS.get(bar, "#fff")
                    content = f"<div style='background:{bg}; font-weight:bold; padding:3px;'>{bar}<br><small>({occ:.0f}%)</small></div>"
                elif mode == "변화":
                    pickup = 0
                    if not prev_df.empty:
                        prev_match = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                        if not prev_match.empty: pickup = prev_match.iloc[0]['Available'] - curr_row['Available']
                    if pickup > 0:
                        style += "background-color: #FFEBEE; color: red; font-weight: bold;"
                        content = f"+{pickup}"
                    elif pickup < 0: content = str(pickup)
                    else: content = "-"
                elif mode == "판매가":
                    content = f"<b style='color:#2E7D32;'>{(price - item['offset']):,}</b>"
                
                html += f"<td style='{style}'>{content}</td>"
            html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 RMS - 3단계 통 대시보드")

if 'sites' not in st.session_state:
    st.session_state.sites = [{"name": "네이버", "offset": 10000}, {"name": "아고다", "offset": 15000}]

with st.sidebar:
    st.header("⚙️ 채널 설정")
    for i, site in enumerate(st.session_state.sites):
        c1, c2 = st.columns([2, 1])
        site['name'] = c1.text_input(f"채널 {i+1}", value=site['name'], key=f"n_{i}")
        site['offset'] = c2.number_input(f"할인액", value=site['offset'], step=1000, key=f"o_{i}")
    if st.button("➕ 채널 추가"):
        st.session_state.sites.append({"name": "신규", "offset": 0})
        st.rerun()
    
    st.divider()
    files = st.file_uploader("엑셀 업로드", accept_multiple_files=True)
    if st.button("🚀 현재 상태 저장 (Snapshot)"):
        if not st.session_state.all_data_df.empty:
            db.collection("daily_snapshots").add({"save_time": datetime.now(), "data": st.session_state.all_data_df.to_dict(orient='records')})
            st.success("저장 완료!")

# 데이터 처리
if files:
    all_new = []
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
                    all_new.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot})
                except: continue
    st.session_state.all_data_df = pd.DataFrame(all_new)

if not st.session_state.all_data_df.empty:
    prev_snapshot = get_last_snapshot()
    curr_df = st.session_state.all_data_df
    
    # [통 1] 기준 데이터 (BAR & OCC)
    st.markdown(render_block_table(curr_df, prev_snapshot, [], "1. 기준 데이터 (BAR / 점유율)", "기준"), unsafe_allow_html=True)
    
    # [통 2] 변화값 (Pick-up)
    st.markdown(render_block_table(curr_df, prev_snapshot, [], "2. 변화값 (전일 대비 Pick-up)", "변화"), unsafe_allow_html=True)
    
    # [통 3] 채널별 판매가
    st.markdown(render_block_table(curr_df, prev_snapshot, st.session_state.sites, "3. 채널별 수식 판매가", "판매가"), unsafe_allow_html=True)
