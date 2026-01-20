import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 파이어베이스 및 상태 초기화 ---
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

# --- 4. 채널별 통 구조 렌더러 (HTML) ---
def render_channel_block(current_df, prev_df, channel_info=None, title="", mode="기준"):
    dates = sorted(current_df['Date'].unique())
    html = f"""
    <div style='margin-top:35px; margin-bottom:10px; font-weight:bold; font-size:18px; color:#1E1E1E; padding:8px; background:#f0f0f0; border-left:8px solid #000;'>{title}</div>
    <table style='width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 12px; margin-bottom:20px;'>
        <thead>
            <tr style='background:#f9f9f9;'>
                <th style='border:1px solid #ddd; padding:8px; width:120px;' rowspan='2'>Room ID</th>
    """
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th style='border:1px solid #ddd; padding:5px;' class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in ROOM_IDS:
        html += "<tr>"
        html += f"<td style='border:1px solid #ddd; font-weight:bold; background:#fff; border-right:3px solid #000;'>{rid}</td>"
        
        for d in dates:
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd;'>-</td>"
                continue
            
            curr_row = curr_match.iloc[0]
            occ, bar, price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
            
            content = "-"
            style = "border:1px solid #ddd; padding:8px;"
            
            if mode == "기준":
                bg = BAR_COLORS.get(bar, "#fff")
                content = f"<div style='background:{bg}; font-weight:bold; border-radius:3px; padding:4px;'>{bar}<br><small>{occ:.0f}%</small></div>"
            elif mode == "변화":
                pickup = 0
                if not prev_df.empty:
                    prev_match = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                    if not prev_match.empty: pickup = prev_match.iloc[0]['Available'] - curr_row['Available']
                if pickup > 0:
                    style += "background-color: #FFEBEE; color: #D32F2F; font-weight: bold;"
                    content = f"+{pickup}"
                elif pickup < 0: content = str(pickup)
                else: content = "-"
            elif mode == "판매가":
                content = f"<b style='color:#2E7D32; font-size:14px;'>{(price - channel_info['offset']):,}</b>"
            
            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 채널 중심 통합 RMS")

if 'sites' not in st.session_state:
    st.session_state.sites = [{"name": "네이버", "offset": 10000}, {"name": "아고다", "offset": 15000}]

with st.sidebar:
    st.header("⚙️ 판매 채널 관리")
    for i, site in enumerate(st.session_state.sites):
        c1, c2 = st.columns([2, 1])
        site['name'] = c1.text_input(f"채널 명 {i+1}", value=site['name'], key=f"n_{i}")
        site['offset'] = c2.number_input(f"할인액", value=site['offset'], step=1000, key=f"o_{i}")
    
    if st.button("➕ 새 채널 추가"):
        st.session_state.sites.append({"name": "신규 채널", "offset": 0})
        st.rerun()
    
    st.divider()
    files = st.file_uploader("엑셀 리포트 업로드 (복수 가능)", accept_multiple_files=True)
    if st.button("🚀 데이터 스냅샷 저장"):
        if not st.session_state.all_data_df.empty:
            db.collection("daily_snapshots").add({"save_time": datetime.now(), "data": st.session_state.all_data_df.to_dict(orient='records')})
            st.success("저장 완료!")

# 데이터 처리 로직
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
    
    # 1. 공통 분석 지표 (BAR / Pick-up)
    st.markdown(render_channel_block(curr_df, prev_snapshot, title="📊 시장 분석 (추천 BAR / 점유율)", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_channel_block(curr_df, prev_snapshot, title="📈 예약 변화량 (전일 대비 Pick-up)", mode="변화"), unsafe_allow_html=True)
    
    st.divider()
    
    # 2. 채널별 통 구조 (요청하신 핵심)
    st.header("📲 채널별 최종 판매가 통")
    for site in st.session_state.sites:
        st.markdown(render_channel_block(curr_df, prev_snapshot, channel_info=site, title=f"✅ {site['name']} 판매가 (BAR - {site['offset']:,})", mode="판매가"), unsafe_allow_html=True)
