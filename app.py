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

# --- 3-A. 재검토 필요 판단 헬퍼 (NEW) ---
def is_review_needed(rid, date_obj, current_df, applied_rates):
    """
    오버라이드 적용된 날짜에서 시스템 권장이 변경되어 재검토가 필요한지 판단.
    리턴: (needs_review: bool, applied_bar: str, recommended_bar: str)
    """
    date_str = date_obj.strftime('%Y-%m-%d')
    applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
    
    if not applied_bar:
        return False, None, None
    
    curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == date_obj)]
    if curr_match.empty:
        return False, applied_bar, None
    
    avail = curr_match.iloc[0]['Available']
    total = curr_match.iloc[0]['Total']
    _, rec_bar, _, _ = get_final_values(rid, date_obj, avail, total)
    
    # 적용 시점의 권장 BAR 저장 여부 확인
    saved_rec_at_apply = applied_rates.get(date_str, {}).get('rec_bar_at_apply', {}).get(rid)
    
    if saved_rec_at_apply and saved_rec_at_apply != rec_bar:
        # 적용 당시 권장이랑 지금 권장이 다르면 재검토 필요
        return True, applied_bar, rec_bar
    
    return False, applied_bar, rec_bar

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
            date_str = d.strftime('%Y-%m-%d')
            
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += f"<td style='border:1px solid #ddd; padding:{row_padding}; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            
            override_key = f"{date_str}_{rid}"
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
                content = f"<b>{bar}</b><br>{base_price:,}<br>{occ:.0f}%"
                
            elif mode == "최종결과":
                applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid) if applied_rates else None
                is_applied = applied_bar is not None
                
                final_bar = applied_bar if is_applied else bar
                final_price = get_bar_price(rid, final_bar) if is_applied else base_price
                
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFFFFF") if rid in DYNAMIC_ROOMS or final_bar == "BAR0" else "#F1F1F1"
                
                # 재검토 필요 표시
                needs_review = False
                if is_applied and applied_rates and rid in DYNAMIC_ROOMS:
                    needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)
                
                if is_applied:
                    if needs_review:
                        style += f"background-color: {bg}; border: 3px solid #FF6F00; font-weight: bold; box-shadow: inset 0 0 0 2px #FFD54F;"
                        content = f"⚠️ <b>{final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
                    else:
                        style += f"background-color: {bg}; border: 3px solid #2E7D32; font-weight: bold;"
                        content = f"⭐ <b>{final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
                else:
                    style += f"background-color: {bg}; opacity: 0.9;"
                    content = f"<b>{final_bar}</b><br>{final_price:,}<br>{occ:.0f}%"
            
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

def save_applied_rate(target_date_str, applied_data, memo="", rec_at_apply=None):
    """
    특정 날짜에 적용된 요금 저장
    target_date_str: '2026-04-25' 형식
    applied_data: {'FDB': 'BAR5', 'FDE': 'BAR5', ...}
    rec_at_apply: 적용 시점의 시스템 권장 BAR (재검토 알림용)
    """
    try:
        payload = {
            'applied_date': target_date_str,
            'applied_at': datetime.now().isoformat(),
            'applied_at_display': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'memo': memo,
            'rooms': applied_data,
        }
        if rec_at_apply:
            payload['rec_bar_at_apply'] = rec_at_apply
        db.collection("applied_rates").document(target_date_str).set(payload)
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
    
    # 재검토 필요 카운트 계산
    review_count = 0
    for rid in DYNAMIC_ROOMS:
        for d in dates:
            needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)
            if needs_review:
                review_count += 1
    
    review_banner = ""
    if review_count > 0:
        review_banner = f"""
        <div style='background:#FFF3E0; border:2px solid #FF6F00; padding:8px 12px; 
                    margin-top:5px; border-radius:6px; font-size:13px; color:#E65100;'>
            ⚠️ <b>재검토 필요 {review_count}건</b> — 적용 시점 이후 시스템 권장이 변경된 셀이 있습니다 (주황 테두리 + ⚠️ 표시)
        </div>
        """
    
    html = f"""
    <div style='margin-top:40px; margin-bottom:10px; font-weight:bold; font-size:18px; 
                padding:10px; background:#f0f2f6; border-left:10px solid #FF8F00;'>
        🔍 4. 권장 vs 적용 비교 대조표 (CMS 관리용)
    </div>
    {review_banner}
    """
    
    html += "<div style='overflow-x:auto; white-space:nowrap; border:1px solid #ddd; margin-top:5px;'>"
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
            rec_at_apply = applied_info.get('rec_bar_at_apply', {}).get(rid)
            
            # 재검토 필요 여부
            needs_review = bool(applied_bar and rec_at_apply and rec_at_apply != rec_bar)
            
            # 메모를 툴팁으로 처리
            tip_parts = []
            if memo: tip_parts.append(f"📝 {memo}")
            if applied_at: tip_parts.append(f"⏰ {applied_at}")
            if needs_review: tip_parts.append(f"⚠️ 적용시점 권장: {rec_at_apply} → 현재 권장: {rec_bar}")
            memo_text = " | ".join(tip_parts)
            tooltip = f"title='{memo_text}'" if memo_text else ""
            
            if not applied_bar:
                style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #FAFAFA; color: #999;"
                content = f"<span style='font-size:9px;'>대기중</span><br>{rec_bar}"
            elif needs_review:
                # 재검토 필요 - 주황 강조
                style = "border:2px solid #FF6F00; padding:8px; text-align:center; background-color: #FFF3E0; color: #E65100; font-weight:bold;"
                content = f"⚠️ <b>{applied_bar}</b><br><span style='font-size:9px; color:#FF6F00;'>권장→{rec_bar}</span>"
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

