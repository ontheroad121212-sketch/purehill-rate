import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import math

# --- 1. 파이어베이스 및 상태 초기화 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# --- 2. 전역 설정 데이터 ---
# BAR 등급별 고유 색상 (동일 BAR는 동일 색상)
BAR_STYLE = {
    "BAR1": {"bg": "#FF4B4B", "text": "white"}, 
    "BAR2": {"bg": "#FF7E7E", "text": "white"}, 
    "BAR3": {"bg": "#FFD166", "text": "black"}, 
    "BAR4": {"bg": "#FFFC99", "text": "black"}, 
    "BAR5": {"bg": "#D1FFBD", "text": "black"}, 
    "BAR6": {"bg": "#99FF99", "text": "black"}, 
    "BAR7": {"bg": "#BAE1FF", "text": "black"}, 
    "BAR8": {"bg": "#A0C4FF", "text": "black"}, 
}

# 판도 변화(BAR 등급 변경) 시 강조 스타일
ALERT_STYLE = "background-color: #7000FF; color: white; font-weight: bold; border: 2.5px solid #000;"

WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
ROOM_IDS = ["FDB", "FDE", "HDP", "HDT", "HDF"]

PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

if 'all_data_df' not in st.session_state:
    st.session_state.all_data_df = pd.DataFrame()

