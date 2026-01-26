import streamlit as st
import pandas as pd
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import math
import re

# --- 1. 파이버베이스 초기화 ---
if not firebase_admin._apps:
    try:
        fb_dict = st.secrets["firebase"]
        cred = credentials.Certificate(dict(fb_dict))
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"파이어베이스 연결 실패: {e}")
db = firestore.client()

# --- 2. 전역 설정 데이터 ---
BAR_GRADIENT_COLORS = {
    "BAR1": "#D32F2F", "BAR2": "#EF5350", "BAR3": "#FF8A65", "BAR4": "#FFB199",
    "BAR5": "#81C784", "BAR6": "#A5D6A7", "BAR7": "#C8E6C9", "BAR8": "#E8F5E9",
}
BAR_LIGHT_COLORS = {
    "BAR1": "#FFEBEE", "BAR2": "#FFEBEE", "BAR3": "#FFF3E0", "BAR4": "#FFF3E0",
    "BAR5": "#E8F5E9", "BAR6": "#E8F5E9", "BAR7": "#F1F8E9", "BAR8": "#F1F8E9",
}
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
DYNAMIC_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF"]
FIXED_ROOMS = ["GDB", "GDF", "FFD", "FPT", "PPV"]
ALL_ROOMS = DYNAMIC_ROOMS + FIXED_ROOMS