# --- 4-C. 요금 적용 UI (필터 + 일괄변경 강화) ---
def render_apply_rate_ui(current_df, applied_rates):
    if current_df.empty: return
    st.markdown("""<div style='margin-top:40px; margin-bottom:15px; font-weight:bold; font-size:18px; padding:10px; background:#FFF3E0; border-left:10px solid #FF6F00;'>⏰ 5. 전략적 요금 오버라이드 (CMS 수동 반영)</div>""", unsafe_allow_html=True)
    st.caption("🔧 특정 일자의 요금을 시스템 권장과 다르게 강제로 묶거나 인상할 때 사용합니다.")
    
    all_dates_full = sorted(current_df['Date'].unique())
    today = date.today()
    
    # ---------- 필터 옵션 (NEW) ----------
    st.markdown("##### 🎚️ 날짜 필터 옵션")
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        include_past = st.checkbox("📜 과거 날짜 포함", value=False, key="apply_include_past")
    with fcol2:
        only_overridden = st.checkbox("⭐ 오버라이드된 날짜만 보기", value=False, key="apply_only_overridden",
                                       help="이미 수동 적용된 날짜만 필터링 (재수정용)")
    with fcol3:
        only_review_needed = st.checkbox("⚠️ 재검토 필요한 날짜만 보기", value=False, key="apply_only_review",
                                          help="시스템 권장이 바뀐 오버라이드 날짜만 표시")
    
    # 1차 필터: 과거 포함 여부
    dates = all_dates_full if include_past else [d for d in all_dates_full if d >= today]
    
    # 2차 필터: 오버라이드된 날짜만
    if only_overridden:
        overridden_dates = set()
        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            if applied_rates.get(date_str, {}).get('rooms'):
                overridden_dates.add(d)
        dates = sorted(overridden_dates)
    
    # 3차 필터: 재검토 필요한 날짜만
    if only_review_needed:
        review_dates = set()
        for d in dates:
            for rid in DYNAMIC_ROOMS:
                needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)
                if needs_review:
                    review_dates.add(d)
                    break
        dates = sorted(review_dates)
    
    if not dates: 
        if only_overridden:
            return st.info("✨ 오버라이드된 날짜가 없습니다.")
        if only_review_needed:
            return st.success("✅ 재검토가 필요한 날짜가 없습니다.")
        return st.warning("⚠️ 선택 가능한 날짜가 없습니다.")
    
    # ---------- 누적 날짜 선택 (NEW: 기간+기간, 기간+일자 자유 조합) ----------
    st.markdown("##### 📅 적용할 날짜 누적 선택")
    st.caption("💡 아래 도구로 기간/일자를 **추가**하면 누적됩니다. 기간+기간, 기간+일자, 일자+일자 자유 조합 가능!")
    
    # 누적 선택 저장소
    if '_picked_dates' not in st.session_state:
        st.session_state['_picked_dates'] = set()
    
    # ---------- [도구 1] 빠른 프리셋 추가 ----------
    with st.container(border=True):
        st.markdown("**🎯 빠른 프리셋 (클릭 시 누적 추가)**")
        pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)
        
        def add_to_picked(new_dates):
            """선택된 날짜들을 누적 set에 추가 (필터된 dates 안에 있는 것만)"""
            valid = [d for d in new_dates if d in dates]
            st.session_state['_picked_dates'].update(valid)
        
        with pcol1:
            if st.button("➕ 이번 주", use_container_width=True, key="preset_thisweek"):
                monday = today - timedelta(days=today.weekday())
                add_to_picked([d for d in dates if monday <= d <= monday + timedelta(days=6)])
                st.rerun()
        with pcol2:
            if st.button("➕ 다음 주", use_container_width=True, key="preset_nextweek"):
                monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
                add_to_picked([d for d in dates if monday <= d <= monday + timedelta(days=6)])
                st.rerun()
        with pcol3:
            if st.button("➕ 이번 달 남은 날", use_container_width=True, key="preset_thismonth"):
                add_to_picked([d for d in dates if d >= today and d.month == today.month])
                st.rerun()
        with pcol4:
            if st.button("➕ 전체 (필터된)", use_container_width=True, key="preset_all"):
                add_to_picked(list(dates))
                st.rerun()
        with pcol5:
            if st.button("🗑️ 전체 비우기", use_container_width=True, key="preset_clear"):
                st.session_state['_picked_dates'] = set()
                # matrix 캐시도 함께 정리
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.rerun()
    
    # ---------- [도구 2] 기간 추가 ----------
    with st.container(border=True):
        st.markdown("**📆 기간 추가 (시작일 ~ 종료일)** — 여러 번 누르면 여러 기간 누적!")
        rc1, rc2, rc3 = st.columns([2, 2, 1])
        with rc1:
            range_start = st.date_input("시작일", value=dates[0], 
                                         min_value=dates[0], 
                                         max_value=dates[-1], 
                                         key="apply_range_start")
        with rc2:
            range_end = st.date_input("종료일", value=dates[-1], 
                                       min_value=dates[0], 
                                       max_value=dates[-1], 
                                       key="apply_range_end")
        with rc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 이 기간 추가", use_container_width=True, key="apply_range_btn", type="primary"):
                if range_start > range_end:
                    st.error("시작일이 종료일보다 늦습니다.")
                else:
                    new_dates = [d for d in dates if range_start <= d <= range_end]
                    add_to_picked(new_dates)
                    st.rerun()
    
    # ---------- [도구 3] 개별 일자 추가 ----------
    with st.container(border=True):
        st.markdown("**📍 개별 일자 추가** — 점 찍듯이 골라서 누적!")
        ic1, ic2 = st.columns([3, 1])
        with ic1:
            single_pick = st.multiselect(
                "추가할 일자 선택 (여러 개 한번에 가능)",
                options=dates,
                format_func=lambda d: f"{d.strftime('%m-%d')} ({WEEKDAYS_KR[d.weekday()]})",
                key="apply_single_pick",
                label_visibility="collapsed"
            )
        with ic2:
            if st.button("➕ 일자 추가", use_container_width=True, key="apply_single_add", type="primary"):
                if single_pick:
                    add_to_picked(single_pick)
                    # 입력칸 비우기
                    if "apply_single_pick" in st.session_state:
                        del st.session_state["apply_single_pick"]
                    st.rerun()
                else:
                    st.warning("일자를 먼저 선택하세요.")
    
    # ---------- [최종] 선택된 날짜 확인 + 미세조정 ----------
    selected_dates = sorted(st.session_state['_picked_dates'])
    
    if not selected_dates:
        return st.info("👆 위 도구로 날짜를 먼저 추가하세요. (기간/일자/프리셋 자유 조합)")
    
    # 선택 결과를 보기 좋게 칩 형태로 표시
    chips_html = "".join([
        f"<span style='background:#E3F2FD; border:1px solid #1976D2; color:#0D47A1; "
        f"padding:3px 8px; border-radius:12px; margin:2px; font-size:11px; "
        f"display:inline-block; font-weight:bold;'>"
        f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})</span>"
        for d in selected_dates
    ])
    st.markdown(f"""
    <div style='background:#F5F5F5; padding:8px 12px; border-radius:8px; margin:8px 0;
                border-left:4px solid #1976D2;'>
        <b style='color:#1976D2;'>✅ 누적 선택된 날짜 ({len(selected_dates)}일):</b><br>
        {chips_html}
    </div>
    """, unsafe_allow_html=True)
    
    # 개별 제거(미세조정)
    with st.expander("🔧 누적 목록 미세 조정 (제거하고 싶은 날짜 체크 해제)", expanded=False):
        adjusted = st.multiselect(
            "최종 적용할 날짜 (체크 해제하면 제외)",
            options=selected_dates,
            default=selected_dates,
            format_func=lambda d: f"{d.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[d.weekday()]})",
            key="apply_date_finetune"
        )
        if len(adjusted) != len(selected_dates):
            if st.button("✂️ 위 조정 사항 적용", key="apply_finetune_apply"):
                st.session_state['_picked_dates'] = set(adjusted)
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.rerun()
    
    if not selected_dates: return st.info("👆 위에서 날짜를 먼저 선택하세요.")
    
    bar_options = ["BAR0"] + [f"BAR{i}" for i in range(1, 9)]
    
    safe_date_str = "".join([d.strftime('%d') for d in selected_dates])
    matrix_key = f"apply_matrix_data_{len(selected_dates)}_{safe_date_str}"
    
    rec_bar_map = {}
    for rid in DYNAMIC_ROOMS:
        for d in selected_dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            rec_bar = "BAR5"
            if not curr_match.empty:
                _, rec_bar, _, _ = get_final_values(rid, d, curr_match.iloc[0]['Available'], curr_match.iloc[0]['Total'])
            rec_bar_map[(rid, date_str)] = rec_bar
    
    def build_initial_matrix():
        data = []
        for rid in DYNAMIC_ROOMS:
            row_data = {"객실": rid}
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                existing = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
                row_data[col_label] = existing if existing else rec_bar_map.get((rid, date_str), "BAR5")
            data.append(row_data)
        return data
    
    # ---------- 빠른 채우기 ----------
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
            if matrix_key in st.session_state: del st.session_state[matrix_key]
            st.rerun()
    
    # ---------- 일괄 시프트(NEW): 전체 한 단계 올리기/내리기 ----------
    st.markdown("**📈 일괄 시프트 (오버라이드 한번에 조정)**")
    sft_col1, sft_col2, sft_col3, sft_col4 = st.columns(4)
    
    def shift_bar(bar_str, step):
        """BAR1~BAR8 사이에서 step만큼 이동. 음수면 인상(번호 감소), 양수면 인하(번호 증가)"""
        if not bar_str or bar_str == "BAR0":
            return bar_str
        try:
            n = int(bar_str.replace("BAR", ""))
            new_n = max(1, min(8, n + step))
            return f"BAR{new_n}"
        except:
            return bar_str
    
    with sft_col1:
        if st.button("⬆️ 한 단계 인상 (BAR↓)", use_container_width=True, key="shift_up_1",
                     help="모든 셀의 BAR을 한 단계 위로 (예: BAR5→BAR4)"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, -1)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    with sft_col2:
        if st.button("⬇️ 한 단계 인하 (BAR↑)", use_container_width=True, key="shift_down_1",
                     help="모든 셀의 BAR을 한 단계 아래로 (예: BAR5→BAR6)"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, 1)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    with sft_col3:
        if st.button("⏫ 두 단계 인상", use_container_width=True, key="shift_up_2"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, -2)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    with sft_col4:
        if st.button("⏬ 두 단계 인하", use_container_width=True, key="shift_down_2"):
            current = st.session_state.get(matrix_key, build_initial_matrix())
            new_data = []
            for row in current:
                new_row = {"객실": row["객실"]}
                for k, v in row.items():
                    if k != "객실":
                        new_row[k] = shift_bar(v, 2)
                new_data.append(new_row)
            st.session_state[matrix_key] = new_data
            st.rerun()
    
    if matrix_key not in st.session_state: st.session_state[matrix_key] = build_initial_matrix()
    matrix_df = pd.DataFrame(st.session_state[matrix_key])
    
    col_config = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
    for d in selected_dates:
        col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
        col_config[col_label] = st.column_config.SelectboxColumn(options=bar_options, required=True, width="small")
    
    edited_matrix = st.data_editor(matrix_df, column_config=col_config, use_container_width=True, hide_index=True, key="apply_matrix_editor_v2")
    
    applied_input = {}
    for idx, row in edited_matrix.iterrows():
        rid = row["객실"]
        for d in selected_dates:
            date_str = d.strftime('%Y-%m-%d')
            col_label = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            
            raw_val = row.get(col_label)
            bar_val = str(raw_val).strip().upper() if raw_val and pd.notna(raw_val) else None
            
            if bar_val and bar_val in bar_options:
                if d not in applied_input: applied_input[d] = {}
                applied_input[d][rid] = bar_val
    
    memo = st.text_area("📝 메모 (툴팁 표시용)", placeholder="예: 총지배인 지시로 유지 / 단체예약 있어서 조정 안함", key="apply_memo", height=70)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("💾 선택한 날짜 모두 적용 저장", type="primary", use_container_width=True, key="apply_save_btn"):
            success_count, fail_count = 0, 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                if applied_input.get(d, {}):
                    # 적용 시점의 시스템 권장 BAR도 같이 저장 (재검토 알림용)
                    rec_at_apply = {}
                    for rid in applied_input[d].keys():
                        rec_at_apply[rid] = rec_bar_map.get((rid, date_str), "BAR5")
                    
                    if save_applied_rate(date_str, applied_input[d], memo, rec_at_apply): 
                        success_count += 1
                    else: 
                        fail_count += 1
            if success_count:
                st.success(f"✅ {success_count}일 적용 완료!")
                # 매트릭스 + 누적 목록 모두 정리
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.session_state['_picked_dates'] = set()
                st.rerun()
    with col2:
        if st.button("🗑️ 선택일 적용 기록 해제", use_container_width=True, key="apply_delete_btn"):
            del_count = 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                if delete_applied_rate(date_str): del_count += 1
            if del_count:
                st.success(f"🗑️ {del_count}일 수동 적용 해제됨 (시스템 권장가로 원복)")
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.session_state['_picked_dates'] = set()
                st.rerun()
                
