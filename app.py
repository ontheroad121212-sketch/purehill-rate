import streamlit as st
import pandas as pd
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore
import math
import re
import io  # 엑셀 다운로드를 위해 추가됨

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
    "BAR0": "#B71C1C", # 수동 인상 (가장 눈에 띄는 진한 빨강)
    "BAR1": "#D32F2F", "BAR2": "#EF5350", "BAR3": "#FF8A65", "BAR4": "#FFB199",
    "BAR5": "#81C784", "BAR6": "#A5D6A7", "BAR7": "#C8E6C9", "BAR8": "#E8F5E9",
}
BAR_LIGHT_COLORS = {
    "BAR0": "#FFCDD2", 
    "BAR1": "#FFEBEE", "BAR2": "#FFEBEE", "BAR3": "#FFF3E0", "BAR4": "#FFF3E0",
    "BAR5": "#E8F5E9", "BAR6": "#E8F5E9", "BAR7": "#F1F8E9", "BAR8": "#F1F8E9",
}
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
DYNAMIC_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF"]
FIXED_ROOMS = ["GDB", "GDF", "FFD", "FPT", "PPV"]
ALL_ROOMS = DYNAMIC_ROOMS + FIXED_ROOMS

PRICE_TABLE = {
    "FDB": {"BAR0": 802000, "BAR8": 315000, "BAR7": 353000, "BAR6": 396000, "BAR5": 445000, "BAR4": 502000, "BAR3": 567000, "BAR2": 642000, "BAR1": 728000},
    "FDE": {"BAR0": 839000, "BAR8": 352000, "BAR7": 390000, "BAR6": 433000, "BAR5": 482000, "BAR4": 539000, "BAR3": 604000, "BAR2": 679000, "BAR1": 765000},
    "HDP": {"BAR0": 759000, "BAR8": 280000, "BAR7": 318000, "BAR6": 361000, "BAR5": 410000, "BAR4": 467000, "BAR3": 532000, "BAR2": 607000, "BAR1": 693000},
    "HDT": {"BAR0": 729000, "BAR8": 250000, "BAR7": 288000, "BAR6": 331000, "BAR5": 380000, "BAR4": 437000, "BAR3": 502000, "BAR2": 577000, "BAR1": 663000},
    "HDF": {"BAR0": 916000, "BAR8": 420000, "BAR7": 458000, "BAR6": 501000, "BAR5": 550000, "BAR4": 607000, "BAR3": 672000, "BAR2": 747000, "BAR1": 833000},
}
FIXED_PRICE_TABLE = {
    "GDB": {"UND1": 298000, "UND2": 298000, "MID1": 298000, "MID2": 298000, "UPP1": 298000, "UPP2": 298000},
    "GDF": {"UND1": 375000, "UND2": 410000, "MID1": 410000, "MID2": 488000, "UPP1": 488000, "UPP2": 578000},
    "FFD": {"UND1": 353000, "UND2": 393000, "MID1": 433000, "MID2": 482000, "UPP1": 539000, "UPP2": 604000},
    "FPT": {"UND1": 500000, "UND2": 550000, "MID1": 600000, "MID2": 650000, "UPP1": 700000, "UPP2": 750000},
    "PPV": {"UND1": 1104000, "UND2": 1154000, "MID1": 1154000, "MID2": 1304000, "UPP1": 1304000, "UPP2": 1554000},
}
# FIXED 객실용 수동 BAR0 가격 테이블 추가
FIXED_BAR0_TABLE = {"GDB": 298000, "GDF": 678000, "FFD": 704000, "FPT": 850000, "PPV": 1704000}

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

