import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
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

# --- 2-A. 오늘 날짜 기준 ---
TODAY = date.today()

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

def date_filter_toggle(key_prefix, total_dates, default_show_past=False):
    """과거 날짜 표시 토글. True면 전체, False면 오늘 이후만"""
    past_count = sum(1 for d in total_dates if d < TODAY)
    future_count = len(total_dates) - past_count
    
    if past_count == 0:
        return total_dates  # 과거 없으면 그대로
    
    show_past = st.checkbox(
        f"📜 과거 {past_count}일 포함 (현재 미래 {future_count}일만 표시)",
        value=default_show_past,
        key=f"show_past_{key_prefix}"
    )
    
    if show_past:
        return total_dates
    else:
        return [d for d in total_dates if d >= TODAY]

def filter_df_by_dates(df, visible_dates):
    """DataFrame을 보이는 날짜만 필터링"""
    if df.empty:
        return df
    return df[df['Date'].isin(visible_dates)].copy()

# --- 4. 렌더러 ---
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준", applied_rates=None):
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

    bg_title_color = "#E3F2FD" if mode == "최종결과" else "#f0f2f6"
    border_title_color = "#1976D2" if mode == "최종결과" else "#000"

    html = f"<div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; padding:10px; background:{bg_title_color}; border-left:10px solid {border_title_color};'>{title}</div>"
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
            
            # [핵심 로직] mode가 "판매가"일 때만 manual_bar를 가져오고, 나머지는 시스템 원본 사용
            override_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
            m_bar = st.session_state.get('manual_bars', {}).get(override_key) if mode == "판매가" else None
            occ, bar, base_price, is_manual = get_final_values(rid, d, avail, total, m_bar)
            
            prev_bar, prev_avail = None, None
            if not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    prev_avail = prev_m.iloc[0]['Available']
                    p_m_bar = st.session_state.get('manual_bars', {}).get(override_key) if mode == "판매가" else None
                    _, prev_bar, _, _ = get_final_values(rid, d, prev_avail, prev_m.iloc[0]['Total'], p_m_bar)

            style = f"border:1px solid #ddd; padding:{row_padding}; text-align:center; background-color:white; {line_style}"
            
            if mode == "기준":
                bg = BAR_GRADIENT_COLORS.get(bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or bar == "BAR0" else "#F1F1F1"
                style += f"background-color: {bg};"
                # 기준 모드에서는 원본 데이터 표시만 수행 (is_manual 분기 제거)
                content = f"<b>{bar}</b><br>{base_price:,}<br>{occ:.0f}%"
                
            elif mode == "최종결과":
                # 1-A 모드: 시스템 권장가(bar) 위에 전략 적용가(applied_bar)를 덮어씌워서 렌더링
                applied_bar = applied_rates.get(d.strftime('%Y-%m-%d'), {}).get('rooms', {}).get(rid) if applied_rates else None
                final_bar = applied_bar if applied_bar else bar
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or final_bar == "BAR0" else "#F1F1F1"
                
                if applied_bar:
                    final_price = get_bar_price(rid, final_bar)
                    style += f"background-color: {bg}; border: 2.5px solid #2E7D32;"
                    content = f"⭐ <b>{final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
                else:
                    style += f"background-color: {bg}; opacity: 0.9;"
                    content = f"<b>{final_bar}</b><br>{base_price:,}<br>{occ:.0f}%"
            
            elif mode == "변화":
                curr_av_safe = float(avail) if pd.notna(avail) else 0.0
                prev_av_safe = float(prev_avail) if (prev_avail is not None and pd.notna(prev_avail)) else 0.0
                pickup = (prev_av_safe - curr_av_safe) if prev_avail is not None else 0
                bg = BAR_LIGHT_COLORS.get(bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or bar == "BAR0" else "#FFFFFF"
                style += f"background-color: {bg};"
                if pickup > 0:
                    style += "color:red; font-weight:bold; border: 1.5px solid red;"
                    content = f"+{pickup:.0f}"
                elif pickup < 0:
                    style += "color:blue; font-weight:bold;"
                    content = f"{pickup:.0f}"
                else: content = "-"
            
            elif mode == "판도변화":
                curr_b_str = str(bar).strip() if bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                
                if prev_bar is not None and prev_b_str != curr_b_str:
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid #000;"
                    content = f"▲ {bar}"
                else: 
                    content = bar
                    
            elif mode == "판매가":
                try:
                    b_price = float(base_price) if base_price is not None else 0
                    d_rate = float(discount) if discount is not None else 0
                    a_price = float(add_price) if add_price is not None else 0
                    
                    after_disc = b_price * (1 - (d_rate / 100))
                    final_p = int((math.floor(after_disc / 1000) * 1000) + a_price)
                    content = f"<b>{final_p:,}</b>"
                    
                except (ValueError, TypeError, ZeroDivisionError):
                    content = "<b>-</b>"

                curr_b_str = str(bar).strip() if bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                
                if prev_bar is not None and prev_b_str != curr_b_str:
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid #333;"
                
                # 판매가 산출 모드에서만 수동 조작 표기
                if is_manual:
                    style += "border: 2px dashed #FF0000;"
                    content = f"⭐ {content}"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html

# --- 4-A. 적용 요금 관리 (applied_rates) ---
@st.cache_data(ttl=60)
def load_applied_rates():
    """Firebase에서 적용 이력 로드. 키는 'YYYY-MM-DD' 형식"""
    try:
        docs = db.collection("applied_rates").stream()
        result = {}
        for doc in docs:
            d = doc.to_dict()
            result[doc.id] = d
        return result
    except Exception:
        return {}

def save_applied_rate(target_date_str, applied_data, memo=""):
    """
    특정 날짜에 적용된 요금 저장
    target_date_str: '2026-04-25' 형식
    applied_data: {'FDB': 'BAR5', 'FDE': 'BAR5', ...}
    """
    try:
        db.collection("applied_rates").document(target_date_str).set({
            'applied_date': target_date_str,
            'applied_at': datetime.now().isoformat(),
            'applied_at_display': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'memo': memo,
            'rooms': applied_data,
        })
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"적용 저장 실패: {e}")
        return False

def delete_applied_rate(target_date_str):
    try:
        db.collection("applied_rates").document(target_date_str).delete()
        st.cache_data.clear()
        return True
    except:
        return False

def get_applied_bar(target_date_str, room_id, applied_rates):
    """해당 날짜+객실의 적용 BAR 반환. 없으면 None"""
    day_data = applied_rates.get(target_date_str, {})
    rooms = day_data.get('rooms', {})
    return rooms.get(room_id)

def get_bar_price(room_id, bar):
    """BAR 문자열로 가격 조회"""
    if bar == "BAR0":
        if room_id in DYNAMIC_ROOMS:
            return PRICE_TABLE.get(room_id, {}).get("BAR0", 0)
        else:
            return FIXED_BAR0_TABLE.get(room_id, 0)
    if room_id in DYNAMIC_ROOMS:
        return PRICE_TABLE.get(room_id, {}).get(bar, 0)
    else:
        return FIXED_PRICE_TABLE.get(room_id, {}).get(bar, 0)

# --- 4-B. 권장 vs 적용 비교 표 ---
def render_applied_vs_recommend_table(current_df, applied_rates):
    """날짜별 × 객실별 권장 vs 적용 비교 (가로 스크롤 매트릭스 형태로 재작성)"""
    if current_df.empty:
        return "<div style='padding:20px;'>데이터를 업로드하세요.</div>"

    dates = sorted(current_df['Date'].unique())
    
    html = """
    <div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; 
                padding:10px; background:#f0f2f6; border-left:10px solid #FF8F00;'>
        🔍 4. 권장 vs 적용 비교 대조표 (CMS 관리용)
    </div>
    """
    
    html += "<div style='overflow-x:auto; white-space:nowrap; border:1px solid #ddd;'>"
    html += "<table style='width:100%; border-collapse:collapse; font-size:11px; min-width:1000px;'>"
    html += "<thead><tr style='background:#f9f9f9;'>"
    html += "<th rowspan='2' style='border:1px solid #ddd; width:180px; position:sticky; left:0; background:#f9f9f9; z-index:2; padding:5px;'>객실</th>"
    for d in dates: 
        html += f"<th style='border:1px solid #ddd; padding:5px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd == '일' else ("blue" if wd == '토' else "black")
        html += f"<th style='border:1px solid #ddd; padding:5px; color:{color};'>{wd}</th>"
    html += "</tr></thead><tbody>"

    # Dynamic 객실만 비교 대상
    for rid in DYNAMIC_ROOMS:
        html += f"<tr><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000; position:sticky; left:0; z-index:1;'><b>{rid}</b></td>"
        
        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd; padding:8px; text-align:center;'>-</td>"
                continue
            
            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            _, rec_bar, _, _ = get_final_values(rid, d, avail, total)
            
            applied_info = applied_rates.get(date_str, {})
            applied_bar = applied_info.get('rooms', {}).get(rid)
            memo = applied_info.get('memo', '')
            applied_at = applied_info.get('applied_at_display', '')
            
            # 메모를 툴팁으로 처리
            memo_text = f"📝 메모: {memo} | ⏰ 반영: {applied_at}" if memo or applied_at else ""
            tooltip = f"title='{memo_text}'" if memo_text else ""
            
            if not applied_bar:
                style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #FAFAFA; color: #999;"
                content = f"<span style='font-size:9px;'>대기중</span><br>{rec_bar}"
            elif applied_bar == rec_bar:
                style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #E8F5E9; color: #2E7D32;"
                content = f"✅ <b>{applied_bar}</b>"
            else:
                style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #FFF3E0; color: #C62828; border: 1.5px dashed #FF8F00;"
                content = f"<span style='font-size:10px;text-decoration:line-through;color:#999;'>{rec_bar}</span><br>⭐ <b>{applied_bar}</b>"
                
            html += f"<td style='{style}' {tooltip}>{content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html

# --- 4-C. 요금 적용 UI (시장분석 형태) ---
def render_apply_rate_ui(current_df, applied_rates):
    """날짜 찍어서 요금 적용하는 에디터 - 시장분석 스타일"""
    if current_df.empty:
        return
    
    st.markdown("""
    <div style='margin-top:40px; margin-bottom:15px; font-weight:bold; font-size:18px; 
                padding:10px; background:#FFF3E0; border-left:10px solid #FF6F00;'>
        ⏰ 5. 요금 적용 (CMS 반영 기록)
    </div>
    """, unsafe_allow_html=True)
    
    st.caption("🔧 시장분석처럼 격자 형태로 편집 → 수정 후 저장하면 CMS 적용 기록으로 저장됩니다.")
    
    all_dates_full = sorted(current_df['Date'].unique())
    today = date.today()
    
    # 적용 UI는 기본적으로 '오늘 이후'만 대상
    include_past = st.checkbox(
        "📜 과거 날짜도 선택 가능하게 (기본: 오늘 이후만)",
        value=False,
        key="apply_include_past"
    )
    
    if include_past:
        dates = all_dates_full
    else:
        dates = [d for d in all_dates_full if d >= today]
    
    if not dates:
        st.warning("⚠️ 선택 가능한 날짜가 없습니다.")
        return
    
    # 빠른 날짜 선택
    col_a, col_b = st.columns([2, 1])
    with col_a:
        quick_select = st.selectbox(
            "📅 빠른 날짜 선택",
            ["이번 주 (월~일)", "다음 주", "이번 달 남은 날", "전체 (필터된)", "직접 선택"],
            key="apply_quick_select"
        )
    
    preset_dates = []
    if quick_select == "이번 주 (월~일)":
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        preset_dates = [d for d in dates if monday <= d <= sunday]
    elif quick_select == "다음 주":
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
        sunday = monday + timedelta(days=6)
        preset_dates = [d for d in dates if monday <= d <= sunday]
    elif quick_select == "이번 달 남은 날":
        preset_dates = [d for d in dates if d >= today and d.month == today.month]
    elif quick_select == "전체 (필터된)":
        preset_dates = list(dates)
    
    selected_dates = st.multiselect(
        "✅ 적용할 날짜 (여러 개 가능)",
        options=dates,
        default=preset_dates,
        format_func=lambda d: f"{d.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[d.weekday()]})",
        key="apply_date_select"
    )
    
    if not selected_dates:
        st.info("👆 위에서 날짜를 먼저 선택하세요.")
        return
    
    st.markdown(f"**선택됨: {len(selected_dates)}일**")
    
    # === 격자 에디터 ===
    bar_options = ["BAR0"] + [f"BAR{i}" for i in range(1, 9)]
    
    # 세션에 편집 중인 매트릭스 저장 (리셋 버튼용)
    matrix_key = f"apply_matrix_data_{len(selected_dates)}"
    
    # 권장 BAR 맵 (비교용)
    rec_bar_map = {}
    for rid in DYNAMIC_ROOMS:
        for d in selected_dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            rec_bar = "BAR5"
            if not curr_match.empty:
                _, rec_bar, _, _ = get_final_values(
                    rid, d,
                    curr_match.iloc[0]['Available'],
                    curr_match.iloc[0]['Total']
                )
            rec_bar_map[(rid, date_str)] = rec_bar
    
    # 초기값: 기존 applied_rates > 권장 BAR
    def build_initial_matrix():
        data = []
        for rid in DYNAMIC_ROOMS:
            row_data = {"객실": rid}
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                # 기존 적용값 > 권장값
                existing = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
                if existing:
                    row_data[col_label] = existing
                else:
                    row_data[col_label] = rec_bar_map.get((rid, date_str), "BAR5")
            data.append(row_data)
        return data
    
    # 빠른 채우기 버튼
    st.markdown("**🔧 빠른 채우기**")
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
    
    with btn_col1:
        if st.button("🎯 권장 BAR 전체 채우기", use_container_width=True, key="fill_recommended"):
            data = []
            for rid in DYNAMIC_ROOMS:
                row_data = {"객실": rid}
                for d in selected_dates:
                    date_str = d.strftime('%Y-%m-%d')
                    col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    row_data[col_label] = rec_bar_map.get((rid, date_str), "BAR5")
                data.append(row_data)
            st.session_state[matrix_key] = data
            st.rerun()
    
    with btn_col2:
        bulk_bar = st.selectbox("일괄 BAR", bar_options, index=4, key="bulk_bar_select", label_visibility="collapsed")
    
    with btn_col3:
        if st.button(f"⚡ 전체 {bulk_bar}로", use_container_width=True, key="fill_bulk"):
            data = []
            for rid in DYNAMIC_ROOMS:
                row_data = {"객실": rid}
                for d in selected_dates:
                    col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    row_data[col_label] = bulk_bar
                data.append(row_data)
            st.session_state[matrix_key] = data
            st.rerun()
    
    with btn_col4:
        if st.button("🔄 저장된 값으로 리셋", use_container_width=True, key="reset_matrix"):
            if matrix_key in st.session_state:
                del st.session_state[matrix_key]
            st.rerun()
    
    # 현재 매트릭스 (세션에 있으면 사용, 없으면 초기값)
    if matrix_key not in st.session_state:
        st.session_state[matrix_key] = build_initial_matrix()
    
    matrix_df = pd.DataFrame(st.session_state[matrix_key])
    
    # 컬럼 설정 (셀을 드롭다운으로)
    col_config = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
    for d in selected_dates:
        col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
        col_config[col_label] = st.column_config.SelectboxColumn(
            options=bar_options,
            required=True,
            width="small"
        )
    
    st.markdown("### 📋 시장분석 형태 편집기")
    st.caption("셀을 클릭해서 BAR 변경하세요. (가로: 날짜 / 세로: 객실)")
    
    edited_matrix = st.data_editor(
        matrix_df,
        column_config=col_config,
        use_container_width=True,
        hide_index=True,
        key="apply_matrix_editor_v2"
    )
    
    # 권장 BAR 참고 표
    with st.expander("🎯 권장 BAR 참고 (시스템 자동 계산)", expanded=False):
        rec_matrix = []
        for rid in DYNAMIC_ROOMS:
            rec_row = {"객실": rid}
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                rec_row[col_label] = rec_bar_map.get((rid, date_str), "-")
            rec_matrix.append(rec_row)
        st.dataframe(pd.DataFrame(rec_matrix), use_container_width=True, hide_index=True)
    
    # applied_input에 반영
    applied_input = {}
    diff_count = 0
    for idx, row in edited_matrix.iterrows():
        rid = row["객실"]
        for d in selected_dates:
            date_str = d.strftime('%Y-%m-%d')
            col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            bar_val = str(row[col_label]).strip().upper() if row[col_label] else None
            if bar_val and bar_val in bar_options:
                if d not in applied_input:
                    applied_input[d] = {}
                applied_input[d][rid] = bar_val
                # 권장과 차이 카운트
                rec_val = rec_bar_map.get((rid, date_str))
                if rec_val and bar_val != rec_val:
                    diff_count += 1
    
    # 상태 표시
    if diff_count > 0:
        st.warning(f"⚠️ 권장 BAR과 다른 값 **{diff_count}개** 있습니다. 저장 전 확인하세요.")
    else:
        st.success("✅ 모든 값이 권장 BAR과 일치합니다.")
    
    st.divider()
    
    # 메모
    memo = st.text_area(
        "📝 메모 (모든 선택된 날짜에 동일 적용)",
        placeholder="예: 총지배인 지시로 유지 / 단체예약 있어서 조정 안함",
        key="apply_memo",
        height=70
    )
    
    # 저장/삭제 버튼
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("💾 선택한 날짜 모두 적용 저장", type="primary", use_container_width=True, key="apply_save_btn"):
            success_count = 0
            fail_count = 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                rooms_data = applied_input.get(d, {})
                if rooms_data:
                    if save_applied_rate(date_str, rooms_data, memo):
                        success_count += 1
                    else:
                        fail_count += 1
            
            if success_count:
                st.success(f"✅ {success_count}일 적용 완료!")
                st.balloons()
                # 매트릭스 세션 초기화 (다음에 새로 불러오도록)
                if matrix_key in st.session_state:
                    del st.session_state[matrix_key]
                st.rerun()
            if fail_count:
                st.error(f"❌ {fail_count}일 저장 실패")
    
    with col2:
        if st.button("🗑️ 적용 기록 삭제", use_container_width=True, key="apply_delete_btn"):
            del_count = 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                if delete_applied_rate(date_str):
                    del_count += 1
            if del_count:
                st.success(f"🗑️ {del_count}일 삭제됨")
                if matrix_key in st.session_state:
                    del st.session_state[matrix_key]
                st.rerun()

# --- 4-D. 채널 판매가 (적용가 기준) ---
def render_channel_sale_table(current_df, ch_name, applied_rates):
    """채널별 판매가 - 시스템 권장가 베이스에 적용 BAR 덮어쓰기"""
    if current_df.empty:
        return ""
    
    items_to_show = st.session_state.promotions.get(ch_name, {}).get("items", [])
    if not items_to_show:
        return f"<div style='padding:10px; color:gray;'>👉 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"
    
    dates = sorted(current_df['Date'].unique())
    
    html = f"""
    <div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; 
                padding:10px; background:#E8F5E9; border-left:10px solid #2E7D32;'>
        ✅ {ch_name} 판매가 산출 (최종 동기화 반영)
    </div>
    """
    html += "<div style='overflow-x:auto; white-space:nowrap; border:1px solid #ddd;'>"
    html += "<table style='width:100%; border-collapse:collapse; font-size:11px; min-width:1000px;'>"
    html += "<thead><tr style='background:#f9f9f9;'>"
    html += "<th rowspan='2' style='border:1px solid #ddd; width:200px; position:sticky; left:0; background:#f9f9f9; z-index:2; padding:5px;'>객실/프로모션</th>"
    for d in dates:
        html += f"<th style='border:1px solid #ddd; padding:3px; min-width:70px;'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd == '일' else ("blue" if wd == '토' else "black")
        html += f"<th style='border:1px solid #ddd; padding:3px; color:{color};'>{wd}</th>"
    html += "</tr></thead><tbody>"
    
    for item in items_to_show:
        rid = item.get('객실타입', 'Unknown')
        label_text = item.get('상품명', 'No Name')
        label = f"<b>{rid}</b> <span style='color:blue; font-size:10px;'>: {label_text}</span>"
        
        try: discount = float(item.get('할인(%)') or 0)
        except: discount = 0.0
        try: add_price = int(item.get('추가금') or 0)
        except: add_price = 0
        
        border_thick = "border-bottom:3px solid #000;" if rid in ["HDF", "PPV"] else ""
        html += f"<tr style='{border_thick}'>"
        html += f"<td style='border:1px solid #ddd; padding:4px; background:#fff; border-right:3px solid #000; position:sticky; left:0; z-index:1; font-size:11px;'>{label}</td>"
        
        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd; padding:4px; text-align:center;'>-</td>"
                continue
            
            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            
            # 기본 시스템 권장가 확인
            _, rec_bar, _, _ = get_final_values(rid, d, avail, total)
            
            # 5번 섹션에서 수동 적용한 BAR 확인
            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
            is_applied = applied_bar is not None
            
            # 최종 결정된 BAR와 기본 가격
            final_bar = applied_bar if is_applied else rec_bar
            base_price = get_bar_price(rid, final_bar)
            
            # 판매가 계산
            try:
                b_price = float(base_price) if base_price else 0
                after_disc = b_price * (1 - (discount / 100))
                final_p = int((math.floor(after_disc / 1000) * 1000) + add_price)
                
                # 색상은 항상 시스템 권장가든 최종 확정가든 해당 BAR에 맞춰 출력
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or final_bar == "BAR0" else "#F1F1F1"
                
                if is_applied:
                    style = f"border:2px dashed #2E7D32; padding:4px; text-align:center; background:{bg}; font-weight:bold;"
                    content = f"⭐ {final_p:,}<br><span style='font-size:9px;'>{final_bar}</span>"
                else:
                    style = f"border:1px solid #ddd; padding:4px; text-align:center; background:{bg};"
                    content = f"{final_p:,}<br><span style='font-size:9px; color:#555;'>{final_bar}</span>"
                
                html += f"<td style='{style}'>{content}</td>"
            except:
                html += "<td style='border:1px solid #ddd; padding:4px; text-align:center;'>-</td>"
        
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
    
    # 🕐 전역 날짜 필터 (최상단)
    all_dates = sorted(curr['Date'].unique())
    st.markdown(f"""
    <div style='background:#E3F2FD; padding:10px 15px; border-radius:8px; margin:15px 0; 
                border-left:5px solid #1976D2;'>
        📅 <b>오늘 기준:</b> {TODAY.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[TODAY.weekday()]}) · 
        기본적으로 <b>오늘 이후</b>만 표시됩니다. 과거 보려면 아래 체크박스 활성화하세요.
    </div>
    """, unsafe_allow_html=True)
    
    # 🎛️ 토글로 필터링된 날짜
    visible_dates = date_filter_toggle("main", all_dates, default_show_past=False)
    
    # 필터링된 DF
    curr_filtered = filter_df_by_dates(curr, visible_dates)
    prev_filtered = filter_df_by_dates(prev, visible_dates) if not prev.empty else prev
    
    if curr_filtered.empty:
        st.warning("⚠️ 표시할 날짜가 없습니다. 위 체크박스를 활성화하거나 파일을 업로드하세요.")
    else:
        applied_rates_data = load_applied_rates()
        
        # 1. 시장 분석 (시스템 권장 요금)
        st.markdown(render_master_table(curr_filtered, prev_filtered, title="📊 1. 시장 분석 (시스템 권장 기준)", mode="기준"), unsafe_allow_html=True)
        
        # 1-A. 실제 최종 요금 판도 (시스템 권장에 전략적 수동 개입 덮어씌움)
        st.markdown(render_master_table(curr_filtered, prev_filtered, applied_rates=applied_rates_data, title="🎯 1-A. 최종 확정 요금 상태 (시스템 + 전략 적용)", mode="최종결과"), unsafe_allow_html=True)

        st.markdown(render_master_table(curr_filtered, prev_filtered, title="📈 2. 예약 변화량", mode="변화"), unsafe_allow_html=True)
        st.markdown(render_master_table(curr_filtered, prev_filtered, title="🔔 3. 판도 변화", mode="판도변화"), unsafe_allow_html=True)

        # --- 4번 표: 권장 vs 적용 비교 (가로형 재작성) ---
        st.markdown(render_applied_vs_recommend_table(curr_filtered, applied_rates_data), unsafe_allow_html=True)

        # --- 5번: 요금 적용 UI (항상 전체 날짜 대상, 자체 필터링) ---
        render_apply_rate_ui(curr, applied_rates_data)

    # === [수정 사항] 판도 직접 수정을 비밀스럽게 숨김 (Expander) ===
    with st.expander("🛠️ 전략적 판도 오버라이드 (Admin Only)", expanded=False):
        st.write("※ 여기서 수정한 내용은 오직 하단의 '✅ 판매가 산출' 표와 엑셀 다운로드에만 반영되며, 상단의 시장 분석 데이터는 원본 시스템 계산값을 유지합니다.")
        dates_list = sorted(st.session_state.today_df['Date'].unique())
        matrix_data = []
        
        # 표 모양으로 데이터 재조립 (가로: 날짜, 세로: 객실)
        for rid in ALL_ROOMS:
            row_data = {"객실": rid}
            for d in dates_list:
                o_key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                row_data[d.strftime('%m-%d')] = st.session_state.get('manual_bars', {}).get(o_key, "")
            matrix_data.append(row_data)
            
        ed_df = pd.DataFrame(matrix_data)
        
        # 에디터 UI 적용 (객실명 수정 불가 처리)
        col_config = {"객실": st.column_config.TextColumn(disabled=True)}
        edited_matrix = st.data_editor(ed_df, use_container_width=True, hide_index=True, column_config=col_config)
        
        if st.button("💾 전략 적용 및 새로고침", use_container_width=True):
            new_manual_bars = {}
            for idx, row in edited_matrix.iterrows():
                rid = row["객실"]
                for d in dates_list:
                    val = str(row[d.strftime('%m-%d')]).strip()
                    if val and val.upper() not in ["NONE", "NAN", ""]:
                        key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                        new_manual_bars[key] = val.upper()
            st.session_state.manual_bars = new_manual_bars
            st.success("수동 오버라이드가 하단 판매가 리포트에 적용되었습니다.")
            st.rerun()

    st.divider()

    # 채널 판매가도 필터 적용 + 적용가 기준 계산 (이지에디터)
    if st.session_state.channel_list:
        st.markdown("""
        <div style='background:#FFF3E0; padding:10px 15px; border-radius:8px; margin:15px 0;'>
            💡 <b>채널 판매가는 '적용가(⭐)' 기준으로 계산됩니다.</b> 
            적용 기록이 없는 날짜는 기본 시스템 권장가로 자동 계산 및 색상 표시됩니다.
        </div>
        """, unsafe_allow_html=True)
        
        for ch in st.session_state.channel_list:
            st.markdown(render_channel_sale_table(
                curr_filtered, ch, applied_rates_data
            ), unsafe_allow_html=True)

    st.divider()
    
    # --- 엑셀 다운로드 기능 ---
    st.subheader("📥 데이터 엑셀 다운로드")
    st.write("현재 화면에 계산된(수동 변경 포함) 최종 데이터 리스트를 엑셀 파일로 다운로드합니다.")
    
    def generate_excel():
        output = io.BytesIO()
        export_data = []
        applied_rates_export = load_applied_rates()
        
        for idx, row in st.session_state.today_df.iterrows():
            d = row['Date']
            rid = row['RoomID']
            date_str = d.strftime('%Y-%m-%d')
            
            # 권장 BAR (시스템 계산)
            occ, rec_bar, rec_price, _ = get_final_values(rid, d, row['Available'], row['Total'])
            
            # 적용 BAR (있으면)
            applied_bar = applied_rates_export.get(date_str, {}).get('rooms', {}).get(rid)
            applied_memo = applied_rates_export.get(date_str, {}).get('memo', '')
            applied_at = applied_rates_export.get(date_str, {}).get('applied_at_display', '')
            
            if applied_bar:
                applied_price = get_bar_price(rid, applied_bar)
                status = "✅ 적용됨"
                is_diff = "⚠️ 다름" if applied_bar != rec_bar else "일치"
            else:
                applied_price = None
                status = "⚪ 대기중"
                is_diff = "-"
            
            is_past = "📜 과거" if d < TODAY else "🔮 미래"
            
            export_data.append({
                "날짜": date_str,
                "요일": WEEKDAYS_KR[d.weekday()],
                "과거/미래": is_past,
                "객실타입": rid,
                "잔여객실": row['Available'],
                "전체객실": row['Total'],
                "점유율(%)": round(occ, 1),
                "🎯권장BAR": rec_bar,
                "🎯권장가": rec_price,
                "⭐적용BAR": applied_bar if applied_bar else "-",
                "⭐적용가": applied_price if applied_price else "-",
                "상태": status,
                "권장vs적용": is_diff,
                "메모": applied_memo,
                "반영일시": applied_at
            })
        df_export = pd.DataFrame(export_data)
        with pd.ExcelWriter(output) as writer:
            df_export.to_excel(writer, index=False, sheet_name='권장vs적용')
        return output.getvalue()

    st.download_button(
        label="📊 엑셀 다운로드 실행",
        data=generate_excel(),
        file_name=f"AmberPureHill_Report_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