# --- 4-D. 채널 판매가 (적용가 기준 + 판도변화 버그 수정) ---
def render_channel_sale_table(current_df, prev_df, ch_name, applied_rates, prev_applied_rates=None):
    """채널별 판매가 - 어제 최종가 vs 오늘 최종가 비교로 판도 변화 정확하게 계산"""
    if current_df.empty:
        return ""
    
    items_to_show = st.session_state.promotions.get(ch_name, {}).get("items", [])
    if not items_to_show:
        return f"<div style='padding:10px; color:gray;'>👉 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"
    
    if prev_applied_rates is None:
        prev_applied_rates = applied_rates  # 안전 기본값
    
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
            
            # 1. 오늘의 시스템 권장가
            _, rec_bar, _, _ = get_final_values(rid, d, avail, total)
            
            # 2. 오늘의 최종 BAR (오버라이드 우선)
            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
            is_applied = applied_bar is not None
            final_bar = applied_bar if is_applied else rec_bar
            base_price = get_bar_price(rid, final_bar)
            
            # 3. 어제의 최종 BAR 계산 (★ 핵심 버그 수정 ★)
            #    - 어제도 오버라이드가 있었으면 그 값을, 없었으면 어제 시스템 권장값을 사용
            prev_final_bar = None
            prev_applied_bar = prev_applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
            
            if prev_applied_bar:
                prev_final_bar = prev_applied_bar
            elif prev_df is not None and not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    _, prev_rec_bar, _, _ = get_final_values(rid, d, prev_m.iloc[0]['Available'], prev_m.iloc[0]['Total'])
                    prev_final_bar = prev_rec_bar
            
            # 판도 변화 = 어제 최종가 != 오늘 최종가
            curr_b_str = str(final_bar).strip() if final_bar else ""
            prev_b_str = str(prev_final_bar).strip() if prev_final_bar else ""
            is_trend_changed = (prev_final_bar is not None and prev_b_str != curr_b_str)
            
            # 재검토 필요 여부
            needs_review = False
            if is_applied and rid in DYNAMIC_ROOMS:
                needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)
            
            try:
                b_price = float(base_price) if base_price else 0
                after_disc = b_price * (1 - (discount / 100))
                final_p = int((math.floor(after_disc / 1000) * 1000) + add_price)
                
                # --- 시각화 로직 ---
                # A. 판도 변화 시 색상 적용
                if is_trend_changed:
                    bg = BAR_GRADIENT_COLORS.get(final_bar, "#7000FF")
                    txt_color = "white"
                    font_weight = "bold"
                    trend_icon = "▲ "
                else:
                    bg = "#FFFFFF"
                    txt_color = "#000"
                    font_weight = "normal"
                    trend_icon = ""

                # B. 오버라이드 + 재검토 필요 여부
                if is_applied and needs_review:
                    border_style = "border: 2px solid #FF6F00; box-shadow: inset 0 0 0 1px #FFD54F;"
                    icon = "⚠️"
                    label_color = "#FFF" if is_trend_changed else "#E65100"
                    bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>재검토:{final_bar}</span>"
                elif is_applied:
                    border_style = "border: 2px dashed #D32F2F;"
                    icon = "⭐"
                    label_color = "#FFF" if is_trend_changed else "#D32F2F"
                    bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>수동:{final_bar}</span>"
                else:
                    border_style = "border: 1px solid #ddd;"
                    icon = ""
                    label_color = "#FFF" if is_trend_changed else "#999"
                    bar_label = f"<span style='font-size:9px; color:{label_color};'>{final_bar}</span>"
                
                style = f"background-color: {bg}; color: {txt_color}; font-weight: {font_weight}; {border_style}; padding:4px; text-align:center;"
                content = f"{icon}{trend_icon}{final_p:,}<br>{bar_label}"
                
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
if 'manual_bars' not in st.session_state: st.session_state.manual_bars = {}