def get_final_values(room_id, date_obj, avail, total, manual_bar=None):
    type_code, season, is_weekend = get_season_details(date_obj)
    try: current_avail = float(avail) if pd.notna(avail) else 0.0
    except: current_avail = 0.0
    occ = ((total - current_avail) / total * 100) if total > 0 else 0
    
    # [핵심] 수동 오버라이드 로직 처리
    if manual_bar:
        bar = manual_bar
        if bar == "BAR0":
            if room_id in DYNAMIC_ROOMS: price = PRICE_TABLE.get(room_id, {}).get("BAR0", 0)
            else: price = FIXED_BAR0_TABLE.get(room_id, 0)
        else:
            if room_id in DYNAMIC_ROOMS: price = PRICE_TABLE.get(room_id, {}).get(bar, 0)
            else: price = FIXED_PRICE_TABLE.get(room_id, {}).get(bar, 0)
        return occ, bar, price, True # is_manual = True

    if room_id in DYNAMIC_ROOMS:
        bar = determine_bar(season, is_weekend, occ)
        price = PRICE_TABLE.get(room_id, {}).get(bar, 0)
    else:
        bar = type_code
        price = FIXED_PRICE_TABLE.get(room_id, {}).get(type_code, 0)
    return occ, bar, price, False # is_manual = False

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
        return f"<div style='padding:10px; color:gray;'>👉 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"

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
            if curr_match.empty:
                html += f"<td style='border:1px solid #ddd; padding:{row_padding}; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            
            # [핵심] 권장 요금(시스템 계산) 먼저 산출
            occ, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total, None)
            
            # [핵심] 실제 세팅 요금(수동 입력) 확인
            override_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
            m_bar = st.session_state.get('manual_bars', {}).get(override_key)
            
            if m_bar:
                _, final_bar, final_price, _ = get_final_values(rid, d, avail, total, m_bar)
                is_manual = True
            else:
                final_bar = rec_bar
                final_price = rec_price
                is_manual = False
            
            prev_bar, prev_avail = None, None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    prev_avail = prev_m.iloc[0]['Available']
                    p_m_bar = st.session_state.get('manual_bars', {}).get(override_key)
                    # 이전 데이터도 동일하게 세팅 요금 반영 여부 확인
                    if p_m_bar: _, prev_bar, _, _ = get_final_values(rid, d, prev_avail, prev_m.iloc[0]['Total'], p_m_bar)
                    else: _, prev_bar, _, _ = get_final_values(rid, d, prev_avail, prev_m.iloc[0]['Total'], None)

            style = f"border:1px solid #ddd; padding:{row_padding}; text-align:center; background-color:white; {line_style}"
            
            if mode == "기준":
                if is_manual and final_bar != rec_bar:
                    bg = "#FFF9C4" # 권장과 실제가 다름 (연노랑)
                    style += f"background-color: {bg}; border: 2.5px solid #FF9800;"
                    content = f"<span style='color:#E65100; font-size:10px; font-weight:bold;'>권장: {rec_bar}</span><br><b style='color:blue;'>실제: {final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
                elif is_manual and final_bar == rec_bar:
                    bg = "#E8F5E9" # 권장과 실제가 같고 확정됨 (연초록)
                    style += f"background-color: {bg}; border: 2.5px solid #4CAF50;"
                    content = f"<span style='color:#2E7D32; font-size:10px; font-weight:bold;'>✅ 확정</span><br><b>{final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
                else:
                    bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or final_bar == "BAR0" else "#F1F1F1"
                    style += f"background-color: {bg};"
                    content = f"<b>{final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
            
            elif mode == "변화":
                curr_av_safe = float(avail) if pd.notna(avail) else 0.0
                prev_av_safe = float(prev_avail) if (prev_avail is not None and pd.notna(prev_avail)) else 0.0
                pickup = (prev_av_safe - curr_av_safe) if prev_avail is not None else 0
                bg = BAR_LIGHT_COLORS.get(final_bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or final_bar == "BAR0" else "#FFFFFF"
                style += f"background-color: {bg};"
                if pickup > 0:
                    style += "color:red; font-weight:bold; border: 1.5px solid red;"
                    content = f"+{pickup:.0f}"
                elif pickup < 0:
                    style += "color:blue; font-weight:bold;"
                    content = f"{pickup:.0f}"
                else: content = "-"
            
            elif mode == "판도변화":
                curr_b_str = str(final_bar).strip() if final_bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                
                if prev_bar is not None and prev_b_str != curr_b_str:
                    bg = BAR_GRADIENT_COLORS.get(final_bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid #000;"
                    content = f"▲ {final_bar}"
                else: 
                    content = final_bar
                    
            elif mode == "판매가":
                try:
                    b_price = float(final_price) if final_price is not None else 0
                    d_rate = float(discount) if discount is not None else 0
                    a_price = float(add_price) if add_price is not None else 0
                    
                    after_disc = b_price * (1 - (d_rate / 100))
                    final_p = int((math.floor(after_disc / 1000) * 1000) + a_price)
                    
                    if is_manual and final_bar != rec_bar:
                        style += "background-color: #FFF9C4; border: 2.5px dashed #FF9800;"
                        content = f"<span style='color:#E65100; font-size:10px; font-weight:bold;'>권장: {rec_bar}</span><br><b>{final_p:,}</b>"
                    elif is_manual and final_bar == rec_bar:
                        style += "background-color: #E8F5E9; border: 2.5px solid #4CAF50;"
                        content = f"<span style='color:#2E7D32; font-size:10px; font-weight:bold;'>✅ 확정</span><br><b>{final_p:,}</b>"
                    else:
                        content = f"<b>{final_p:,}</b>"
                    
                except (ValueError, TypeError, ZeroDivisionError):
                    content = "<b>-</b>"

                curr_b_str = str(final_bar).strip() if final_bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                
                if prev_bar is not None and prev_b_str != curr_b_str:
                    bg = BAR_GRADIENT_COLORS.get(final_bar, "#7000FF")
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
if 'manual_bars' not in st.session_state: st.session_state.manual_bars = {} # 수동 오버라이드 상태

with st.sidebar:
    st.header("📅 수정 내역 조회 (History)")
    
    # [새로운 캘린더 시각화 로직] 업데이트된 일자들을 태그 형태로 직관적 표시
    try:
        all_docs = db.collection("daily_snapshots").select(["work_date"]).stream()
        saved_dates = sorted(list(set([d.to_dict().get('work_date', '') for d in all_docs if d.to_dict().get('work_date')])))
        if saved_dates:
            st.markdown("**📌 데이터가 저장된 날짜 (최근 14일)**")
            tags = "".join([f"<span style='background:#E8F5E9; border:1px solid #4CAF50; color:#2E7D32; padding:3px 8px; border-radius:12px; margin:2px; font-size:12px; display:inline-block; font-weight:bold;'>{d[5:]} ✅</span>" for d in saved_dates[-14:]])
            st.markdown(f"<div style='margin-bottom: 10px;'>{tags}</div>", unsafe_allow_html=True)
    except Exception:
        pass

    work_day = st.date_input("조회 날짜", value=date.today())
    if st.button("📂 과거 기록 불러오기"):
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
            
            # 수동 바 로드
            st.session_state.manual_bars = d_dict.get('saved_manual_bars', {})
            
            st.session_state.compare_label = f"불러온 과거 기록: {work_day}"
            found = True
        if found: st.success("역사적 스냅샷 로드 완료")
        else: st.warning("해당 날짜의 데이터가 없습니다.")

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
            
            st.info("표에서 바로 수정/추가/삭제 하세요.")
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
                st.success("저장 완료! 표에 즉시 반영됩니다.")

    st.divider()
    files = st.file_uploader("리포트 업로드 (부분 수정 가능)", accept_multiple_files=True)
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
                "saved_channel_list": st.session_state.channel_list,
                "saved_manual_bars": st.session_state.manual_bars # 수동 저장 내역 포함
            })
            st.success("저장 완료!")