PRICE_TABLE = {
    "FDB": {"BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDT": {"BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}
FIXED_PRICE_TABLE = {
    "GDB": {"UND1": 180000, "UND2": 180000, "MID1": 225000, "MID2": 225000, "UPP1": 285000, "UPP2": 315000},
    "GDF": {"UND1": 375000, "UND2": 375000, "MID1": 410000, "MID2": 410000, "UPP1": 488000, "UPP2": 488000},
    "FFD": {"UND1": 353000, "UND2": 353000, "MID1": 445000, "MID2": 445000, "UPP1": 567000, "UPP2": 567000},
    "FPT": {"UND1": 500000, "UND2": 550000, "MID1": 600000, "MID2": 650000, "UPP1": 700000, "UPP2": 750000},
    "PPV": {"UND1": 1100000, "UND2": 1100000, "MID1": 1250000, "MID2": 1250000, "UPP1": 1400000, "UPP2": 1400000},
}

# --- 3. 로직 함수 ---
def get_season_details(date_obj):
    m, d = date_obj.month, date_obj.day
    md = f"{m:02d}.{d:02d}"
    actual_is_weekend = date_obj.weekday() in [4, 5]
    if ("02.13" <= md <= "02.18") or ("09.23" <= md <= "09.28"):
        season, is_weekend = "UPP", True
    elif ("12.21" <= md <= "12.31") or ("10.01" <= md <= "10.08"):
        season, is_weekend = "UPP", False
    elif ("05.03" <= md <= "05.05") or ("05.24" <= md <= "05.26") or ("06.05" <= md <= "06.07"):
        season, is_weekend = "MID", True
    elif "07.17" <= md <= "08.29":
        season, is_weekend = "UPP", actual_is_weekend
    elif ("01.04" <= md <= "03.31") or ("11.01" <= md <= "12.20"):
        season, is_weekend = "UND", actual_is_weekend
    else:
        season, is_weekend = "MID", actual_is_weekend
    type_code = f"{season}{'2' if is_weekend else '1'}"
    return type_code, season, is_weekend

def determine_bar(season, is_weekend, occ):
    if season == "UPP":
        if is_weekend:
            if occ >= 81: return "BAR1"
            elif occ >= 51: return "BAR2"
            elif occ >= 31: return "BAR3"
            else: return "BAR4"
        else:
            if occ >= 81: return "BAR2"
            elif occ >= 51: return "BAR3"
            elif occ >= 31: return "BAR4"
            else: return "BAR5"
    elif season == "MID":
        if is_weekend:
            if occ >= 81: return "BAR3"
            elif occ >= 51: return "BAR4"
            elif occ >= 31: return "BAR5"
            else: return "BAR6"
        else:
            if occ >= 81: return "BAR4"
            elif occ >= 51: return "BAR5"
            elif occ >= 31: return "BAR6"
            else: return "BAR7"
    else: # UND
        if is_weekend:
            if occ >= 81: return "BAR4"
            elif occ >= 51: return "BAR5"
            elif occ >= 31: return "BAR6"
            else: return "BAR7"
        else:
            if occ >= 81: return "BAR5"
            elif occ >= 51: return "BAR6"
            elif occ >= 31: return "BAR7"
            else: return "BAR8"

def get_final_values(room_id, date_obj, avail, total):
    type_code, season, is_weekend = get_season_details(date_obj)
    
    # [안전장치] avail이 None이거나 비어있으면 0.0으로 처리
    try: current_avail = float(avail) if pd.notna(avail) else 0.0
    except: current_avail = 0.0
        
    occ = ((total - current_avail) / total * 100) if total > 0 else 0
    
    if room_id in DYNAMIC_ROOMS:
        bar = determine_bar(season, is_weekend, occ)
        price = PRICE_TABLE.get(room_id, {}).get(bar, 0)
    else:
        bar = type_code
        price = FIXED_PRICE_TABLE.get(room_id, {}).get(type_code, 0)
    return occ, bar, price

# --- 4. 렌더러 ---
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준"):
    if current_df.empty: return "<div style='padding:20px;'>데이터를 업로드하세요.</div>"
    dates = sorted(current_df['Date'].unique())
    
    if mode == "판매가":
        items_to_show = st.session_state.promotions.get(ch_name, {}).get("items", [])
        row_padding = "1px"
        header_padding = "2px"
        line_style = "line-height: 1.0; font-size: 11px;"
        font_size = "11px"
        col_width_style = "min-width: 45px;"
    else:
        items_to_show = ALL_ROOMS
        row_padding = "8px"
        header_padding = "5px"
        line_style = ""
        font_size = "11px"
        col_width_style = ""

    if mode == "판매가" and not items_to_show:
        return f"<div style='padding:10px; color:gray;'>👉 왼쪽 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"

    html = f"<div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; padding:10px; background:#f0f2f6; border-left:10px solid #000;'>{title}</div>"
    html += "<div style='overflow-x: auto; white-space: nowrap; border: 1px solid #ddd;'>"
    html += f"<table style='width:100%; border-collapse:collapse; font-size:{font_size}; min-width:1000px;'><thead><tr style='background:#f9f9f9;'><th rowspan='2' style='border:1px solid #ddd; width:180px; position:sticky; left:0; background:#f9f9f9; z-index:2; padding:{header_padding};'>객실/프로모션</th>"
    for d in dates: html += f"<th style='border:1px solid #ddd; padding:{header_padding}; {col_width_style}'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd=='일' else ("blue" if wd=='토' else "black")
        html += f"<th style='border:1px solid #ddd; padding:{header_padding}; color:{color}; {col_width_style}'>{wd}</th>"
    html += "</tr></thead><tbody>"

    for item in items_to_show:
        if mode == "판매가":
            rid = item.get('객실타입', 'Unknown')
            label_text = item.get('상품명', 'No Name')
            label = f"<b>{rid}</b> <span style='color:blue; margin-left:4px;'>: {label_text}</span>"
            try: discount = float(item.get('할인(%)') or 0)
            except: discount = 0.0
            try: add_price = int(item.get('추가금') or 0)
            except: add_price = 0
        else:
            rid = item
            label = rid
            if rid in ["HDF", "PPV"]: label = f"<b>{rid}</b>"

        border_thick = "border-bottom:3.4px solid #000;" if rid in ["HDF", "PPV"] else ""
        html += f"<tr style='{border_thick}'><td style='border:1px solid #ddd; padding:{row_padding}; background:#fff; border-right:4px solid #000; position:sticky; left:0; z-index:1; {line_style}'>{label}</td>"
        
        for d in dates:
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            
            # [수정] 값이 비어 있어도(empty) 날짜만 있으면 칸을 그림
            if curr_match.empty:
                # 데이터가 아예 없는 날짜라도 "-" 표시하여 칸 유지
                html += f"<td style='border:1px solid #ddd; padding:{row_padding}; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            occ, bar, base_price = get_final_values(rid, d, avail, total)
            
            prev_bar, prev_avail = None, None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    prev_avail = prev_m.iloc[0]['Available']
                    _, prev_bar, _ = get_final_values(rid, d, prev_avail, prev_m.iloc[0]['Total'])

            style = f"border:1px solid #ddd; padding:{row_padding}; text-align:center; background-color:white; {line_style}"
            
            if mode == "기준":
                bg = BAR_GRADIENT_COLORS.get(bar, "#FFFFFF") if rid in DYNAMIC_ROOMS else "#F1F1F1"
                style += f"background-color: {bg};"
                content = f"<b>{bar}</b><br>{base_price:,}<br>{occ:.0f}%"
            
            elif mode == "변화":
                # 안전하게 숫자 변환
                curr_av_safe = float(avail) if pd.notna(avail) else 0.0
                prev_av_safe = float(prev_avail) if (prev_avail is not None and pd.notna(prev_avail)) else 0.0
                
                pickup = (prev_av_safe - curr_av_safe) if prev_avail is not None else 0
                bg = BAR_LIGHT_COLORS.get(bar, "#FFFFFF") if rid in DYNAMIC_ROOMS else "#FFFFFF"
                style += f"background-color: {bg};"
                
                if pickup > 0:
                    style += "color:red; font-weight:bold; border: 1.5px solid red;"
                    content = f"+{pickup:.0f}"
                elif pickup < 0:
                    style += "color:blue; font-weight:bold;"
                    content = f"{pickup:.0f}"
                else: content = "-"
            
            elif mode == "판도변화":
                if prev_bar and prev_bar != bar:
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid #000;"
                    content = f"▲ {bar}"
                else: content = bar
            
            elif mode == "판매가":
                after_disc = base_price * (1 - (discount / 100))
                final_p = int((math.floor(after_disc / 1000) * 1000) + add_price)
                content = f"<b>{final_p:,}</b>"
                if prev_bar and prev_bar != bar:
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid #333;"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html

# --- 5. 파서 및 DB 로직 ---
def robust_date_parser(d_val):
    if pd.isna(d_val): return None
    try:
        if isinstance(d_val, (int, float)): return (pd.to_datetime('1899-12-30') + pd.to_timedelta(d_val, 'D')).date()
        s = str(d_val).strip().replace('.', '-').replace('/', '-').replace(' ', '')
        match = re.search(r'(\d{1,2})-(\d{1,2})', s)
        if match: return date(2026, int(match.group(1)), int(match.group(2)))
    except: pass
    return None

def save_channel_configs():
    db.collection("settings").document("channels").set({"channel_list": st.session_state.channel_list, "promotions": st.session_state.promotions})

def load_channel_configs():
    doc = db.collection("settings").document("channels").get()
    if doc.exists:
        d = doc.to_dict()
        st.session_state.channel_list = d.get("channel_list", [])
        st.session_state.promotions = d.get("promotions", {})
    else:
        st.session_state.channel_list = []
        st.session_state.promotions = {}

def get_latest_snapshot():
    docs = db.collection("daily_snapshots").order_by("save_time", direction=firestore.Query.DESCENDING).limit(1).stream()
    for doc in docs:
        d_dict = doc.to_dict()
        df = pd.DataFrame(d_dict['data'])
        if not df.empty and 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df, d_dict.get('work_date', '알수없음')
    return pd.DataFrame(), None

# --- 6. 메인 UI ---
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략 통합 수익관리 시스템")

if 'channel_list' not in st.session_state: load_channel_configs()
if 'today_df' not in st.session_state: st.session_state.today_df = pd.DataFrame()
if 'prev_df' not in st.session_state: st.session_state.prev_df = pd.DataFrame()
if 'compare_label' not in st.session_state: st.session_state.compare_label = ""

with st.sidebar:
    st.header("📅 수정 내역 조회")
    work_day = st.date_input("조회 날짜", value=date.today())
    if st.button("📂 과거 기록 보기"):
        docs = db.collection("daily_snapshots").where("work_date", "==", work_day.strftime("%Y-%m-%d")).limit(1).stream()
        found = False
        for doc in docs:
            d_dict = doc.to_dict()
            
            st.session_state.today_df = pd.DataFrame(d_dict['data'])
            if not st.session_state.today_df.empty and 'Date' in st.session_state.today_df.columns:
                st.session_state.today_df['Date'] = pd.to_datetime(st.session_state.today_df['Date']).dt.date
            
            if 'prev_data' in d_dict and d_dict['prev_data']:
                st.session_state.prev_df = pd.DataFrame(d_dict['prev_data'])
                if not st.session_state.prev_df.empty and 'Date' in st.session_state.prev_df.columns:
                    st.session_state.prev_df['Date'] = pd.to_datetime(st.session_state.prev_df['Date']).dt.date
            else:
                st.session_state.prev_df = pd.DataFrame()

            if 'saved_promotions' in d_dict:
                st.session_state.promotions = d_dict['saved_promotions']
                st.session_state.channel_list = d_dict.get('saved_channel_list', [])
            
            st.session_state.compare_label = f"불러온 과거 기록: {work_day}"
            found = True
        if found: st.success("로드 완료")
        else: st.warning("데이터 없음")

    st.divider()
    st.header("🎯 채널 & 상품 관리 (이지 에디터)")
    new_ch = st.text_input("새 채널 명칭")
    if st.button("➕ 채널 추가"):
        if new_ch and new_ch not in st.session_state.channel_list:
            st.session_state.channel_list.append(new_ch)
            st.session_state.promotions[new_ch] = {"items": []}
            save_channel_configs(); st.rerun()

    for ch in st.session_state.channel_list:
        with st.expander(f"📦 {ch} 상품 편집"):
            if st.button(f"❌ {ch} 채널 삭제", key=f"del_{ch}"):
                st.session_state.channel_list.remove(ch)
                st.session_state.promotions.pop(ch, None)
                save_channel_configs(); st.rerun()
            
            st.info("아래 표에서 바로 수정/추가/삭제 하세요.")
            current_items = st.session_state.promotions[ch].get("items", [])
            df_editor = pd.DataFrame(current_items)
            
            if df_editor.empty:
                df_editor = pd.DataFrame(columns=["객실타입", "상품명", "할인(%)", "추가금"])

            edited_df = st.data_editor(
                df_editor,
                num_rows="dynamic",
                column_config={
                    "객실타입": st.column_config.SelectboxColumn(options=ALL_ROOMS, required=True),
                    "상품명": st.column_config.TextColumn(required=True),
                    "할인(%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=1),
                    "추가금": st.column_config.NumberColumn(step=1000, format="%d")
                },
                key=f"editor_{ch}",
                use_container_width=True
            )

            if st.button(f"💾 {ch} 설정 저장", key=f"save_{ch}"):
                updated_items = edited_df.to_dict(orient="records")
                st.session_state.promotions[ch]["items"] = updated_items
                save_channel_configs()
                st.success("저장 완료!")

    st.divider()
    files = st.file_uploader("리포트 업로드 (복수 가능)", accept_multiple_files=True)
    if st.button("🚀 오늘 내역 저장"):
        if not st.session_state.today_df.empty:
            t_df = st.session_state.today_df.copy()
            t_df['Date'] = t_df['Date'].apply(lambda x: x.isoformat())
            p_df_dict = []
            if not st.session_state.prev_df.empty:
                p_df = st.session_state.prev_df.copy()
                p_df['Date'] = p_df['Date'].apply(lambda x: x.isoformat())
                p_df_dict = p_df.to_dict(orient='records')
            db.collection("daily_snapshots").add({
                "work_date": date.today().strftime("%Y-%m-%d"),
                "save_time": datetime.now().isoformat(),
                "data": t_df.to_dict(orient='records'),
                "prev_data": p_df_dict,
                "saved_promotions": st.session_state.promotions,
                "saved_channel_list": st.session_state.channel_list
            })
            st.success("저장 완료!")

# --- 7. 파일 로직 ---
if files:
    all_extracted = []
    ROW_MAP = {4:"GDB", 5:"GDF", 6:"FDB", 7:"FDE", 8:"FPT", 9:"FFD", 10:"HDP", 11:"HDT", 12:"HDF", 13:"PPV"}

    for f in files:
        date_tag = re.search(r'\d{8}', f.name).group() if re.search(r'\d{8}', f.name) else f.name
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values
        
        for r_idx, rid in ROW_MAP.items():
            if r_idx < len(df_raw):
                tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
                for d_val, av in zip(dates_raw, df_raw.iloc[r_idx, 2:].values):
                    d_obj = robust_date_parser(d_val)
                    # [🔴 핵심 수정] 데이터가 비어있어도(NaN) 날짜만 있으면 Skip 안 함
                    if d_obj is None: continue
                    all_extracted.append({"Date": d_obj, "RoomID": rid, "Available": pd.to_numeric(av, errors='coerce'), "Total": tot, "Tag": date_tag})

    if all_extracted:
        full_df = pd.DataFrame(all_extracted)
        tags = sorted(full_df['Tag'].unique())
        
        if len(tags) >= 2:
            st.session_state.today_df = full_df[full_df['Tag'] == tags[-1]].copy()
            st.session_state.prev_df = full_df[full_df['Tag'] == tags[-2]].copy()
            st.session_state.compare_label = f"파일 간 비교: {tags[-2]} vs {tags[-1]}"
        else:
            st.session_state.today_df = full_df.copy()
            if st.session_state.prev_df.empty:
                latest_df, save_dt = get_latest_snapshot()
                if not latest_df.empty:
                    st.session_state.prev_df = latest_df
                    st.session_state.compare_label = f"자동 DB 비교: {save_dt} 저장본"
                else:
                    st.session_state.prev_df = pd.DataFrame()
                    st.session_state.compare_label = "비교 대상 없음"

# --- 8. 메인 출력 ---
if not st.session_state.today_df.empty:
    curr, prev = st.session_state.today_df, st.session_state.prev_df
    
    if st.session_state.compare_label:
        st.info(f"ℹ️ {st.session_state.compare_label}")
        
    st.markdown(render_master_table(curr, prev, title="📊 1. 시장 분석", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="📈 2. 예약 변화량", mode="변화"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="🔔 3. 판도 변화", mode="판도변화"), unsafe_allow_html=True)
    for ch in st.session_state.channel_list:
        st.markdown(render_master_table(curr, prev, ch_name=ch, title=f"✅ {ch} 판매가 산출", mode="판매가"), unsafe_allow_html=True)