with st.sidebar:
    st.header("📅 수정 내역 조회 (History)")
    
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
                "saved_manual_bars": st.session_state.manual_bars
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
    
    all_dates = sorted(curr['Date'].unique())
    st.markdown(f"""
    <div style='background:#E3F2FD; padding:10px 15px; border-radius:8px; margin:15px 0; 
                border-left:5px solid #1976D2;'>
        📅 <b>오늘 기준:</b> {TODAY.strftime('%Y-%m-%d')} ({WEEKDAYS_KR[TODAY.weekday()]}) · 
        기본적으로 <b>오늘 이후</b>만 표시됩니다. 과거 보려면 아래 체크박스 활성화하세요.
    </div>
    """, unsafe_allow_html=True)
    
    visible_dates = date_filter_toggle("main", all_dates, default_show_past=False)
    
    curr_filtered = filter_df_by_dates(curr, visible_dates)
    prev_filtered = filter_df_by_dates(prev, visible_dates) if not prev.empty else prev
    
    if curr_filtered.empty:
        st.warning("⚠️ 표시할 날짜가 없습니다. 위 체크박스를 활성화하거나 파일을 업로드하세요.")
    else:
        applied_rates_data = load_applied_rates()
        
        # ----- 재검토 필요 알림 배너 (NEW) -----
        review_alerts = []
        for rid in DYNAMIC_ROOMS:
            for d in curr_filtered['Date'].unique():
                needs_review, applied_b, rec_b = is_review_needed(rid, d, curr_filtered, applied_rates_data)
                if needs_review:
                    review_alerts.append({
                        '날짜': d.strftime('%m-%d'),
                        '요일': WEEKDAYS_KR[d.weekday()],
                        '객실': rid,
                        '적용 BAR': applied_b,
                        '신규 권장': rec_b,
                    })
        
        if review_alerts:
            st.markdown(f"""
            <div style='background:#FFF3E0; border:2px solid #FF6F00; padding:15px; 
                        border-radius:8px; margin:15px 0; font-size:14px;'>
                <b style='color:#E65100; font-size:16px;'>⚠️ 재검토 필요 {len(review_alerts)}건 발견!</b><br>
                오버라이드된 날짜에서 시스템 권장이 변경되었습니다. 5번 섹션에서 '⚠️ 재검토 필요한 날짜만 보기' 필터를 사용하세요.
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("📋 재검토 대상 상세 보기", expanded=False):
                df_alerts = pd.DataFrame(review_alerts)
                st.dataframe(df_alerts, use_container_width=True, hide_index=True)
        
        # 1. 시장 분석 (시스템 권장 요금)
        st.markdown(render_master_table(curr_filtered, prev_filtered, title="📊 1. 시장 분석 (시스템 권장 기준)", mode="기준"), unsafe_allow_html=True)
        
        # 1-A. 실제 최종 요금 판도
        st.markdown(render_master_table(curr_filtered, prev_filtered, applied_rates=applied_rates_data, title="🎯 1-A. 최종 확정 요금 상태 (시스템 + 전략 적용)", mode="최종결과"), unsafe_allow_html=True)

        st.markdown(render_master_table(curr_filtered, prev_filtered, title="📈 2. 예약 변화량", mode="변화"), unsafe_allow_html=True)
        st.markdown(render_master_table(curr_filtered, prev_filtered, title="🔔 3. 판도 변화", mode="판도변화"), unsafe_allow_html=True)

        # 4. 권장 vs 적용 비교
        st.markdown(render_applied_vs_recommend_table(curr_filtered, applied_rates_data), unsafe_allow_html=True)

        # 5. 요금 적용 UI
        render_apply_rate_ui(curr, applied_rates_data)

    # === 전략적 판도 오버라이드 (Admin Only) ===
    with st.expander("🛠️ 전략적 판도 오버라이드 (Admin Only)", expanded=False):
        st.write("※ 여기서 수정한 내용은 오직 하단의 '✅ 판매가 산출' 표와 엑셀 다운로드에만 반영되며, 상단의 시장 분석 데이터는 원본 시스템 계산값을 유지합니다.")
        dates_list = sorted(st.session_state.today_df['Date'].unique())
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

    # 채널 판매가 (이지에디터) - 판도변화 버그 수정 적용
    if st.session_state.channel_list:
        st.markdown("""
        <div style='background:#FFF3E0; padding:10px 15px; border-radius:8px; margin:15px 0;'>
            💡 <b>채널 판매가 표기 규칙</b><br>
            - 배경색(그라데이션): 어제 최종가 대비 오늘 최종가가 변동되었을 때 (오버라이드 포함)<br>
            - 붉은 점선과 ⭐: 수동으로 전략적 오버라이드한 날짜<br>
            - 주황 테두리와 ⚠️: 오버라이드 후 시스템 권장이 바뀐 '재검토 필요' 날짜
        </div>
        """, unsafe_allow_html=True)
        
        for ch in st.session_state.channel_list:
            st.markdown(render_channel_sale_table(
                curr_filtered, prev_filtered, ch, applied_rates_data, applied_rates_data
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
            
            occ, rec_bar, rec_price, _ = get_final_values(rid, d, row['Available'], row['Total'])
            
            applied_bar = applied_rates_export.get(date_str, {}).get('rooms', {}).get(rid)
            applied_memo = applied_rates_export.get(date_str, {}).get('memo', '')
            applied_at = applied_rates_export.get(date_str, {}).get('applied_at_display', '')
            rec_at_apply = applied_rates_export.get(date_str, {}).get('rec_bar_at_apply', {}).get(rid, '')
            
            if applied_bar:
                applied_price = get_bar_price(rid, applied_bar)
                status = "✅ 적용됨"
                is_diff = "⚠️ 다름" if applied_bar != rec_bar else "일치"
                # 재검토 필요 여부
                needs_review = "⚠️ 재검토" if (rec_at_apply and rec_at_apply != rec_bar) else "OK"
            else:
                applied_price = None
                status = "⚪ 대기중"
                is_diff = "-"
                needs_review = "-"
            
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
                "적용시점권장": rec_at_apply if rec_at_apply else "-",
                "재검토": needs_review,
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