# --- 7. 파일 로직 (스마트 병합) ---
if files:
    new_extracted = []
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
                    if d_obj is None: continue
                    new_extracted.append({"Date": d_obj, "RoomID": rid, "Available": pd.to_numeric(av, errors='coerce'), "Total": tot, "Tag": date_tag})

    if new_extracted:
        new_df = pd.DataFrame(new_extracted)
        
        if st.session_state.prev_df.empty:
            latest_db, save_dt = get_latest_snapshot()
            if not latest_db.empty:
                combined = pd.concat([new_df, latest_db]).drop_duplicates(subset=['Date', 'RoomID'], keep='first')
                st.session_state.today_df = combined.sort_values(by=['Date', 'RoomID'])
                st.session_state.prev_df = latest_db
                st.session_state.compare_label = f"자동 DB 병합/비교: {save_dt} 기준"
            else:
                st.session_state.today_df = new_df
                st.session_state.prev_df = pd.DataFrame()
                st.session_state.compare_label = "비교 대상 없음 (신규)"
        else:
            combined = pd.concat([new_df, st.session_state.today_df]).drop_duplicates(subset=['Date', 'RoomID'], keep='first')
            st.session_state.today_df = combined.sort_values(by=['Date', 'RoomID'])

# --- 8. 메인 출력 ---
if not st.session_state.today_df.empty:
    curr, prev = st.session_state.today_df, st.session_state.prev_df
    
    if st.session_state.compare_label:
        st.info(f"ℹ️ {st.session_state.compare_label}")
        
    st.markdown(render_master_table(curr, prev, title="📊 1. 시장 분석", mode="기준"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="📈 2. 예약 변화량", mode="변화"), unsafe_allow_html=True)
    st.markdown(render_master_table(curr, prev, title="🔔 3. 판도 변화", mode="판도변화"), unsafe_allow_html=True)

