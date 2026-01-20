import streamlit as st

import pandas as pd

from datetime import datetime

import firebase_admin

from firebase_admin import credentials, firestore

import math



# --- 1. 파이버베이스 초기화 ---

if not firebase_admin._apps:

    try:

        fb_dict = st.secrets["firebase"]

        cred = credentials.Certificate(dict(fb_dict))

        firebase_admin.initialize_app(cred)

    except Exception as e:

        st.error(f"파이어베이스 연결 실패: {e}")

db = firestore.client()



# --- 2. 전역 설정 (유채색 판도 컬러) ---

ALERT_BAR_COLORS = {

    "BAR1": "#FF0000", "BAR2": "#FF8C00", "BAR3": "#FFD166", "BAR4": "#DAF7A6",

    "BAR5": "#2ECC71", "BAR6": "#3498DB", "BAR7": "#0000FF", "BAR8": "#BDC3C7",

}

WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']

ROOM_IDS = ["FDB", "FDE", "HDP", "HDT", "HDF"]



PRICE_TABLE = {

    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},

    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},

    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},

    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},

    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},

}



# --- 3. 상태 관리 (채널 리스트) ---

if 'channel_list' not in st.session_state:

    st.session_state.channel_list = ["네이버"]



if 'promotions' not in st.session_state:

    st.session_state.promotions = {

        "네이버": {rid: {"name": f"네이버_{rid}", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}

    }



# --- 4. 로직 함수 ---

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



def get_snapshot_by_date(selected_date):

    date_str = selected_date.strftime("%Y-%m-%d")

    docs = db.collection("daily_snapshots").where("work_date", "==", date_str).limit(1).stream()

    for doc in docs:

        df = pd.DataFrame(doc.to_dict()['data'])

        df['Date'] = pd.to_datetime(df['Date']).dt.date

        return df

    return pd.DataFrame()



# --- 5. 메인 렌더러 (HTML) ---

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

        if mode == "판매가":

            p_name = st.session_state.promotions[ch_name][rid]['name']

            label = f"<b>{rid}</b><br><small style='color:blue;'>{p_name}</small>"

        html += f"<tr><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000;'>{label}</td>"

        

        for d in dates:

            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]

            if curr_match.empty:

                html += "<td style='border:1px solid #ddd;'>-</td>"; continue

            

            curr_row = curr_match.iloc[0]

            occ, bar, base_price = determine_values(rid, d, curr_row['Available'], curr_row['Total'])

            style = "border:1px solid #ddd; padding:8px; text-align:center; background-color:white;"

            content = "-"



            prev_bar = None

            if not prev_df.empty:

                prev_m = prev_df[(prev_df['RoomID'] == rid) & (pd.to_datetime(prev_df['Date']).dt.date == d)]

                if not prev_m.empty: _, prev_bar, _ = determine_values(rid, d, prev_m.iloc[0]['Available'], prev_m.iloc[0]['Total'])

            

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

                    bg = ALERT_BAR_COLORS.get(bar, "#000")

                    text_c = "white" if bar in ["BAR1", "BAR2", "BAR5", "BAR6", "BAR7"] else "black"

                    style += f"background-color: {bg}; color: {text_c}; font-weight: bold; border: 2.5px solid #000;"

                    content = f"▲ {bar}"

                else: content = bar

            elif mode == "판매가":

                conf = st.session_state.promotions[ch_name][rid]

                final_p = calculate_final_price(base_price, conf['discount_rate'], conf['add_price'])

                content = f"<b>{final_p:,}</b>"

                if is_changed:

                    bg = ALERT_BAR_COLORS.get(bar, "#000")

                    text_c = "white" if bar in ["BAR1", "BAR2", "BAR5", "BAR6", "BAR7"] else "black"

                    style += f"background-color: {bg}; color: {text_c}; font-weight: bold; border: 2.5px solid #333;"



            html += f"<td style='{style}'>{content}</td>"

        html += "</tr>"

    html += "</tbody></table>"

    return html



# --- 6. UI 구성 ---

st.set_page_config(layout="wide")

st.title("🏨 엠버퓨어힐 무제한 채널 확장 RMS")