# ⭐ 사이드바 커스텀 셋팅을 저장할 상태값 (핵심)
if 'promotions' not in st.session_state:
    st.session_state.promotions = {
        "네이버": {rid: {"name": f"네이버_{rid}_패키지", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}
    }

# --- 3. 핵심 로직 함수 ---
def calculate_final_price(base_price, discount_rate, add_price):
    """(기준가 * 할인율) -> 1000원 단위 절삭 -> 추가금액"""
    after_discount = base_price * (1 - (discount_rate / 100))
    floored = math.floor(after_discount / 1000) * 1000
    return int(floored + add_price)

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
    try:
        docs = db.collection("daily_snapshots").order_by("save_time", direction=firestore.Query.DESCENDING).limit(1).stream()
        for doc in docs: return pd.DataFrame(doc.to_dict()['data'])
    except: return pd.DataFrame()
    return pd.DataFrame()

# --- 4. 4단계 통 구조 HTML 렌더러 ---
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준"):
    dates = sorted(current_df['Date'].unique())
    html = f"""
    <div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; color:#1E1E1E; padding:10px; background:#f0f2f6; border-left:10px solid #000;'>{title}</div>
    <table style='width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 11px;'>
        <thead><tr style='background:#f9f9f9;'><th style='border:1px solid #ddd; padding:8px; width:150px;' rowspan='2'>객실/프로모션</th>
    """
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th style='border:1px solid #ddd; padding:5px;' class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in ROOM_IDS:
        label = rid
        if mode == "판매가" and ch_name:
            p_name = st.session_state.promotions[ch_name][rid]['name']
            label = f"<b>{rid}</b><br><span style='color:#1A73E8; font-size:10px;'>{p_name}</span>"
        
        html += f"<tr><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000;'>{label}</td>"
        
        for d in dates:
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd;'>-</td>"
                continue
            
            curr_row = curr_match.iloc[0]
            occ, bar, base_price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
            style = "border:1px solid #ddd; padding:8px; text-align:center;"
            content = "-"
            
            if mode == "기준":
                conf = BAR_STYLE.get(bar, {"bg": "#fff", "text": "#000"})
                content = f"<div style='background:{conf['bg']}; color:{conf['text']}; font-weight:bold; padding:4px;'>{bar}<br>{occ:.0f}%</div>"
            elif mode == "변화":
                pickup = 0
                if not prev_df.empty:
                    prev_match = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                    if not prev_match.empty: pickup = prev_match.iloc[0]['Available'] - curr_row['Available']
                if pickup > 0:
                    style += "background-color: #FFEBEE; color: #D32F2F; font-weight: bold;"
                    content = f"+{pickup}"
                elif pickup < 0: content = str(pickup)
            elif mode == "판도변화":
                prev_bar = None
                if not prev_df.empty:
                    prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                    if not prev_m.empty: _, prev_bar, _ = determine_values(rid, d, prev_m.iloc[0]['Available'], prev_m.iloc[0]['Total'])
                if prev_bar and prev_bar != bar:
                    style += ALERT_STYLE
                    content = f"▲ {bar}"
                else:
                    conf = BAR_STYLE.get(bar, {"bg": "#fff", "text": "#000"})
                    style += f"background-color: {conf['bg']}; color: {conf['text']};"
                    content = bar
            elif mode == "판매가":
                conf = st.session_state.promotions[ch_name][rid]
                final_p = calculate_final_price(base_price, conf['discount_rate'], conf['add_price'])
                content = f"<b style='color:#2E7D32; font-size:13px;'>{final_p:,}</b>"
            
            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI 및 메인 로직 ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략적 판도 분석 RMS")

# ⭐ 사이드바: 커스텀 셋팅 영역 (생략 없음)
with st.sidebar:
    st.header("🎯 채널별 프로모션 빌더")
    new_ch = st.text_input("새 채널 이름")
    if st.button("➕ 채널 추가"):
        if new_ch and new_ch not in st.session_state.promotions:
            st.session_state.promotions[new_ch] = {rid: {"name": f"{new_ch}_기본", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}
            st.rerun()

    st.divider()
    for ch, configs in st.session_state.promotions.items():
        with st.expander(f"📦 {ch} 채널 상세 설정", expanded=False):
            for rid in ROOM_IDS:
                st.markdown(f"**[{rid}] 설정**")
                configs[rid]['name'] = st.text_input(f"프로모션명", value=configs[rid]['name'], key=f"{ch}_{rid}_n")
                c1, c2 = st.columns(2)
                configs[rid]['discount_rate'] = c1.number_input("할인(%)", value=configs[rid]['discount_rate'], key=f"{ch}_{rid}_d")
                configs[rid]['add_price'] = c2.number_input("추가금", value=configs[rid]['add_price'], step=1000, key=f"{ch}_{rid}_a")
                st.divider()

    uploaded_files = st.file_uploader("엑셀 리포트 업로드", accept_multiple_files=True)
    if st.button("🚀 스냅샷 저장 (기준점)"):
        if not st.session_state.all_data_df.empty:
            db.collection("daily_snapshots").add({"save_time": datetime.now(), "data": st.session_state.all_data_df.to_dict(orient='records')})
            st.success("오늘 데이터 저장 완료! 내일 비교 기준이 됩니다.")

# 파일 로드 로직
if uploaded_files:
    all_temp = []
    for f in uploaded_files:
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values
        for r_idx in [6, 7, 10, 11, 12]:
            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()
            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                if pd.isna(d_val) or pd.isna(av): continue
                try:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date().replace(year=2026) if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                    all_temp.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot})
                except: continue
    st.session_state.all_data_df = pd.DataFrame(all_temp)

# 메인 화면 출력 (4단계 통 구조)
if not st.session_state.all_data_df.empty:
    last_data = get_last_snapshot()
    curr_data = st.session_state.all_data_df
    
    st.markdown(render_master_table(curr_data, last_data, title="📊 1. 시장 분석 (오늘의 추천 BAR / 점유율)", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr_data, last_data, title="📈 2. 예약 변화량 (전일 대비 Pick-up)", mode="변화"), unsafe_allow_html=True)
    
    # ⭐ 판도 변화 통: BAR가 변하면 보라색 강조, 동일 BAR는 동일 색상
    st.markdown(render_master_table(curr_data, last_data, title="🔔 3. 판도 변화 (BAR 등급 변경 알림)", mode="판도변화"), unsafe_allow_html=True)
    
    st.header("📲 4. 채널별 최종 판매가 통")
    for ch_name in st.session_state.promotions.keys():
        st.markdown(render_master_table(curr_data, last_data, ch_name=ch_name, title=f"✅ {ch_name} 판매가 (커스텀 수식 반영)", mode="판매가"), unsafe_allow_html=True)
