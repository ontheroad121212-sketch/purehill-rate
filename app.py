import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import math

# --- 1. 파이어베이스 초기화 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# --- 2. 전역 설정 데이터 ---
# [기본 영역용] 보라색 채도 단계 (BAR 1이 가장 진함)
BASE_BAR_CHROMA = {
    "BAR1": "#4B0082", "BAR2": "#5A189A", "BAR3": "#7B2CBF", "BAR4": "#9D4EDD",
    "BAR5": "#C77DFF", "BAR6": "#D89DFF", "BAR7": "#E0AAFF", "BAR8": "#F3E5F5",
}

# [판도 변화 강조용] 아예 다른 컬러 에어리어 (예: 강렬한 오렌지/옐로우 계열)
ALERT_COLOR = "#FF6D00" # 강렬한 오렌지 (눈에 확 띄는 색)

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

if 'promotions' not in st.session_state:
    st.session_state.promotions = {"네이버": {rid: {"name": f"네이버_{rid}", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}}

# --- 3. 로직 함수 ---
def calculate_final_price(base_price, discount_rate, add_price):
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
        for doc in docs:
            df = pd.DataFrame(doc.to_dict()['data'])
            df['Date'] = pd.to_datetime(df['Date']).dt.date
            return df
    except: return pd.DataFrame()
    return pd.DataFrame()

# --- 4. 메인 렌더러 (HTML) ---
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준"):
    dates = sorted(current_df['Date'].unique())
    html = f"<div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; padding:10px; background:#f0f2f6; border-left:10px solid #000;'>{title}</div>"
    html += "<table style='width:100%; border-collapse:collapse; font-size:11px;'><thead><tr style='background:#f9f9f9;'><th rowspan='2' style='border:1px solid #ddd; width:150px;'>객실/프로모션</th>"
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th style='border:1px solid #ddd; padding:5px;' class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in ROOM_IDS:
        label = rid
        if mode == "판매가": label = f"<b>{rid}</b><br><small style='color:blue;'>{st.session_state.promotions[ch_name][rid]['name']}</small>"
        
        html += f"<tr><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000;'>{label}</td>"
        
        for d in dates:
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd;'>-</td>"; continue
            
            curr_row = curr_match.iloc[0]
            occ, bar, base_price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
            style = "border:1px solid #ddd; padding:8px; text-align:center; background-color:white;"
            content = "-"

            # 비교 로직
            prev_bar = None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                if not prev_m.empty: _, prev_bar, _ = determine_values(rid, d, prev_m.iloc[0]['Available'], prev_m.iloc[0]['Total'])
            
            is_changed = prev_bar and prev_bar != bar

            if mode == "기준":
                # ⭐ 1번 통: 보라색 채도 단계 적용
                bg = BASE_BAR_CHROMA.get(bar, "#fff")
                text_color = "white" if bar in ["BAR1", "BAR2", "BAR3"] else "black"
                style += f"background-color: {bg}; color: {text_color}; font-weight: bold;"
                content = f"{bar}<br>{occ:.0f}%"
            elif mode == "변화":
                pickup = 0
                if not prev_df.empty:
                    prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                    if not prev_m.empty: pickup = prev_m.iloc[0]['Available'] - curr_row['Available']
                content = f"+{pickup}" if pickup > 0 else (pickup if pickup < 0 else "-")
                if pickup > 0: style += "color:red; font-weight:bold; background:#FFEBEE;"
            elif mode == "판도변화":
                # ⭐ 3번 통: 변화 시에만 눈에 확 띄는 컬러 에어리어(오렌지) 적용
                if is_changed:
                    style += f"background-color: {ALERT_COLOR}; color: white; font-weight: bold; border: 2px solid black;"
                    content = f"▲ {bar}"
                else: content = bar
            elif mode == "판매가":
                conf = st.session_state.promotions[ch_name][rid]
                final_p = calculate_final_price(base_price, conf['discount_rate'], conf['add_price'])
                content = f"<b>{final_p:,}</b>"
                # ⭐ 하단 커스텀 통: 변화 발생 시 동일하게 오렌지 컬러 강조
                if is_changed:
                    style += f"background-color: {ALERT_COLOR}; color: white; font-weight: bold; border: 2.5px solid #000;"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI 및 데이터 처리 ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략적 수익관리 시스템")

with st.sidebar:
    st.header("⚙️ 채널 및 프로모션 빌더")
    new_ch = st.text_input("새 채널 명칭")
    if st.button("➕ 채널 추가"):
        if new_ch and new_ch not in st.session_state.promotions:
            st.session_state.promotions[new_ch] = {rid: {"name": f"{new_ch}_{rid}", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}
            st.rerun()
    
    for ch, configs in st.session_state.promotions.items():
        with st.expander(f"📦 {ch} 채널 설정"):
            for rid in ROOM_IDS:
                st.markdown(f"**{rid} 타입**")
                configs[rid]['name'] = st.text_input(f"프로모션명", value=configs[rid]['name'], key=f"{ch}_{rid}_n")
                c1, c2 = st.columns(2)
                configs[rid]['discount_rate'] = c1.number_input("할인율(%)", value=configs[rid]['discount_rate'], key=f"{ch}_{rid}_d")
                configs[rid]['add_price'] = c2.number_input("추가금액", value=configs[rid]['add_price'], step=1000, key=f"{ch}_{rid}_a")

    uploaded_files = st.file_uploader("엑셀 업로드 (1/9꺼 4개, 1/20꺼 4개 등 합쳐서 올리세요)", accept_multiple_files=True)
    if st.button("🚀 오늘 데이터 스냅샷 저장"):
        if 'today_df' in st.session_state:
            save_df = st.session_state.today_df.copy()
            save_df['Date'] = save_df['Date'].apply(lambda x: x.isoformat())
            db.collection("daily_snapshots").add({"save_time": datetime.now(), "data": save_df.to_dict(orient='records')})
            st.success("오늘 데이터 저장 완료!")

# 파일 처리 (생략 없이 로직 보강)
if uploaded_files:
    all_temp = []
    for f in uploaded_files:
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values
        data = []
        for r_idx in [6, 7, 10, 11, 12]:
            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()
            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                if pd.isna(d_val) or pd.isna(av): continue
                try:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date() if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                    data.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot, "File": f.name})
                except: continue
        all_temp.append(pd.DataFrame(data))

    if all_temp:
        full_df = pd.concat(all_temp)
        unique_files = sorted(full_df['File'].unique())
        if len(unique_files) >= 2:
            mid = len(unique_files) // 2
            st.session_state.prev_df = full_df[full_df['File'].isin(unique_files[:mid])]
            st.session_state.today_df = full_df[full_df['File'].isin(unique_files[mid:])]
        else:
            st.session_state.today_df = full_df
            st.session_state.prev_df = get_last_snapshot()

if 'today_df' in st.session_state:
    curr = st.session_state.today_df
    prev = st.session_state.get('prev_df', pd.DataFrame())
    
    st.markdown(render_master_table(curr, prev, title="📊 1. 시장 분석 (보라색 채도 단계)", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="📈 2. 예약 변화량 (Pick-up)", mode="변화"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="🔔 3. 판도 변화 (강렬한 오렌지 강조)", mode="판도변화"), unsafe_allow_html=True)
    
    st.divider()
    st.header("📲 4. 채널별 최종 판매가 산출 (변화 시 오렌지 연동)")
    for ch in st.session_state.promotions.keys():
        st.markdown(render_master_table(curr, prev, ch_name=ch, title=f"✅ {ch} 판매가", mode="판매가"), unsafe_allow_html=True)