with st.sidebar:

    st.header("📅 데이터 불러오기")

    compare_date = st.date_input("비교할 과거 날짜 선택", value=datetime.now())

    if st.button("📂 과거 데이터 로드"):

        st.session_state.prev_df = get_snapshot_by_date(compare_date)

        if not st.session_state.prev_df.empty: st.success(f"{compare_date} 로드 완료!")

        else: st.warning("저장된 데이터가 없습니다.")



    st.divider()

    st.header("🎯 채널 무제한 추가")

    new_channel = st.text_input("새 채널 이름 (예: 아고다, 익스피디아)")

    if st.button("➕ 채널 추가"):

        if new_channel and new_channel not in st.session_state.channel_list:

            st.session_state.channel_list.append(new_channel)

            st.session_state.promotions[new_channel] = {rid: {"name": f"{new_channel}_{rid}", "discount_rate": 0, "add_price": 0} for rid in ROOM_IDS}

            st.rerun()



    st.divider()

    st.header("⚙️ 채널별 상세 설정")

    for ch in st.session_state.channel_list:

        with st.expander(f"📦 {ch} 프로모션 설정"):

            for rid in ROOM_IDS:

                st.markdown(f"**[{rid}]**")

                st.session_state.promotions[ch][rid]['name'] = st.text_input(f"명칭", value=st.session_state.promotions[ch][rid]['name'], key=f"{ch}_{rid}_n")

                c1, c2 = st.columns(2)

                st.session_state.promotions[ch][rid]['discount_rate'] = c1.number_input("할인율(%)", value=st.session_state.promotions[ch][rid]['discount_rate'], key=f"{ch}_{rid}_d")

                st.session_state.promotions[ch][rid]['add_price'] = c2.number_input("추가금", value=st.session_state.promotions[ch][rid]['add_price'], step=1000, key=f"{ch}_{rid}_a")



    st.divider()

    uploaded_files = st.file_uploader("오늘자 리포트 업로드", accept_multiple_files=True)

    if st.button("🚀 오늘 데이터 스냅샷 저장"):

        if 'today_df' in st.session_state:

            save_df = st.session_state.today_df.copy()

            save_df['Date'] = save_df['Date'].apply(lambda x: x.isoformat())

            db.collection("daily_snapshots").add({

                "work_date": datetime.now().strftime("%Y-%m-%d"),

                "save_time": datetime.now(),

                "data": save_df.to_dict(orient='records')

            })

            st.success("오늘 데이터 저장 완료!")



# 데이터 처리 로직

if uploaded_files:

    all_temp = []

    for f in uploaded_files:

        df_raw = pd.read_excel(f, header=None)

        dates_raw = df_raw.iloc[2, 2:].values

        for r_idx in [6, 7, 10, 11, 12]:

            rid = str(df_raw.iloc[r_idx, 0]).strip().upper()

            tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')

            for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):

                if pd.isna(d_val) or pd.isna(av):

                    continue

                try:

                    d_obj = (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date() if isinstance(d_val, (int, float)) else datetime.strptime(f"2026-{d_val}", "%Y-%m-%d").date()

                    all_temp.append({"Date": d_obj, "RoomID": rid, "Available": av, "Total": tot})

                except:

                    continue

    st.session_state.today_df = pd.DataFrame(all_temp)



# 메인 화면 출력

if 'today_df' in st.session_state:

    curr = st.session_state.today_df

    prev = st.session_state.get('prev_df', pd.DataFrame())

    

    st.markdown(render_master_table(curr, prev, title="📊 1. 시장 분석 (추천 BAR)", mode="기준"), unsafe_allow_html=True)

    st.markdown(render_master_table(curr, prev, title="📈 2. 예약 변화량 (Pick-up)", mode="변화"), unsafe_allow_html=True)

    st.markdown(render_master_table(curr, prev, title="🔔 3. 판도 변화 (유채색 등급 알림)", mode="판도변화"), unsafe_allow_html=True)

    

    st.header("📲 4. 채널별 최종 판매가 산출 (컬러 연동)")

    # ⭐ 등록된 채널 개수만큼 반복하여 테이블 생성

    for ch in st.session_state.channel_list:

        st.markdown(render_master_table(curr, prev, ch_name=ch, title=f"✅ {ch} 판매가 (공식 적용)", mode="판매가"), unsafe_allow_html=True)