# === [수정 사항] 수기 입력 최소화! 스마트 락 & 언락 시스템 ===
    with st.expander("🛠️ 전략적 요금 컨트롤 타워 (수기입력 최소화)", expanded=False):
        st.write("※ 엑셀 업로드 후, 아래 순서대로 클릭하면 수기 입력 없이 요금을 통제할 수 있습니다.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🔒 1단계: 기존 요금 방어")
            st.caption("어제 팔던 요금 그대로 전체 락(Lock)을 겁니다. (재고가 줄어서 권장 요금이 올라도 안 따라감)")
            if st.button("🛡️ 어제 실제 요금으로 전체 동결", use_container_width=True):
                new_manual_bars = st.session_state.get('manual_bars', {}).copy()
                if not st.session_state.prev_df.empty:
                    for idx, row in st.session_state.today_df.iterrows():
                        d = row['Date']
                        rid = row['RoomID']
                        o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                        
                        # 어제 데이터에서 실제 팔던 요금(최종 BAR) 추적
                        prev_m = st.session_state.prev_df[(st.session_state.prev_df['RoomID'] == rid) & (st.session_state.prev_df['Date'] == d)]
                        if not prev_m.empty:
                            p_avail = prev_m.iloc[0]['Available']
                            p_total = prev_m.iloc[0]['Total']
                            p_m_bar = st.session_state.get('manual_bars', {}).get(o_key)
                            _, prev_actual_bar, _, _ = get_final_values(rid, d, p_avail, p_total, p_m_bar)
                            
                            # 어제 요금으로 수동 개입(manual_bars)을 덮어씌워버림 = 동결
                            new_manual_bars[o_key] = prev_actual_bar
                    st.session_state.manual_bars = new_manual_bars
                    st.success("✅ 전체 날짜가 어제 요금으로 동결되었습니다!")
                    st.rerun()
                else:
                    st.warning("과거 기록이 없어 동결할 수 없습니다. (신규 데이터)")

        with col2:
            st.markdown("#### ✨ 2단계: 특정일 인상/수정")
            st.caption("총지배인님 지시 등으로 새 시스템 요금을 적용할 날짜만 고르세요.")
            dates_list = sorted(st.session_state.today_df['Date'].unique())
            selected_dates = st.multiselect("적용할 날짜 선택", options=dates_list, format_func=lambda x: x.strftime('%m-%d'), label_visibility="collapsed")
            
            if st.button("🚀 선택한 날짜만 새 요금으로 락 해제", use_container_width=True):
                if selected_dates:
                    current_manual_bars = st.session_state.manual_bars.copy()
                    for d in selected_dates:
                        for rid in ALL_ROOMS:
                            o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                            # 해당 날짜의 락을 지워버림 -> 오늘 계산된 권장 요금으로 자연스럽게 따라감
                            current_manual_bars.pop(o_key, None)
                    st.session_state.manual_bars = current_manual_bars
                    st.success(f"✅ {len(selected_dates)}일치 요금이 새 권장 요금으로 업데이트 되었습니다!")
                    st.rerun()
                else:
                    st.warning("날짜를 먼저 선택해주세요.")
                    
        st.divider()
        st.write("📝 **3단계 (옵션): 개별 수기 직접 입력** (특정 객실을 완전히 다른 요금으로 뺄 때만 쓰세요)")
        
        matrix_data = []
        for rid in ALL_ROOMS:
            row_data = {"객실": rid}
            for d in dates_list:
                o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                row_data[d.strftime('%m-%d')] = st.session_state.get('manual_bars', {}).get(o_key, "")
            matrix_data.append(row_data)
            
        ed_df = pd.DataFrame(matrix_data)
        col_config = {"객실": st.column_config.TextColumn(disabled=True)}
        edited_matrix = st.data_editor(ed_df, use_container_width=True, hide_index=True, column_config=col_config)
        
        if st.button("💾 표 수기입력 내용 저장", use_container_width=True):
            new_manual_bars = st.session_state.manual_bars.copy()
            for idx, row in edited_matrix.iterrows():
                rid = row["객실"]
                for d in dates_list:
                    val = str(row[d.strftime('%m-%d')]).strip()
                    o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                    if val and val.upper() not in ["NONE", "NAN", ""]:
                        new_manual_bars[o_key] = val.upper()
                    else:
                        # 사용자가 에디터에서 값을 지우면 락 해제
                        new_manual_bars.pop(o_key, None)
            st.session_state.manual_bars = new_manual_bars
            st.success("수기 입력 내역이 저장되었습니다.")
            st.rerun()

    st.divider()

    for ch in st.session_state.channel_list:
        st.markdown(render_master_table(curr, prev, ch_name=ch, title=f"✅ {ch} 판매가 산출", mode="판매가"), unsafe_allow_html=True)

    st.divider()
    
    # --- 엑셀 다운로드 기능 ---
    st.subheader("📥 데이터 엑셀 다운로드")
    st.write("현재 화면에 계산된(수동 변경 포함) 최종 데이터 리스트를 엑셀 파일로 다운로드합니다.")
    
    def generate_excel():
        output = io.BytesIO()
        export_data = []
        for idx, row in st.session_state.today_df.iterrows():
            d = row['Date']
            rid = row['RoomID']
            o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
            # 엑셀 다운로드에는 관리자가 수동으로 개입한 최종 전략 값이 반영되도록 설정
            m_bar = st.session_state.get('manual_bars', {}).get(o_key)
            occ, bar, b_price, is_man = get_final_values(rid, d, row['Available'], row['Total'], m_bar)
            export_data.append({
                "날짜": d.strftime('%Y-%m-%d'),
                "객실타입": rid,
                "잔여객실": row['Available'],
                "전체객실": row['Total'],
                "점유율(%)": round(occ, 1),
                "적용BAR": bar,
                "판매가": b_price,
                "수동개입": "O" if is_man else ""
            })
        df_export = pd.DataFrame(export_data)
        with pd.ExcelWriter(output) as writer:
            df_export.to_excel(writer, index=False, sheet_name='시장분석데이터')
        return output.getvalue()

    st.download_button(
        label="📊 엑셀 다운로드 실행",
        data=generate_excel(),
        file_name=f"AmberPureHill_Report_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
