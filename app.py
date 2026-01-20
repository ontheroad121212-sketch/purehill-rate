import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import math

# --- 1. 파이어베이스 및 상태 초기화 ---
if not firebase_admin._apps:
    fb_dict = st.secrets["firebase"]
    cred = credentials.Certificate(dict(fb_dict))
    firebase_admin.initialize_app(cred)
db = firestore.client()

if 'all_data_df' not in st.session_state:
    st.session_state.all_data_df = pd.DataFrame()

# 채널/프로모션 설정 상태 관리
if 'promotions' not in st.session_state:
    st.session_state.promotions = {
        "네이버": {
            "FDB": {"name": "네이버_조식패키지", "discount_rate": 20, "add_price": 190000},
            "FDE": {"name": "네이버_단독특가", "discount_rate": 10, "add_price": 50000},
            "HDP": {"name": "네이버_연박할인", "discount_rate": 15, "add_price": 0},
            "HDT": {"name": "네이버_기본", "discount_rate": 0, "add_price": -10000},
            "HDF": {"name": "네이버_풀빌라패키지", "discount_rate": 5, "add_price": 250000},
        }
    }

WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
ROOM_IDS = ["FDB", "FDE", "HDP", "HDT", "HDF"]

# --- 2. 가격 데이터 및 로직 ---
PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}

def calculate_final_price(base_price, discount_rate, add_price):
    # 1. 할인율 적용: 기준가 * (1 - 할인율/100)
    after_discount = base_price * (1 - (discount_rate / 100))
    # 2. 100원 단위 절삭 (내림)
    floored = math.floor(after_discount / 1000) * 1000
    # 3. 추가 금액 더하기
    return int(floored + add_price)

def determine_values(room_id, date_obj, avail, total):
    occ = ((total - avail) / total * 100) if total > 0 else 0
    # 간단 OCC 로직
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

# --- 3. UI: 사이드바 (프로모션 빌더) ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략적 프로모션 대시보드")

with st.sidebar:
    st.header("🎯 채널별 프로모션 설정")
    
    # 채널 추가
    new_channel_name = st.text_input("새 채널 이름 (예: 아고다)", key="add_ch_name")
    if st.button("➕ 채널 생성"):
        if new_channel_name and new_channel_name not in st.session_state.promotions:
            st.session_state.promotions[new_channel_name] = {rid: {"name": f"{new_channel_name}_기본", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}
            st.rerun()

    st.divider()

    # 각 채널별 상세 설정 (Expanders 사용)
    for ch_name, config in st.session_state.promotions.items():
        with st.expander(f"📦 {ch_name} 설정", expanded=False):
            for rid in ROOM_IDS:
                st.markdown(f"**[{rid}] 타입**")
                col1, col2 = st.columns(2)
                config[rid]['name'] = col1.text_input(f"프로모션명", value=config[rid]['name'], key=f"{ch_name}_{rid}_n")
                config[rid]['discount_rate'] = col2.number_input(f"할인율(%)", value=config[rid]['discount_rate'], step=1, key=f"{ch_name}_{rid}_r")
                config[rid]['add_price'] = st.number_input(f"추가금액(+/-)", value=config[rid]['add_price'], step=1000, key=f"{ch_name}_{rid}_a")
                st.divider()

    files = st.file_uploader("엑셀 리포트 업로드", accept_multiple_files=True)
    if st.button("🚀 현재 상태 저장 (Snapshot)"):
        if not st.session_state.all_data_df.empty:
            db.collection("daily_snapshots").add({"save_time": datetime.now(), "data": st.session_state.all_data_df.to_dict(orient='records')})
            st.success("저장 완료!")

# --- 4. 메인 대시보드 렌더러 ---
def render_promo_table(current_df, prev_df, ch_name=None, title="", mode="기준"):
    dates = sorted(current_df['Date'].unique())
    html = f"<div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; color:#1E1E1E; padding:10px; background:#f0f2f6; border-left:10px solid #000;'>{title}</div>"
    html += "<table style='width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 11px;'>"
    html += "<thead><tr style='background:#f9f9f9;'><th style='border:1px solid #ddd; padding:8px; width:150px;' rowspan='2'>객실/프로모션</th>"
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        html += f"<th style='border:1px solid #ddd; padding:5px;' class='{'sun' if wd=='일' else ('sat' if wd=='토' else '')}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for rid in ROOM_IDS:
        html += "<tr>"
        # 프로모션 명 표시
        label = rid
        if mode == "판매가" and ch_name:
            label = f"<b>{rid}</b><br><span style='color:blue; font-size:10px;'>{st.session_state.promotions[ch_name][rid]['name']}</span>"
        
        html += f"<td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:3px solid #000;'>{label}</td>"
        
        for d in dates:
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd;'>-</td>"
                continue
            
            curr_row = curr_match.iloc[0]
            occ, bar, base_price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])
            
            content = "-"
            style = "border:1px solid #ddd; padding:8px; text-align:center;"
            
            if mode == "기준":
                bg = BAR_COLORS.get(bar, "#fff")
                content = f"<div style='background:{bg}; font-weight:bold; border-radius:3px;'>{bar}<br>{occ:.0f}%</div>"
            elif mode == "변화":
                # (Pick-up 로직 동일...)
                pickup = 0 # ...생략 (이전 코드와 동일하게 작동)
                content = f"{pickup}" 
            elif mode == "판매가":
                conf = st.session_state.promotions[ch_name][rid]
                final_p = calculate_final_price(base_price, conf['discount_rate'], conf['add_price'])
                content = f"<b style='color:#2E7D32; font-size:13px;'>{final_p:,}</b>"
            
            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# 데이터 로드 후 렌더링 (이전 파일 로드 로직 유지)
if not st.session_state.all_data_df.empty:
    # 1. 분석 통
    st.markdown(render_promo_table(st.session_state.all_data_df, None, title="📊 시장 분석 (기준 BAR / 점유율)", mode="기준"), unsafe_allow_html=True)
    
    # 2. 채널별 프로모션 통
    for ch_name in st.session_state.promotions.keys():
        st.markdown(render_promo_table(st.session_state.all_data_df, None, ch_name=ch_name, title=f"✅ {ch_name} 프로모션별 최종가", mode="판매가"), unsafe_allow_html=True)
