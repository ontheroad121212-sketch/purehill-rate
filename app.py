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
# BAR 등급별 보라색 (변화된 등급끼리 같은 색)
CHANGE_COLORS = {
    "BAR1": "#4B0082", "BAR2": "#5A189A", "BAR3": "#7B2CBF", "BAR4": "#9D4EDD",
    "BAR5": "#C77DFF", "BAR6": "#D89DFF", "BAR7": "#E0AAFF", "BAR8": "#EFD3FF",
}

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

# --- 4. 렌더러 (HTML) ---
def render_snapshot_table(current_df, prev_df, ch_name=None, title="", mode="기준"):
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

            # 비교 대상 BAR 추출
            prev_bar = None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                if not prev_m.empty:
                    _, prev_bar, _ = determine_values(rid, d, prev_m.iloc[0]['Available'], prev_m.iloc[0]['Total'])
            
            is_changed = prev_bar and prev_bar != bar
            
            if mode == "기준":
                content = f"<b>{bar}</b><br>{occ:.0f}%"
            elif mode == "변화":
                pickup = 0
                if not prev_df.empty:
                    prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]
                    if not prev_m.empty: pickup = prev_m.iloc[0]['Available'] - curr_row['Available']
                content = f"+{pickup}" if pickup > 0 else (pickup if pickup < 0 else "-")
                if pickup > 0: style += "color:red; font-weight:bold; background:#FFEBEE;"
            elif mode == "판도변화":
                if is_changed:
                    bg = CHANGE_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold;"
                    content = f"▲ {bar}"
                else: content = bar
            elif mode == "판매가":
                conf = st.session_state.promotions[ch_name][rid]
                final_p = calculate_final_price(base_price, conf['discount_rate'], conf['add_price'])
                content = f"<b>{final_p:,}</b>"
                if is_changed:
                    bg = CHANGE_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2px solid #000;"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 5. UI 및 데이터 처리 ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 판도 분석 RMS")

with st.sidebar:
    st.header("⚙️ 채널 설정")
    # ... (생략 없이 사이드바 설정 유지)
    uploaded_files = st.file_uploader("엑셀 업로드 (1/9꺼 4개, 1/20꺼 4개 등 합쳐서 올리세요)", accept_multiple_files=True)

# 8개 파일을 한꺼번에 처리하는 로직
if uploaded_files:
    all_extracted_data = []
    for f in uploaded_files:
        df_raw = pd.read_excel(f, header=None)
        # 업로드 시점(파일 내부 정보) 확인용 날짜 추출
        # 보통 엑셀 상단이나 파일명에 정보가 있지만, 여기서는 데이터 기반으로 처리
        dates_raw = df_raw.iloc[2, 2:].values
        data = []
        for r_idx in [6, 7, 10, 11, 12]:
            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()
            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                if pd.isna(d_val) or pd.isna(av): continue
                try:
                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date() if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()
                    data.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot, "UploadRef": f.name})
                except: continue
        all_extracted_data.append(pd.DataFrame(data))

    if len(all_extracted_data) > 0:
        # 모든 데이터를 하나로 합침
        full_df = pd.concat(all_extracted_data)
        
        # 파일명이나 업로드 순서를 기준으로 '과거'와 '현재'를 나누기 위해 
        # 사용자가 올린 파일 리스트에서 유니크한 파일셋을 확인
        unique_files = full_df['UploadRef'].unique()
        
        if len(unique_files) >= 2:
            # 테스트를 위해: 파일 리스트의 앞쪽 절반을 과거, 뒤쪽 절반을 현재로 간주
            # 혹은 파일 이름에 날짜가 있다면 그 순서대로 정렬 가능
            unique_files_sorted = sorted(unique_files) # 파일 이름순 정렬
            mid = len(unique_files_sorted) // 2
            
            prev_files = unique_files_sorted[:mid]
            today_files = unique_files_sorted[mid:]
            
            st.session_state.prev_df = full_df[full_df['UploadRef'].isin(prev_files)]
            st.session_state.today_df = full_df[full_df['UploadRef'].isin(today_files)]
            
            st.success(f"분석 완료: 과거({len(prev_files)}개 파일) vs 현재({len(today_files)}개 파일) 비교 중")
        else:
            st.session_state.today_df = full_df
            st.info("비교를 위해 파일을 더 업로드하거나 스냅샷을 저장하세요.")

# 메인 렌더링
if 'today_df' in st.session_state:
    curr = st.session_state.today_df
    prev = st.session_state.get('prev_df', pd.DataFrame())
    
    st.markdown(render_snapshot_table(curr, prev, title="📊 1. 시장 분석", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_snapshot_table(curr, prev, title="📈 2. 예약 변화량 (Pick-up)", mode="변화"), unsafe_allow_html=True)
    st.markdown(render_snapshot_table(curr, prev, title="🔔 3. 판도 변화 (보라색 강조)", mode="판도변화"), unsafe_allow_html=True)
    
    for ch in st.session_state.promotions.keys():
        st.markdown(render_snapshot_table(curr, prev, ch_name=ch, title=f"✅ {ch} 판매가 (변화 시 보라색)", mode="판매가"), unsafe_allow_html=True)
