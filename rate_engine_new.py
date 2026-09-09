# -*- coding: utf-8 -*-
"""
엠버 퓨어힐 · 신 요금로직 (16칸 사다리) — 별개 엔진 모듈
=============================================================================
app.py 는 한 글자도 고치지 않습니다. 이 파일은 pages/ 아래 별도 페이지에서만
불려갑니다. 기존 로직(BAR0P~BAR8 / PRICE_TABLE / 시즌 시작BAR)은 메인 페이지에
그대로 살아 있고, 여기서는 완전히 별개의 사다리(16칸)와 앵커 캘린더를 씁니다.

※ 연도와 무관합니다. 앵커는 "월 x 요일"이고 공휴일은 연도별로 자동 산출하므로
  2026년 날짜에도, 2027년 날짜에도, 그 이후에도 같은 로직이 그대로 돌아갑니다.
  설계 확정판 이름이 Final 6.6 이라서 판 표기에만 남아 있습니다.

무엇이 그대로이고 무엇이 바뀌는가
-----------------------------------------------------------------------------
[유지]  "이전 기록(prev_df) 대비 새 파일(today_df)에서 재고가 바뀌면 요금이
        움직인다"는 구조 자체. 픽업(하루당 판매 실수) → 소진예상일 ÷ 남은일수
        비율로 칸을 올리고 내리는 경로를 그대로 씁니다.
[변경]  그 신호가 꽂히는 '값'. 10단 BAR(BAR0P~BAR8) → 16칸 사다리(B0pp~B13),
        시즌·요일 시작BAR → 앵커 캘린더 84셀, 시즌 상한/게이트 → Peak Event
        Floor(Opening) + Scarcity Floor(Absolute).

칸 규칙 (날짜 6단계 + 타입 1단계)
-----------------------------------------------------------------------------
 1 앵커        월 × 요일 84셀 → 시작 칸
 2 연휴        공휴일·연휴 2칸 상향 (x1.166)
 3 페이스       픽업 기반 +-2칸 (인상은 D-44 이내, 인하는 D-21 이내)
 4 재고        호텔 총잔여율 <=20/12/5% → 1/2/3칸 상향 (리드타임 무관)
 5 Peak Event Floor   이벤트일 최소 칸. D-46 이상 하향 금지 / D-45 1회 재심사
 6 Scarcity Floor     총잔여율 기반 절대 하한. 자동 해제·승인 완화 없음
 7 객실타입      타입 잔여율로 +-2칸, 마감 타입은 판매 중지

칸 인덱스 규약: 1 = B0pp (가장 비쌈) ... 16 = B13 (가장 쌤).
             따라서 "상향(비싸게)" = 인덱스 감소. adj 값이 음수면 상향입니다.
=============================================================================
"""

import io
import math
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

NEW_EDITION = "Final 6.6"

# =============================================================================
# 1. 사다리 · 앵커 · 객실배수  (마스터 [안 G · Final 6.6] 확정값)
# =============================================================================
# HDT 기준 16칸, 칸 간격 8%. 가중 BAR 418,899원 / 필요 이론 BAR 418,849원.
NEW_RUNG = {
    1: 724000, 2: 671000, 3: 621000, 4: 575000, 5: 532000, 6: 493000, 7: 456000, 8: 423000,
    9: 391000, 10: 362000, 11: 336000, 12: 311000, 13: 288000, 14: 266000, 15: 247000, 16: 228000,
}
NEW_LAB = ['0pp', '0p', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13']
NEW_N = 16

# 라벨 → 칸 인덱스 ('3' → 6 = B3)
NEW_RI = {l: i + 1 for i, l in enumerate(NEW_LAB)}


def new_lab(idx):
    """칸 인덱스 → 'B3' 형태 라벨."""
    idx = max(1, min(NEW_N, int(idx)))
    return "B" + NEW_LAB[idx - 1]


_NEW_RI_LOWER = {k.lower(): v for k, v in NEW_RI.items()}


def new_idx(label):
    """'B3' / 'b0pp' / '3' → 칸 인덱스. 알 수 없으면 None."""
    if label is None:
        return None
    s = str(label).strip().replace(" ", "").lower()
    if s in ("", "none", "nan", "-"):
        return None
    if s.startswith("b"):
        s = s[1:]
    return _NEW_RI_LOWER.get(s)


# 객실타입 배수 (HDT = 1.0). 직전연도 실현 ADR 회귀로 산출.
NEW_MULT = {
    "HDT": 1.0,
    "HDP": 1.044,
    "FDB": 1.177,
    "FDE": 1.341,
    "HDF": 1.56,
    "GDB": 0.816,
    "GDF": 1.342,
    "FFD": 1.383,
    "FPT": 1.898,
    "PPV": 2.843,
}
# 표시 순서는 기존 앱 ALL_ROOMS 와 동일합니다 (메인 호텔동 → 특수객실).
NEW_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF", "GDB", "GDF", "FFD", "FPT", "PPV"]
NEW_ROOM_NAMES = {
    "HDT": "힐사이드 디럭스 트윈", "HDP": "힐사이드 디럭스 패밀리",
    "FDB": "포레스트 디럭스 더블", "FDE": "포레스트 디럭스 이그제큐티브",
    "HDF": "힐사이드 디럭스 스위트", "GDB": "그린밸리 더블",
    "GDF": "그린밸리 패밀리", "FFD": "포레스트 패밀리 더블",
    "FPT": "펫 프렌들리", "PPV": "프라이빗 풀빌라",
}

# 타입별 16칸 요금표 = round(RUNG x MULT, 천원). 로드(BAR) 기준가입니다.
NEW_TABLE = {
    "HDT": {"0pp": 724000, "0p": 671000, "0": 621000, "1": 575000, "2": 532000, "3": 493000, "4": 456000, "5": 423000, "6": 391000, "7": 362000, "8": 336000, "9": 311000, "10": 288000, "11": 266000, "12": 247000, "13": 228000},
    "HDP": {"0pp": 756000, "0p": 701000, "0": 648000, "1": 600000, "2": 555000, "3": 515000, "4": 476000, "5": 442000, "6": 408000, "7": 378000, "8": 351000, "9": 325000, "10": 301000, "11": 278000, "12": 258000, "13": 238000},
    "FDB": {"0pp": 852000, "0p": 790000, "0": 731000, "1": 677000, "2": 626000, "3": 580000, "4": 537000, "5": 498000, "6": 460000, "7": 426000, "8": 395000, "9": 366000, "10": 339000, "11": 313000, "12": 291000, "13": 268000},
    "FDE": {"0pp": 971000, "0p": 900000, "0": 833000, "1": 771000, "2": 713000, "3": 661000, "4": 611000, "5": 567000, "6": 524000, "7": 485000, "8": 451000, "9": 417000, "10": 386000, "11": 357000, "12": 331000, "13": 306000},
    "HDF": {"0pp": 1129000, "0p": 1047000, "0": 969000, "1": 897000, "2": 830000, "3": 769000, "4": 711000, "5": 660000, "6": 610000, "7": 565000, "8": 524000, "9": 485000, "10": 449000, "11": 415000, "12": 385000, "13": 356000},
    "GDB": {"0pp": 591000, "0p": 548000, "0": 507000, "1": 469000, "2": 434000, "3": 402000, "4": 372000, "5": 345000, "6": 319000, "7": 295000, "8": 274000, "9": 254000, "10": 235000, "11": 217000, "12": 202000, "13": 186000},
    "GDF": {"0pp": 972000, "0p": 900000, "0": 833000, "1": 772000, "2": 714000, "3": 662000, "4": 612000, "5": 568000, "6": 525000, "7": 486000, "8": 451000, "9": 417000, "10": 386000, "11": 357000, "12": 331000, "13": 306000},
    "FFD": {"0pp": 1001000, "0p": 928000, "0": 859000, "1": 795000, "2": 736000, "3": 682000, "4": 631000, "5": 585000, "6": 541000, "7": 501000, "8": 465000, "9": 430000, "10": 398000, "11": 368000, "12": 342000, "13": 315000},
    "FPT": {"0pp": 1374000, "0p": 1274000, "0": 1179000, "1": 1091000, "2": 1010000, "3": 936000, "4": 865000, "5": 803000, "6": 742000, "7": 687000, "8": 638000, "9": 590000, "10": 547000, "11": 505000, "12": 469000, "13": 433000},
    "PPV": {"0pp": 2058000, "0p": 1908000, "0": 1766000, "1": 1635000, "2": 1512000, "3": 1402000, "4": 1296000, "5": 1203000, "6": 1112000, "7": 1029000, "8": 955000, "9": 884000, "10": 819000, "11": 756000, "12": 702000, "13": 648000},
}

# 앵커 캘린더 84셀 — NEW_ANCHOR[월][요일(0=월 ... 6=일)] = 시작 칸 인덱스
NEW_ANCHOR = {
     1: [13, 13, 13, 12, 12, 12, 13],
     2: [13, 13, 13, 12, 10, 11, 13],
     3: [13, 12, 13, 12, 12, 12, 13],
     4: [11, 11, 11, 11, 10, 10, 11],
     5: [11, 10, 10, 10,  9,  9, 11],
     6: [11, 11, 11, 11, 10, 10, 11],
     7: [ 9,  8,  9,  8,  7,  7,  9],
     8: [ 7,  6,  7,  6,  5,  5,  7],
     9: [11, 11, 11, 10,  9, 10, 11],
    10: [ 8,  8,  8,  7,  6,  7,  8],
    11: [13, 12, 13, 12, 11, 11, 13],
    12: [12, 10, 11, 10, 10, 10, 11],
}

# =============================================================================
# 2. 달력 — 연휴 / Peak Event Floor
# =============================================================================
# 음력 공휴일의 양력 확정일. 새 연도를 쓸 때 여기 한 줄만 추가하면 됩니다.
NEW_LUNAR = {
    2026: {"설날": (2, 17), "추석": (9, 25), "부처님오신날": (5, 24)},
    2027: {"설날": (2,  6), "추석": (9, 15), "부처님오신날": (5, 13)},
    2028: {"설날": (1, 26), "추석": (10, 3), "부처님오신날": (5,  2)},
}
# 양력 고정 공휴일 (월, 일, 명칭)
NEW_FIXED_HOLIDAYS = [
    (1, 1, "신정"), (3, 1, "삼일절"), (5, 5, "어린이날"), (6, 6, "현충일"),
    (8, 15, "광복절"), (10, 3, "개천절"), (10, 9, "한글날"), (12, 25, "크리스마스"),
]
# 주말과 겹치면 대체공휴일이 생기는 공휴일
NEW_SUBSTITUTE = {"설날", "추석", "어린이날", "삼일절", "광복절", "개천절",
                 "한글날", "부처님오신날", "크리스마스"}
# 대체공휴일 자동 생성에서 뺄 날짜 (연, 월, 일)
#   2026-09-28: 기존 운영 캘린더가 '일반 월요일'로 보고 있어 확정 적용표와 맞췄습니다.
#   실제 관보에 대체공휴일로 확정되면 이 줄을 지우십시오.
NEW_HOLIDAY_EXCLUDE = {(2026, 9, 28)}
# 설날 · 추석은 당일 기준 이 범위까지 연휴로 봅니다 (샌드위치 데이 포함).
#   2026 추석 09/25(금) → 09/24 ~ 09/27  |  2027 설날 02/06(토) → 02/05 ~ 02/08
NEW_LUNAR_SPREAD = (-1, 2)

# 공휴일 달력에는 없지만 '수요상' 연휴로 취급하는 구간 (월,일)~(월,일)
#   10/1~10/10 : 중국 국경절(인바운드) + 개천절 + 한글날이 한 덩어리로 붙습니다.
NEW_EXTRA_HOLIDAY_RANGES = [
    ((10, 1), (10, 10), "국경절 · 개천절 · 한글날"),
    ((12, 24), (12, 26), "크리스마스 연휴"),
    ((12, 31), (12, 31), "연말"),
]

# --- Peak Event Floor (Opening Floor) ---------------------------------------
# "한 번 싸게 노출해 선점된 재고는 되돌릴 수 없다" → 이벤트일은 최소 칸을 박습니다.
# 형식: (시작 오프셋, 끝 오프셋, 최소 칸 라벨, 표시명)
#   설날/추석은 당일(0)을 기준으로 -1 ~ +1 이 핵심 3일입니다.
NEW_EVENT_FLOOR_LUNAR = {
    "추석": [(-1, 1, "3", "추석 핵심일")],
    "설날": [(-1, 1, "3", "설날 핵심일")],
}
# 형식: ((시작월,일), (끝월,일), 최소 칸 라벨, 표시명)
NEW_EVENT_FLOOR_FIXED = [
    ((10, 1), (10, 5), "3", "10월 연휴 핵심일"),
    ((10, 9), (10, 10), "3", "한글날 연휴"),
    ((12, 24), (12, 24), "3", "크리스마스 이브"),
    ((12, 25), (12, 25), "2", "크리스마스"),
    ((12, 26), (12, 26), "2", "크리스마스 연휴"),
    ((12, 31), (12, 31), "2", "연말"),
    # ※ 쇼울더(추석 마지막날, 10/6~10/8)는 의도적으로 floor 없음 — 페이스가 내리도록 둡니다.
    # ※ 여름 최성수기(7/25~8/8)는 앵커가 이미 B2~B4 구간이라 floor를 두지 않았습니다.
    #    실측 후 필요하면 아래 한 줄을 주석 해제하십시오.
    # ((7, 25), (8, 8), "4", "여름 최성수기"),
]

# --- Scarcity Floor (Absolute Floor) ----------------------------------------
# 호텔 총잔여율 → 절대 최소 칸. 자동 해제도, 승인 완화도 없습니다.
NEW_SCARCITY_FLOOR = [
    (0.05, "1"),   # 총잔여 5% 이하  → 최소 B1
    (0.12, "3"),   # 12% 이하        → 최소 B3
    (0.20, "4"),   # 20% 이하        → 최소 B4
]

# =============================================================================
# 3. 조정 단계 파라미터
# =============================================================================
NEW_HOLIDAY_STEP = 2            # 연휴 상향 칸 수 (2칸 = x1.166)

# 페이스(픽업) — 기존 앱의 소진예상일 로직을 그대로 재사용합니다.
#   ratio = (잔여 / 하루당 판매) / 남은 일수
NEW_PACE_RULES = [
    (0.25, -2),                # 남은 시간의 1/4 만에 소진될 속도 → 2칸 상향
    (0.50, -1),
    (2.00,  0),                # 정상
    (4.00, +1),
    (10 ** 9, +2),
]
NEW_PACE_FLOOR = 0.1           # 픽업 0일 때 쓰는 하한 (10일에 1실)
NEW_PACE_LEAD_UP_MAX = 44      # 상향 신호는 D-44 이내에서만 (Final 6.6 페이스 창)
NEW_PACE_LEAD_DOWN_MAX = 21    # 하향 신호는 D-21 이내에서만 (기존 앱 비대칭 유지)
NEW_PACE_MIN_AVAIL = 1
NEW_PACE_HOLD_REMH = 0.25      # 총잔여율이 이보다 낮으면 하향 보류
NEW_SNAPSHOT_INTERVAL_DAYS = 1

# 호텔 총재고에서 상시 빼는 실수 (house use · OOO · comp).
#   업로드 리포트의 '전체객실'에는 이 방들이 포함돼 있습니다. 확정 적용표는
#   sellable(=cap-ooo-house-comp)을 썼기 때문에 이 값을 0으로 두면 총잔여율이
#   최대 1~2%p 낮게(=덜 희소하게) 나옵니다. 상시 house use가 있으면 실수로 넣으십시오.
NEW_SELLABLE_ADJ = 0

# 호텔 재고 — 리드타임과 무관하게 항상 적용 (재고는 관찰 대상이 아니라 사실)
NEW_INV_RULES = [
    (0.05, -3),
    (0.12, -2),
    (0.20, -1),
]

# 객실타입 조정
NEW_TYPE_TIGHT = [(0.15, -2), (0.30, -1)]      # 타입 잔여율 이하 → 상향 칸 수
NEW_TYPE_LOOSE_2 = (0.85, 0.60)                # (타입잔여, 총잔여) 이상 → 2칸 하향
NEW_TYPE_LOOSE_1 = (0.70, 0.40)                # (타입잔여, 총잔여) 이상 → 1칸 하향
NEW_TYPE_LOOSE_LEAD = 44                       # 하향은 D-44 이내에서만
NEW_TYPE_LOOSE_EXCLUDE = {"GDB"}               # 그린밸리 더블은 하향 제외
NEW_TYPE_SCARCE_REMH = 0.20                    # 그날 총잔여 20% 이하면 남은 타입은 희소재
NEW_TYPE_RUNG_MIN = 1                          # 상향 한계
NEW_TYPE_RUNG_MAX = 13                         # 하향 한계 (B10). B11~B13은 승인 항목
NEW_APPROVAL_RUNG = 4                          # 칸 4(B1) 이상 고가는 헤드룸 = RM 승인

# 재심사 (Opening Floor 완화 3조건)
NEW_REVIEW_LEAD = 45           # 재검증일 = 입실일 - 45일
NEW_REVIEW_PACE = 0.85         # 페이스가 이보다 낮아야 완화 후보
NEW_REVIEW_REMH = 0.25         # 총잔여율이 이보다 커야 완화 후보

# =============================================================================
# 4. 하한 · 할인 레이어  (전부 '순실수령' 기준. 노출가 기준이 아닙니다)
# =============================================================================
NEW_MEMBER_K = 0.90            # 회원 노출가 = 로드(BAR) x 0.90
NEW_FLOOR_FLEX = 0.72          # 상시 Flexible 순실수령 하한
NEW_FLOOR_NRF = 0.66           # 상시 NRF 순실수령 하한
NEW_FLOOR_APPROVAL = 0.70      # 경영 승인선
NEW_FLOOR_DISPLAY = 0.70       # 노출가 절대선 (BAR x 0.70)
NEW_OTA_COMM = 0.18            # 해외 OTA 표준 수수료

# 상시/캠페인 레이어 (명칭, 목표계수 k, 회원중첩 여부, 취소정책, 하한)
NEW_LAYERS = [
    ("BAR 정가 Flexible",        0.9000, True,  "Flexible",  NEW_FLOOR_FLEX),
    ("BAR 환불불가 (NRF)",        0.8550, True,  "NRF",       NEW_FLOOR_NRF),
    ("얼리버드 D-15~30",          0.8550, True,  "Flexible",  NEW_FLOOR_FLEX),
    ("얼리버드 D-31~60",          0.8280, True,  "NRF",       NEW_FLOOR_NRF),
    ("얼리버드 D-61+",            0.8100, True,  "NRF 필수",  NEW_FLOOR_NRF),
    ("연박 2박+",                0.8019, True,  "Flexible",  NEW_FLOOR_FLEX),
    ("해외 프로모션 (표기 40%)",   0.7800, False, "NRF 필수",  NEW_FLOOR_NRF),
    ("얼리버드 D-61+ x 연박 중첩", 0.7217, True,  "NRF",       NEW_FLOOR_NRF),
    ("라이브 · 공동구매",         0.7200, False, "NRF 필수",  NEW_FLOOR_NRF),
]
# 해외 프로모션 랙 — 회원 중첩이 없으므로 가산(x1.30). 랙 x (1-40%) = BAR x 0.78
NEW_RACK_MULT = 1.30
NEW_RACK_DISPLAY_DISCOUNT = 0.40
NEW_RACK_CHANNELS = [
    ("아고다",        "Agoda 회원가/쿠폰", "입금가", 0.00),
    ("부킹닷컴",      "Genius",           "판매가", 0.18),
    ("익스피디아 E.C", "One Key",          "입금가", 0.00),
    ("익스피디아 H.C", "One Key",          "판매가", 0.18),
    ("트립닷컴",      "Trip 회원가",       "입금가", 0.00),
    ("야놀자",        "쿠폰",             "입금가", 0.00),
    ("여기어때",      "쿠폰",             "입금가", 0.00),
]

# 목표 정의 B 상수 (읽기 전용 표시용)
NEW_TARGET = {
    "wc": 0.02709,        # 가중 수수료율
    "scb": 0.03219,       # 직판 서비스료 기여율
    "need_gross": 327171, # 필요 Gross ADR (원)
    "up": 0.18539,        # 직전연도 실현 대비 +18.54%
    "bar_need": 418849,   # 필요 이론 BAR
    "bar_ach": 418899,    # 실제 사다리 가중 BAR
    "f": 0.873059,        # 믹스 계수
    "nrf": 0.38,          # NRF 목표 비중
}

# 부킹 로드 정책 3단
NEW_BOOKING_POLICY = [
    ("자동",   "BAR x 0.90 이상", "회원 노출가 = 로드가 x 0.90. RM 시스템이 자동으로 로드합니다."),
    ("승인",   "BAR x 0.72 ~ 0.90", "상시 레이어 범위. 채널 담당이 설정하고 RM이 사후 확인합니다."),
    ("캠페인", "BAR x 0.66 미만", "환불불가 · 기간한정 · 물량상한 3조건 전부 충족 + RM 승인 필수."),
]

WD_KR = ['월', '화', '수', '목', '금', '토', '일']


# =============================================================================
# 5. 달력 계산
# =============================================================================
def _md(d):
    return (d.month, d.day)


def _in_md_range(d, a, b):
    """(월,일) 범위 포함 여부. 연말연시처럼 해를 넘기는 범위도 처리."""
    md = _md(d)
    if a <= b:
        return a <= md <= b
    return md >= a or md <= b


@st.cache_data(show_spinner=False)
def new_holiday_map(years):
    """연도 목록 → {date: 연휴명}. 대체공휴일까지 포함."""
    out = {}

    def put(dd, nm):
        if dd not in out:
            out[dd] = nm

    for y in years:
        base = []
        for m, dy, nm in NEW_FIXED_HOLIDAYS:
            try:
                base.append((date(y, m, dy), nm))
            except ValueError:
                continue
        for nm, (m, dy) in NEW_LUNAR.get(y, {}).items():
            try:
                base.append((date(y, m, dy), nm))
            except ValueError:
                continue

        # 관보상 공휴일(대체공휴일 산출의 근거가 되는 날) = 설날/추석 당일 +-1일
        official = list(base)
        for d0, nm in list(base):
            if nm in ("설날", "추석"):
                for off in (-1, 1):
                    official.append((d0 + timedelta(days=off), nm + " 연휴"))
        taken = {d for d, _ in official}

        # 수요상 연휴로 넓히는 날 (샌드위치 데이) — 대체공휴일은 만들지 않습니다.
        spread = []
        for d0, nm in list(base):
            if nm in ("설날", "추석"):
                for off in range(NEW_LUNAR_SPREAD[0], NEW_LUNAR_SPREAD[1] + 1):
                    if off != 0:
                        spread.append((d0 + timedelta(days=off), nm + " 연휴"))

        for d0, nm in official + spread:
            put(d0, nm)

        # 대체공휴일 (관보상 공휴일이 토·일과 겹칠 때만)
        for d0, nm in sorted(official):
            root = nm.replace(" 연휴", "")
            if root not in NEW_SUBSTITUTE or d0.weekday() < 5:
                continue
            cand = d0 + timedelta(days=1)
            while cand in taken or cand.weekday() >= 5:
                cand += timedelta(days=1)
            taken.add(cand)
            if (cand.year, cand.month, cand.day) in NEW_HOLIDAY_EXCLUDE:
                continue
            put(cand, root + " 대체공휴일")

        for (a, b, nm) in NEW_EXTRA_HOLIDAY_RANGES:
            try:
                s, e = date(y, a[0], a[1]), date(y, b[0], b[1])
            except ValueError:
                continue
            cur = s
            while cur <= e:
                put(cur, nm)
                cur += timedelta(days=1)
    return out


@st.cache_data(show_spinner=False)
def new_event_floor_map(years):
    """연도 목록 → {date: (표시명, 최소 칸 라벨)}. Peak Event Floor."""
    out = {}

    def put(dd, nm, lab):
        cur = out.get(dd)
        idx = NEW_RI[lab]
        if cur is None or idx < NEW_RI[cur[1]]:
            out[dd] = (nm, lab)

    for y in years:
        for nm, (m, dy) in NEW_LUNAR.get(y, {}).items():
            rules = NEW_EVENT_FLOOR_LUNAR.get(nm)
            if not rules:
                continue
            try:
                d0 = date(y, m, dy)
            except ValueError:
                continue
            for a, b, lab, disp in rules:
                for off in range(a, b + 1):
                    put(d0 + timedelta(days=off), disp, lab)
        for (a, b, lab, disp) in NEW_EVENT_FLOOR_FIXED:
            try:
                s, e = date(y, a[0], a[1]), date(y, b[0], b[1])
            except ValueError:
                continue
            cur = s
            while cur <= e:
                put(cur, disp, lab)
                cur += timedelta(days=1)
    return out


def new_scarcity_floor(remh):
    """총잔여율 → Absolute Floor 칸 인덱스 (없으면 None)."""
    if remh is None or remh != remh:
        return None
    for thr, lab in NEW_SCARCITY_FLOOR:
        if remh <= thr:
            return NEW_RI[lab]
    return None


# =============================================================================
# 6. 단계 함수
# =============================================================================
def new_anchor(d):
    """앵커 캘린더 → 시작 칸 인덱스."""
    return NEW_ANCHOR[d.month][d.weekday()]


def new_pace_ratio(avail, pickup_per_day, days_left):
    """소진예상일 ÷ 남은일수. 판단 불가면 None."""
    if pickup_per_day is None or days_left is None or days_left <= 0:
        return None
    try:
        av = float(avail)
    except (TypeError, ValueError):
        return None
    if av != av or av < NEW_PACE_MIN_AVAIL:
        return None
    est = av / max(float(pickup_per_day), NEW_PACE_FLOOR)
    return est / days_left


def new_pace_step(ratio, days_left, remh):
    """페이스 조정 칸 수. 음수 = 상향(비싸게), 양수 = 하향(싸게)."""
    if ratio is None or days_left is None or days_left <= 0:
        return 0
    step = NEW_PACE_RULES[-1][1]
    for thr, s in NEW_PACE_RULES:
        if ratio <= thr:
            step = s
            break
    if step < 0 and days_left > NEW_PACE_LEAD_UP_MAX:
        return 0
    if step > 0 and days_left > NEW_PACE_LEAD_DOWN_MAX:
        return 0
    # 재고가 없어서 안 팔린 것은 하향의 근거가 아닙니다.
    if step > 0 and remh is not None and remh == remh and remh < NEW_PACE_HOLD_REMH:
        return 0
    return step


def new_inventory_step(remh):
    """호텔 총잔여율 → 상향 칸 수 (음수)."""
    if remh is None or remh != remh:
        return 0
    for thr, s in NEW_INV_RULES:
        if remh <= thr:
            return s
    return 0


def new_zone(days_left):
    if days_left is None:
        return ""
    if days_left > 44:
        return "관찰 (D-45+)"
    if days_left > 30:
        return "재고 조정"
    return "요금 액션"


def new_raw(rt, rung):
    """타입 × 칸의 반올림 전 원가 (RUNG x MULT). 파생 요금은 여기서 한 번만 반올림합니다."""
    r = max(1, min(NEW_N, int(rung)))
    return NEW_RUNG[r] * NEW_MULT.get(rt, 1.0)


def new_load_price(rt, rung):
    """타입 × 칸 → 로드(BAR) 기준가. 발행된 타입별 요금표를 그대로 씁니다."""
    return NEW_TABLE.get(rt, {}).get(NEW_LAB[max(1, min(NEW_N, int(rung))) - 1], 0)


def new_k_price(rt, rung, k):
    """타입 × 칸 × 계수 → 천원 단위 요금.

    ※ 로드가(이미 천원 반올림)에 다시 계수를 곱하지 않고, 반올림 전 원가에서
      한 번만 반올림합니다. 확정 적용표·마스터의 표기와 동일한 경로입니다.
    """
    return int(round(new_raw(rt, rung) * k / 1000) * 1000)


def new_member_price(rt, rung):
    """타입 × 칸 → 회원 노출가 (BAR x 0.90)."""
    return new_k_price(rt, rung, NEW_MEMBER_K)


# =============================================================================
# 7. 재고 · 픽업 집계
# =============================================================================
def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _as_date(v):
    """Timestamp · datetime · date · 'YYYY-MM-DD' 를 모두 datetime.date 로.

    ※ 이게 없으면 조용한 사고가 납니다. 한쪽 프레임의 Date 가 pd.Timestamp,
      다른 쪽이 datetime.date 이면 (Date, RoomID) 키가 절대 안 맞아서
      픽업이 전부 비고, 페이스가 통째로 사라집니다.
    """
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        t = pd.to_datetime(v, errors='coerce')
    except (TypeError, ValueError):
        return None
    if t is None or t is pd.NaT or t != t:
        return None
    try:
        return t.date()
    except AttributeError:
        return None


def new_normalize(df):
    """업로드/스냅샷 프레임의 키 타입을 통일하고 중복행을 제거합니다.

    Date → datetime.date, RoomID → 대문자 문자열. 두 프레임을 비교하기 전에
    반드시 통과시켜야 키가 맞습니다.
    """
    if df is None or not hasattr(df, 'empty') or df.empty:
        return df
    if not {'Date', 'RoomID'} <= set(df.columns):
        return df
    out = df.copy()
    out['Date'] = out['Date'].map(_as_date)
    out['RoomID'] = out['RoomID'].map(
        lambda v: str(v).strip().upper() if v is not None else "")
    out = out[out['Date'].notna() & (out['RoomID'] != "")]
    if out.empty:
        return out
    return out.drop_duplicates(subset=['Date', 'RoomID'], keep='first')


def _numcol(s_, mul=1.0):
    """어떤 dtype 이든 숫자 Series 로. None 만 든 object 컬럼에 .round() 를
    걸면 TypeError 가 나므로, 표를 만들기 전에 반드시 통과시킵니다."""
    return pd.to_numeric(s_, errors='coerce') * mul


def new_hotel_inventory(curr_df):
    """{date: dict(tot_avail, tot_rooms, remh, occ)}  — 정상 행만 집계.

    ※ 기존 V2 엔진은 타입별 잔여의 음수를 0으로 올려 잡습니다(min/max 클램프).
      신 로직은 Final 6.6 정의대로 오버부킹(음수)을 호텔 합계에서 그대로 상계합니다.
      오버부킹은 '팔 게 없다'가 아니라 '이미 초과로 팔았다'이므로, 호텔 전체
      판매 여력을 볼 때는 차감돼야 합니다. (예: 2026-11-28 잔여 17실이 아니라 15실)
    """
    out = {}
    if curr_df is None or curr_df.empty:
        return out
    for d, g in curr_df.groupby('Date'):
        av_sum = 0.0
        tot_sum = 0.0
        for _, r in g.iterrows():
            tot = _num(r.get('Total'))
            av = _num(r.get('Available'))
            if tot is None or tot <= 0 or av is None:
                continue
            av_sum += min(av, tot)
            tot_sum += tot
        tot_sum = max(0.0, tot_sum - NEW_SELLABLE_ADJ)
        if tot_sum <= 0:
            out[d] = dict(tot_avail=float('nan'), tot_rooms=0.0,
                          remh=float('nan'), occ=float('nan'))
        else:
            out[d] = dict(tot_avail=av_sum, tot_rooms=tot_sum,
                          remh=av_sum / tot_sum,
                          occ=(tot_sum - av_sum) / tot_sum * 100)
    return out


def new_pickup_map(curr_df, prev_df):
    """이전 기록 대비 하루당 판매 실수. {(date, rt): per_day}

    ※ 이 함수가 "이전 기록 대비 새 파일에서 바뀌면 요금이 움직인다"의 심장입니다.
      기존 앱의 get_pickup_per_day()와 같은 계산이며, 결과만 새 사다리에 꽂힙니다.
    """
    out = {}
    if curr_df is None or curr_df.empty or prev_df is None or prev_df.empty:
        return out
    try:
        p = prev_df.set_index(['Date', 'RoomID'])['Available']
        c = curr_df.set_index(['Date', 'RoomID'])['Available']
    except Exception:
        return out
    p = p[~p.index.duplicated(keep='first')]
    c = c[~c.index.duplicated(keep='first')]
    for key, cv in c.items():
        if key not in p.index:
            continue
        pa, ca = _num(p.loc[key]), _num(cv)
        if pa is None or ca is None:
            continue
        out[key] = max(0.0, pa - ca) / max(1, NEW_SNAPSHOT_INTERVAL_DAYS)
    return out


# =============================================================================
# 8. 날짜 칸 계산 (6단계)
# =============================================================================
def new_compute_days(curr_df, prev_df=None, today=None, overrides=None):
    """일자별 칸 배정. 반환: DataFrame (날짜 오름차순)."""
    if today is None:
        today = date.today()
    overrides = overrides or {}

    # ※ 키 타입 통일 + 중복행 제거. 이 두 줄이 픽업이 조용히 비는 사고를 막습니다.
    curr_df = new_normalize(curr_df)
    prev_df = new_normalize(prev_df)

    inv = new_hotel_inventory(curr_df)
    pk = new_pickup_map(curr_df, prev_df)

    # ── 이전 기록이 현재와 완전히 같은 경우 방어 ────────────────────
    #  같은 스냅샷을 '이전 기록'으로 붙이면 모든 셀의 판매가 0이 됩니다.
    #  그건 "어제 하나도 안 팔렸다"가 아니라 "시간이 흐르지 않았다"입니다.
    #  픽업 0을 그대로 쓰면 소진예상일이 무한히 길어져 페이스가 전부 하향으로
    #  기울기 때문에, 이 경우엔 페이스를 아예 판단 불가로 둡니다.
    prev_stale = bool(pk) and len(pk) >= 20 and all(v == 0 for v in pk.values())
    if prev_stale:
        pk = {}

    dates = sorted(inv.keys())
    years = sorted({d.year for d in dates}) or [today.year]
    HOL = new_holiday_map(tuple(years))
    EVF = new_event_floor_map(tuple(years))

    # 호텔 단위 픽업 = 타입 픽업 합
    hotel_pk = {}
    for (d, _rt), v in pk.items():
        hotel_pk[d] = hotel_pk.get(d, 0.0) + v

    rows = []
    for d in dates:
        m = inv[d]
        remh = m['remh']
        remh = remh if remh == remh else None
        dta = (d - today).days
        anchor = new_anchor(d)

        # 1 앵커 → 2 연휴
        hol = HOL.get(d, "")
        idx_hol = anchor - (NEW_HOLIDAY_STEP if hol else 0)

        # 3 페이스 (이전 기록 대비 픽업)
        pu = hotel_pk.get(d)
        ratio = new_pace_ratio(m['tot_avail'], pu, dta)
        padj = new_pace_step(ratio, dta, remh)

        # 4 호텔 재고
        iadj = new_inventory_step(remh)

        pre = int(max(1, min(NEW_N, idx_hol + padj + iadj)))

        # 5 Peak Event Floor / 6 Scarcity Floor — 더 높은(작은 인덱스) 쪽이 구속
        ev = EVF.get(d)
        ef = NEW_RI[ev[1]] if ev else None
        sf = new_scarcity_floor(remh)
        cands = [x for x in (ef, sf) if x is not None]
        floor = min(cands) if cands else None
        rung = min(pre, floor) if floor else pre

        fby, fkind = "", ""
        if floor and rung < pre:
            if ef is not None and ef == rung and (sf is None or ef <= sf):
                fby = "이벤트 (%s)" % ev[0]
                fkind = "Opening (D-45 재심사)"
            else:
                fby = "희소재고 (총잔여 %.1f%%)" % (remh * 100 if remh is not None else 0)
                fkind = "Absolute (해제 없음)"

        # Opening Floor 재심사 판정
        rev, revd = "", ""
        if ef is not None:
            revd = (d - timedelta(days=NEW_REVIEW_LEAD)).strftime('%m/%d')
            binding = (rung < pre) and fby.startswith("이벤트")
            if not binding:
                rev = "구속 안 함 (계산 칸이 floor보다 높음)"
            elif dta > NEW_REVIEW_LEAD:
                rev = "재심사 전 — %s에 판정" % revd
            elif ratio is None:
                rev = "재심사: 페이스 표본 부족 → floor 유지"
            elif remh is not None and remh <= NEW_REVIEW_REMH:
                rev = "재심사: 잔여 %.0f%% — 재고 부족으로 완화 금지" % (remh * 100)
            elif ratio <= 2.0:
                rev = "재심사 통과 (소진 %.2f배) → floor 유지" % ratio
            else:
                rev = "★ 완화 후보 (소진 %.2f배 · 잔여 %.0f%%) — RM 승인 시 1칸" % (
                    ratio, (remh or 0) * 100)

        # 날짜 단위 수동 고정
        ov = overrides.get(d.strftime('%Y-%m-%d'), {}).get('_DAY')
        ov_idx = new_idx(ov)
        is_ov = False
        if ov_idx:
            rung, is_ov = ov_idx, True

        rows.append(dict(
            date=d, dow=WD_KR[d.weekday()], dta=dta, zone=new_zone(dta), hol=hol,
            anchor=anchor, anchor_lab=new_lab(anchor),
            after_hol=idx_hol, pickup=pu, pace_ratio=ratio, pace_adj=padj,
            remh=remh, occ=m['occ'], tot_avail=m['tot_avail'], tot_rooms=m['tot_rooms'],
            inv_adj=iadj, pre=pre, pre_lab=new_lab(pre),
            ev=(ev[0] if ev else ""), ev_floor=(new_lab(ef) if ef else ""),
            ev_relax=(new_lab(min(ef + 1, NEW_N)) if ef else ""),
            sc_floor=(new_lab(sf) if sf else ""),
            floor=(new_lab(floor) if floor else ""), floor_by=fby, floor_kind=fkind,
            review=rev, review_date=revd,
            rung=rung, lab=new_lab(rung), is_override=is_ov,
            hdt_load=new_load_price("HDT", rung), hdt_member=new_member_price("HDT", rung),
            prev_stale=prev_stale,
        ))
    return pd.DataFrame(rows)


# =============================================================================
# 9. 객실타입 칸 계산 (7단계)
# =============================================================================
def new_compute_types(curr_df, day_df, today=None, overrides=None):
    """객실타입별 칸 배정. 반환: DataFrame."""
    if today is None:
        today = date.today()
    overrides = overrides or {}
    if day_df is None or day_df.empty or curr_df is None or curr_df.empty:
        return pd.DataFrame()

    base = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
    # ※ 키 타입 통일 + 중복행 제거 (렌더에서 .loc 이 Series 를 돌려주도록)
    src = new_normalize(curr_df)
    if src is None or src.empty:
        return pd.DataFrame()
    rows = []
    for _, r in src.iterrows():
        d = r['Date']
        rt = r['RoomID']
        rt = str(rt).strip().upper() if rt is not None else ""
        if d not in base.index or rt not in NEW_TABLE:
            continue
        info = base.loc[d]
        dbase = int(info['rung'])
        remh = _num(info['remh'])      # None 도 NaN 도 여기서 None 이 됩니다
        dta = int(info['dta'])

        cap = _num(r.get('Total'))
        av = _num(r.get('Available'))
        remt = (av / cap) if (cap and cap > 0 and av is not None) else None

        tadj, state, why = 0, "판매", ""
        if av is None or cap is None or cap <= 0:
            state, why = "데이터 이상", "잔여/전체 결측 — 날짜 칸을 그대로 씁니다"
        elif av <= 0:
            state = "마감" if av == 0 else "오버부킹"
            why = "팔 재고 없음 — 요금은 참고값"
        else:
            hit = False
            for thr, s in NEW_TYPE_TIGHT:
                if remt is not None and remt <= thr:
                    tadj, why, hit = s, "타입 잔여 %d%% 이하" % int(thr * 100), True
                    break
            if not hit and dta <= NEW_TYPE_LOOSE_LEAD and rt not in NEW_TYPE_LOOSE_EXCLUDE \
                    and remt is not None and remh is not None:
                if remt >= NEW_TYPE_LOOSE_2[0] and remh >= NEW_TYPE_LOOSE_2[1]:
                    tadj, why = +2, "타입만 크게 남음"
                elif remt >= NEW_TYPE_LOOSE_1[0] and remh >= NEW_TYPE_LOOSE_1[1]:
                    tadj, why = +1, "타입 여유"
            if remh is not None and remh <= NEW_TYPE_SCARCE_REMH and tadj >= 0:
                tadj = min(tadj, 0) - 1
                why = "그날 거의 매진 — 남은 타입은 희소재"

        rung = int(max(NEW_TYPE_RUNG_MIN, min(NEW_TYPE_RUNG_MAX, dbase + tadj)))

        ov = overrides.get(d.strftime('%Y-%m-%d'), {}).get(rt)
        ov_idx = new_idx(ov)
        is_ov = False
        if ov_idx:
            rung, is_ov, why = ov_idx, True, "수동 예외"

        rows.append(dict(
            date=d, dow=WD_KR[d.weekday()], dta=dta, rt=rt,
            cap=int(cap) if cap else 0, avail=av, remt=remt,
            day_rung=dbase, day_lab=new_lab(dbase), tadj=tadj,
            rung=rung, lab=new_lab(rung), state=state, why=why,
            approval=("헤드룸 (RM 승인)" if rung <= NEW_APPROVAL_RUNG else ""),
            load=new_load_price(rt, rung), member=new_member_price(rt, rung),
            rack=new_k_price(rt, rung, NEW_RACK_MULT),
            floor_flex=new_k_price(rt, rung, NEW_FLOOR_FLEX),
            floor_nrf=new_k_price(rt, rung, NEW_FLOOR_NRF),
            floor_display=new_k_price(rt, rung, NEW_FLOOR_DISPLAY),
            stop=bool(av is not None and av <= 0), is_override=is_ov,
        ))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['rt'] = pd.Categorical(df['rt'], categories=NEW_ROOMS, ordered=True)
    return df.sort_values(['date', 'rt']).reset_index(drop=True)

# =============================================================================
# 10. Firestore — 신 로직 예외는 기존 컬렉션을 건드리지 않고 별도로 보관합니다
# =============================================================================
NEW_COL_APPLIED = "applied_rates_v3"     # 문서 ID = YYYY-MM-DD, {rooms:{RT:칸라벨}, memo}
NEW_COL_AUDIT = "audit_log_v3"


def new_load_overrides(db, force=False):
    """{ 'YYYY-MM-DD': {'rooms': {...}, 'memo': str, 'saved_at': str} }"""
    if db is None:
        return st.session_state.get('_new_ov_local', {})
    if not force and '_new_ov_cache' in st.session_state:
        return st.session_state['_new_ov_cache']
    out = {}
    try:
        for doc in db.collection(NEW_COL_APPLIED).stream():
            out[doc.id] = doc.to_dict() or {}
    except Exception as e:
        st.warning(f"신 로직 예외 불러오기 실패 — 이번 화면은 예외 없이 계산합니다. ({e})")
    st.session_state['_new_ov_cache'] = out
    return out


def new_override_map(raw):
    """Firestore 문서 → {'YYYY-MM-DD': {RT: 칸라벨}} (계산 함수가 먹는 형태)"""
    out = {}
    for ds, info in (raw or {}).items():
        rooms = (info or {}).get('rooms') or {}
        clean = {}
        for rt, v in rooms.items():
            if new_idx(v) is not None:
                clean[rt] = str(v).strip()
        if clean:
            out[ds] = clean
    return out


def new_save_override(db, date_str, rooms, memo=""):
    payload = {
        'rooms': {k: v for k, v in (rooms or {}).items() if new_idx(v) is not None},
        'memo': memo,
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'edition': NEW_EDITION,
    }
    if db is None:
        loc = st.session_state.setdefault('_new_ov_local', {})
        loc[date_str] = payload
        return True, "세션에만 저장됐습니다 (DB 미연결)"
    try:
        db.collection(NEW_COL_APPLIED).document(date_str).set(payload)
        try:
            db.collection(NEW_COL_AUDIT).add({
                'action': 'new_apply', 'target_date': date_str,
                'rooms': payload['rooms'], 'memo': memo,
                'at': payload['saved_at'],
            })
        except Exception:
            pass
        st.session_state.pop('_new_ov_cache', None)
        return True, "저장 완료"
    except Exception as e:
        return False, str(e)


def new_delete_override(db, date_str):
    if db is None:
        st.session_state.setdefault('_new_ov_local', {}).pop(date_str, None)
        return True, "세션에서 삭제"
    try:
        db.collection(NEW_COL_APPLIED).document(date_str).delete()
        try:
            db.collection(NEW_COL_AUDIT).add({
                'action': 'new_delete', 'target_date': date_str,
                'at': datetime.now().isoformat(timespec='seconds')})
        except Exception:
            pass
        st.session_state.pop('_new_ov_cache', None)
        return True, "삭제 완료"
    except Exception as e:
        return False, str(e)


# =============================================================================
# 11. 색상 · HTML 유틸
# =============================================================================
# 16칸 램프 — 왼쪽(비쌈)이 진한 적색, 오른쪽(쌈)이 연한 녹색
_NEW_RAMP = [
    ("#6B0000", "#FFFFFF"), ("#8A0F0F", "#FFFFFF"), ("#A81C1C", "#FFFFFF"),
    ("#C22727", "#FFFFFF"), ("#D63A2E", "#FFFFFF"), ("#E4573C", "#FFFFFF"),
    ("#EE7150", "#3A0B00"), ("#F79470", "#3A0B00"), ("#FDB595", "#4A1400"),
    ("#FFD3BC", "#4A1400"), ("#F2E7D2", "#33301F"), ("#DCEBCF", "#1F3320"),
    ("#C6E3C4", "#14331C"), ("#DCF0DC", "#14331C"), ("#EAF6EA", "#14331C"),
    ("#F4FAF2", "#14331C"),
]


def new_color(rung):
    i = max(1, min(NEW_N, int(rung))) - 1
    return _NEW_RAMP[i]


def _won(v):
    try:
        return "{:,}".format(int(v))
    except (TypeError, ValueError):
        return "-"


def _pct(v, nd=1):
    if v is None or v != v:
        return "-"
    return ("{:." + str(nd) + "f}%").format(v * 100)


def _numf(v, default=0.0):
    """어떤 값이든 안전하게 float 으로. None · NaN · 빈칸 · 문자열 모두 default.

    ※ 이 함수가 필요한 이유: 파이썬에서 NaN 은 참(truthy)입니다.
      `float(x) or 0` 은 NaN 을 걸러내지 못하고 그대로 통과시키고,
      그 NaN 이 int(round(...)) 에 닿는 순간 ValueError 로 화면이 죽습니다.
      이지에디터·업로드 데이터의 빈 칸은 전부 NaN 으로 들어옵니다.
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        try:
            f = float(str(v).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return default
    if f != f or f in (float('inf'), float('-inf')):   # NaN · inf
        return default
    return f


def _txt(v, default=""):
    """None · NaN · 'nan' 을 걸러낸 문자열."""
    if v is None:
        return default
    try:
        if v != v:          # NaN
            return default
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    if s.lower() in ("", "nan", "none"):
        return default
    return s


NEW_CSS = """
<style>
.rewrap{font-size:13px}
.retbl{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
.retbl th,.retbl td{border:1px solid #E3E7EB;padding:4px 6px;white-space:nowrap;text-align:center}
.retbl thead th{background:#F3F5F7;font-size:11px;font-weight:700;color:#414A54;position:sticky;top:0;z-index:2}
.retbl td.l{text-align:left}
.retbl td.dt{text-align:left;font-weight:700;background:#FAFBFC;position:sticky;left:0;z-index:1}
.retbl tr.hol td.dt{color:#B5602C}
.retbl td.rg{font-weight:700}
.retbl td.rg em{display:block;font-style:normal;font-weight:400;font-size:9.5px;opacity:.8}
.retbl td.stop{background:#F2F3F4;color:#9AA1A8;font-weight:400}
.retbl td.mut{color:#8A929A}
.rescroll{max-height:620px;overflow:auto;border:1px solid #E3E7EB;border-radius:6px}
.rebadge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700}
.renote{border-left:4px solid #1F5C8B;background:#F7FAFC;padding:11px 14px;margin:10px 0;
        font-size:12.5px;line-height:1.65;border-radius:0 6px 6px 0}
.renote.warn{border-left-color:#B5602C;background:#FFF8F2}
.renote.stop{border-left-color:#9D3D34;background:#FDF3F2}
.restep{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;background:#E3E7EB;
        border:1px solid #E3E7EB;margin:6px 0 2px}
.restep>div{background:#fff;padding:12px 14px}
.restep h5{margin:0 0 5px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#1F5C8B}
.restep p{margin:0;font-size:12px;color:#4B5866;line-height:1.55}
.restep code{background:#F1F4F7;padding:1px 4px;border-radius:3px;font-size:11px}
</style>
"""


# =============================================================================
# 12. 탭 1 — 규칙 & 요약
# =============================================================================
def _new_tab_rules(day_df, type_df, today):
    st.markdown(f"""
<div class="renote"><b>이 페이지는 신 요금로직 [{NEW_EDITION}]으로만 계산합니다.</b>
왼쪽 페이지 목록에서 <b>메인</b>으로 돌아가면 기존 로직·기존 요금표가 그대로 나옵니다 — 
app.py 는 한 글자도 고치지 않았습니다. 두 로직은 사다리·요금표·예외 저장소가 전부
분리돼 있어 서로 간섭하지 않습니다.<br>
<b>연도와 무관합니다.</b> 앵커는 "월 x 요일"이고 공휴일은 연도별로 자동 산출하므로,
올린 재고가 몇 년도든 같은 규칙으로 계산합니다.</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="restep">
 <div><h5>1 · 앵커</h5><p>월 × 요일 <b>84셀</b>이 시작 칸을 정합니다. 시즌 구간·주말 판정이 아니라
   실현 ADR로 캘리브레이션한 표입니다.</p></div>
 <div><h5>2 · 연휴</h5><p>공휴일·연휴는 <b>2칸 상향</b>(x1.166). 설날·추석은 음력 확정일 기준
   <code>-1 ~ +2</code>일, 대체공휴일 자동 산출.</p></div>
 <div><h5>3 · 페이스</h5><p><b>이전 기록 대비 새 파일</b>의 판매 실수로 소진예상일을 구해
   <code>+-2칸</code>. 상향은 D-44 이내, 하향은 D-21 이내만. 총잔여 25% 미만이면 하향 보류.</p></div>
 <div><h5>4 · 재고</h5><p>호텔 총잔여율 <code>&lt;=20 / 12 / 5%</code> → <b>1 / 2 / 3칸 상향</b>.
   리드타임과 무관하게 항상 — 재고는 관찰 대상이 아니라 사실입니다.</p></div>
 <div><h5>5 · Peak Event Floor</h5><p>이벤트일 최소 칸. <b>Opening Floor</b>로 D-46 이상 하향 금지,
   <b>D-45에 1회 재심사</b>(3조건 충족 시 RM 승인으로 최대 1칸 완화).</p></div>
 <div><h5>6 · Scarcity Floor</h5><p>총잔여율 <code>&lt;=20/12/5%</code> → 최소 <b>B4 / B3 / B1</b>.
   <b>Absolute Floor</b> — 자동 해제도, 승인 완화도 없습니다.</p></div>
 <div><h5>7 · 객실타입</h5><p>타입 잔여율 <code>&lt;=15 / 30%</code> 2 / 1칸 상향, 여유 타입은 하향.
   그날 총잔여 20% 이하면 남은 타입은 희소재로 1칸 더.</p></div>
 <div><h5>7' · 판매 중지</h5><p>잔여 0 이하는 <b>요금이 아니라 판매를 닫습니다</b>.
   표시 요금은 참고값입니다.</p></div>
</div>
""", unsafe_allow_html=True)

    st.markdown("##### 목표 정의 B — 이 사다리가 겨냥하는 숫자")
    T = NEW_TARGET
    c = st.columns(5)
    c[0].metric("필요 Gross ADR", f"{T['need_gross']:,}원", f"+{T['up']*100:.2f}%")
    c[1].metric("필요 이론 BAR", f"{T['bar_need']:,}원")
    c[2].metric("사다리 가중 BAR", f"{T['bar_ach']:,}원",
                f"{T['bar_ach']-T['bar_need']:+,}원")
    c[3].metric("믹스 계수 f", f"{T['f']:.4f}", f"유효 할인 {100*(1-T['f']):.2f}%")
    c[4].metric("NRF 목표 비중", f"{T['nrf']*100:.0f}%")
    st.caption(
        f"순액 = Gross x [(1 − 가중수수료율 {T['wc']*100:.3f}%) + 서비스료 기여율 {T['scb']*100:.3f}%]"
        f" = Gross x {1 - T['wc'] + T['scb']:.6f}  ·  서비스료는 수수료 대상이 아니므로 곱하지 않고 가산합니다."
    )

    if day_df is None or day_df.empty:
        st.info("리포트를 업로드하면 아래에 현재 재고 기준 요약이 나옵니다.")
        return

    st.divider()
    st.markdown("##### 업로드된 재고에 얹은 결과")
    n_days = len(day_df)
    n_cells = len(type_df) if type_df is not None else 0
    n_stop = int(type_df['stop'].sum()) if (type_df is not None and not type_df.empty) else 0
    n_floor = int((day_df['floor_by'] != "").sum())
    n_ev = int(day_df['floor_by'].str.startswith("이벤트").sum())
    n_sc = int(day_df['floor_by'].str.startswith("희소").sum())
    n_pace_up = int((day_df['pace_adj'] < 0).sum())
    n_pace_dn = int((day_df['pace_adj'] > 0).sum())
    n_inv = int((day_df['inv_adj'] < 0).sum())
    diff_cells = 0
    if type_df is not None and not type_df.empty:
        diff_cells = int((type_df['rung'] != type_df['day_rung']).sum())

    c = st.columns(6)
    c[0].metric("날짜", f"{n_days}일")
    c[1].metric("셀", f"{n_cells:,}")
    c[2].metric("판매 마감 셀", f"{n_stop:,}")
    c[3].metric("floor 적용일", f"{n_floor}일", f"이벤트 {n_ev} · 희소 {n_sc}")
    c[4].metric("페이스 조정", f"↑{n_pace_up} / ↓{n_pace_dn}")
    c[5].metric("타입이 날짜와 다른 셀", f"{diff_cells:,}")

    if n_pace_up == 0 and n_pace_dn == 0:
        st.markdown("""
<div class="renote warn"><b>페이스가 0건입니다.</b> 이전 기록(prev_df)이 없거나 재고 변화가 없어서
판매 속도를 계산할 수 없었습니다. 사이드바에서 리포트를 두 번(어제·오늘) 올리거나
과거 기록을 불러오면 페이스 단계가 살아납니다. 앵커·연휴·재고·floor는 그대로 작동합니다.</div>
""", unsafe_allow_html=True)

    st.markdown("###### 사다리 16칸 (HDT 기준)")
    cells = []
    for i in range(1, NEW_N + 1):
        bg, fg = new_color(i)
        cells.append(
            f"<td class='rg' style='background:{bg};color:{fg}'>{new_lab(i)}"
            f"<em>{_won(NEW_RUNG[i])}</em></td>")
    st.markdown(
        "<div class='rewrap'><div class='rescroll'><table class='retbl'><tbody><tr>"
        + "".join(cells) + "</tr></tbody></table></div></div>",
        unsafe_allow_html=True)
    st.caption("칸 간격 8%. 왼쪽이 비쌉니다. B11~B13은 자동 진입 금지 구간(승인 항목)입니다.")



# =============================================================================
# 13. 이전 기록 대비 자동 비교
# -----------------------------------------------------------------------------
# 기존 앱의 "자동 DB 병합/비교"와 같은 개념입니다. 리포트를 올리면 직전 스냅샷을
# 이전 기록으로 잡고, 그 사이에 재고가 얼마나 빠졌는지 → 그래서 칸을 바꿔야 하는
# 날이 어디인지를 보여줍니다.
#
# 표기 주의
#   '이전 칸' = 그 스냅샷 하나만 보고 정했을 칸 (그 시점엔 더 이전 기록이 없으니
#              페이스 단계는 0). '현재 칸' = 지금 확정 칸 (페이스 포함).
#              그래서 차이에는 '재고가 빠진 효과'와 '페이스 효과'가 함께 들어 있고,
#              어느 쪽이 움직였는지는 '페이스' 열로 갈라 볼 수 있습니다.
# =============================================================================
def new_compute_change(curr_df, prev_df, day_df, type_df, today=None):
    """반환: (day_cmp, type_cmp, summary). prev 가 없으면 (빈, 빈, {})."""
    empty = (pd.DataFrame(), pd.DataFrame(), {})
    if prev_df is None or prev_df.empty or day_df is None or day_df.empty:
        return empty
    if not {'Date', 'RoomID', 'Available', 'Total'} <= set(prev_df.columns):
        return empty
    if today is None:
        today = date.today()
    prev_df = new_normalize(prev_df)
    if prev_df is None or prev_df.empty:
        return empty

    try:
        prev_day = new_compute_days(prev_df, None, today=today)
        prev_type = new_compute_types(prev_df, prev_day, today=today)
    except Exception:
        return empty
    if prev_day.empty:
        return empty

    # ── 날짜 단위 ────────────────────────────────────────────────
    p = prev_day[['date', 'rung', 'lab', 'tot_avail', 'remh', 'occ']].rename(columns={
        'rung': 'p_rung', 'lab': 'p_lab', 'tot_avail': 'p_avail',
        'remh': 'p_remh', 'occ': 'p_occ'})
    d = day_df[['date', 'dow', 'dta', 'hol', 'anchor_lab', 'pace_adj', 'pace_ratio',
                'inv_adj', 'pre_lab', 'floor', 'floor_by', 'rung', 'lab',
                'tot_avail', 'remh', 'occ', 'hdt_member']]
    dc = d.merge(p, on='date', how='inner')
    if dc.empty:
        return empty
    dc['sold'] = dc['p_avail'] - dc['tot_avail']          # 그 사이 판매 실수
    dc['rung_move'] = dc['p_rung'] - dc['rung']           # + 면 비싼 칸으로 올라감
    dc['occ_move'] = dc['occ'] - dc['p_occ']
    dc = dc.sort_values('date').reset_index(drop=True)

    # ── 타입 단위 ────────────────────────────────────────────────
    tc = pd.DataFrame()
    if type_df is not None and not type_df.empty and not prev_type.empty:
        pt = prev_type[['date', 'rt', 'rung', 'lab', 'avail', 'member', 'state']].rename(
            columns={'rung': 'p_rung', 'lab': 'p_lab', 'avail': 'p_avail',
                     'member': 'p_member', 'state': 'p_state'})
        cur = type_df[['date', 'dow', 'dta', 'rt', 'avail', 'cap', 'remt', 'rung',
                       'lab', 'load', 'member', 'state']]
        tc = cur.merge(pt, on=['date', 'rt'], how='inner')
        if not tc.empty:
            tc['sold'] = tc['p_avail'] - tc['avail']
            tc['rung_move'] = tc['p_rung'] - tc['rung']
            tc['price_move'] = tc['member'] - tc['p_member']
            tc = tc.sort_values(['date', 'rt']).reset_index(drop=True)

    stale = bool(len(dc)) and bool((dc['sold'].fillna(0) == 0).all())
    sold_total = float(dc['sold'].fillna(0).sum())
    moved = dc[dc['rung_move'] != 0]
    summary = {
        'days': int(len(dc)),
        'sold_total': sold_total,
        'sold_days': int((dc['sold'].fillna(0) > 0).sum()),
        'moved_days': int(len(moved)),
        'moved_up': int((dc['rung_move'] > 0).sum()),
        'moved_down': int((dc['rung_move'] < 0).sum()),
        'pace_up': int((dc['pace_adj'] < 0).sum()),
        'pace_down': int((dc['pace_adj'] > 0).sum()),
        'type_cells': int(len(tc)),
        'type_moved': int((tc['rung_move'] != 0).sum()) if not tc.empty else 0,
        'stale': stale,
    }
    return dc, tc, summary


def _new_tab_change(day_cmp, type_cmp, summary, compare_label="", day_df=None):
    if not summary:
        st.markdown("""
<div class="renote warn"><b>비교할 이전 기록이 없습니다.</b>
리포트를 올리면 DB에 저장된 <b>가장 최근 스냅샷</b>을 이전 기록으로 자동으로 잡아
그 사이 재고 변화와 칸 변화를 여기 보여줍니다. 기존 앱의 "자동 DB 병합/비교"와 같습니다.<br><br>
지금 비어 있는 이유는 보통 셋 중 하나입니다.
<b>①</b> 아직 저장된 스냅샷이 없다 (첫 사용) —
<b>②</b> 사이드바에서 데이터를 직접 불러와 이전 기록이 안 붙었다 (
<code>🔄 최신 스냅샷을 이전 기록으로</code> 를 누르면 붙습니다) —
<b>③</b> 이전 스냅샷과 현재 데이터의 날짜가 안 겹친다.<br>
이전 기록이 없어도 앵커 · 연휴 · 재고 · Floor 는 정상 작동합니다. 페이스 단계만 0입니다.</div>
""", unsafe_allow_html=True)
        return

    if compare_label:
        st.markdown(f"<div class='renote'><b>비교 기준</b> — {compare_label}</div>",
                    unsafe_allow_html=True)

    if summary.get('stale'):
        st.markdown(
            "<div class='renote stop'><b>⚠️ 이전 기록이 현재 데이터와 동일합니다.</b> "
            "판매가 전부 0이라 비교가 의미 없습니다. 페이스 단계는 0으로 두었습니다. "
            "다른 날 저장된 스냅샷을 이전 기록으로 잡으십시오.</div>",
            unsafe_allow_html=True)

    s = summary
    c = st.columns(6)
    c[0].metric("그 사이 판매", f"{s['sold_total']:,.0f}실")
    c[1].metric("움직인 날", f"{s['sold_days']}일 / {s['days']}일")
    c[2].metric("칸이 바뀐 날", f"{s['moved_days']}일",
                f"↑{s['moved_up']} / ↓{s['moved_down']}")
    c[3].metric("페이스 발동", f"↑{s['pace_up']} / ↓{s['pace_down']}")
    c[4].metric("칸이 바뀐 셀", f"{s['type_moved']:,}")
    c[5].metric("비교 셀", f"{s['type_cells']:,}")

    if s['moved_days'] == 0:
        st.success("이전 기록 대비 칸이 바뀐 날이 없습니다. 요금을 손댈 필요가 없습니다.")
    else:
        st.markdown("##### 🔔 요금을 바꿔야 하는 날")
        st.caption("이전 기록만 보고 정했을 칸과 지금 확정 칸이 다른 날입니다. "
                   "'재고' 열이 움직였으면 재고가 빠져서, '페이스' 열이 움직였으면 "
                   "판매 속도 때문입니다.")
        mv = day_cmp[day_cmp['rung_move'] != 0].copy()
        head = ("<tr><th>일자</th><th>요일</th><th>D-</th><th>연휴</th>"
                "<th>이전 잔여</th><th>현재 잔여</th><th>판매</th>"
                "<th>페이스</th><th>재고</th><th>floor</th>"
                "<th>이전 칸</th><th>현재 칸</th><th>이동</th>"
                "<th>HDT 회원가</th></tr>")
        body = []
        for r in mv.itertuples():
            bg, fg = new_color(r.rung)
            pbg, pfg = new_color(r.p_rung)
            arrow = ("▲%d" % r.rung_move) if r.rung_move > 0 else ("▼%d" % -r.rung_move)
            acol = "#C62828" if r.rung_move > 0 else "#1565C0"
            pace = "—" if r.pace_adj == 0 else (
                "▲%d" % -r.pace_adj if r.pace_adj < 0 else "▼%d" % r.pace_adj)
            inv = "—" if r.inv_adj == 0 else "▲%d" % -r.inv_adj
            body.append(
                f"<tr class='{'hol' if r.hol else ''}'>"
                f"<td class='dt'>{r.date.strftime('%m/%d')}</td><td>{r.dow}</td>"
                f"<td class='mut'>D-{r.dta}</td>"
                f"<td class='l' style='font-size:11px'>{r.hol or '—'}</td>"
                f"<td class='mut'>{_won(r.p_avail)}</td><td class='mut'>{_won(r.tot_avail)}</td>"
                f"<td><b>{_won(r.sold)}</b></td>"
                f"<td>{pace}</td><td>{inv}</td><td>{r.floor or '—'}</td>"
                f"<td class='rg' style='background:{pbg};color:{pfg}'>{r.p_lab}</td>"
                f"<td class='rg' style='background:{bg};color:{fg}'>{r.lab}</td>"
                f"<td style='color:{acol};font-weight:700'>{arrow}</td>"
                f"<td><b>{_won(r.hdt_member)}</b></td></tr>")
        st.markdown(NEW_CSS + "<div class='rewrap'><div class='rescroll'>"
                    "<table class='retbl'><thead>" + head + "</thead><tbody>"
                    + "".join(body) + "</tbody></table></div></div>",
                    unsafe_allow_html=True)

    # ── 가로 매트릭스: 행 = 객실 · 열 = 날짜 ──────────────────────
    if type_cmp is not None and not type_cmp.empty and day_df is not None \
            and not day_df.empty:
        st.divider()
        st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
        mvonly = st.checkbox("칸이 바뀐 셀만 색칠", value=True, key="new_chg_mxonly")
        dts = _date_window(day_df, "new_chg_mx")
        if dts:
            dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
            tix = type_cmp.drop_duplicates(subset=['date', 'rt'], keep='first')
            tix = tix.set_index(['date', 'rt'])
            st.markdown(_mx_title("이전 대비 변화 — 행 = 객실 · 열 = 날짜", True),
                        unsafe_allow_html=True)
            head = _mx_head(dts, dmap, "객실")
            rows = []
            cells = []
            for d in dts:
                sub = day_cmp[day_cmp['date'] == d]
                if sub.empty:
                    cells.append("<td class='mut'>—</td>")
                    continue
                r = sub.iloc[0]
                mvv = int(r['rung_move'])
                bg, fg = new_color(int(r['rung']))
                arw = "—" if mvv == 0 else (f"▲{mvv}" if mvv > 0 else f"▼{-mvv}")
                cells.append(f"<td class='c3' style='background:{bg};color:{fg};"
                             f"font-weight:700'>{r['p_lab']}→{r['lab']}"
                             f"<em>{arw} · {_won(r['sold'])}실</em></td>")
            rows.append("<tr class='gend'><td class='rh'>날짜 칸 (기준)"
                        "<em style='display:block;font-style:normal;font-size:9px;"
                        "font-weight:400;color:#7d858c'>이전→현재 · 판매</em></td>"
                        + "".join(cells) + "</tr>")
            for rt in NEW_ROW_ORDER:
                cls = "gend" if rt in NEW_GROUP_END else ""
                cells = []
                for d in dts:
                    key = (d, rt)
                    if key not in tix.index:
                        cells.append("<td class='mut'>—</td>")
                        continue
                    row = tix.loc[key]
                    mvv = int(row['rung_move'])
                    sold = row['sold']
                    if mvv == 0 and mvonly:
                        cells.append(f"<td class='mut c3'>{row['lab']}"
                                     f"<em>{_won(sold)}실</em></td>")
                        continue
                    bg, fg = new_color(int(row['rung']))
                    arw = "—" if mvv == 0 else (f"▲{mvv}" if mvv > 0 else f"▼{-mvv}")
                    pm = int(row['price_move'] or 0)
                    cells.append(f"<td class='c3' style='background:{bg};color:{fg};"
                                 f"font-weight:700'>{row['p_lab']}→{row['lab']}"
                                 f"<em>{arw} · {_won(sold)}실</em>"
                                 f"<i style='color:{fg};opacity:.8'>{pm:+,}원</i></td>")
                rows.append(
                    f"<tr class='{cls}'><td class='rh'>{rt}"
                    f"<em style='display:block;font-style:normal;font-size:9px;"
                    f"font-weight:400;color:#7d858c'>{NEW_ROOM_NAMES.get(rt,'')}</em></td>"
                    + "".join(cells) + "</tr>")
            st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                        + "".join(rows) + "</tbody></table></div>",
                        unsafe_allow_html=True)
            st.caption("셀 = 이전 칸 → 현재 칸 / 이동·판매실수 / 회원가 차액. "
                       "회색은 칸이 그대로인 셀입니다.")

    st.divider()
    st.markdown("##### 날짜별 재고 변화 (전체)")
    only_moved = st.checkbox("재고가 움직인 날만", value=True, key="new_chg_only")
    dv = day_cmp[day_cmp['sold'].fillna(0) != 0] if only_moved else day_cmp
    if dv.empty:
        st.info("표시할 날짜가 없습니다.")
    else:
        t = pd.DataFrame({
            "일자": dv['date'].map(lambda x: x.strftime('%Y-%m-%d')),
            "요일": dv['dow'], "D-": dv['dta'].map(lambda x: f"D-{x}"),
            "연휴": dv['hol'].replace("", "—"),
            "이전 잔여": dv['p_avail'], "현재 잔여": dv['tot_avail'],
            "판매(실)": dv['sold'],
            "이전 총점유(%)": _numcol(dv['p_occ']).round(1),
            "현재 총점유(%)": _numcol(dv['occ']).round(1),
            "점유 변화(%p)": _numcol(dv['occ_move']).round(1),
            "소진 배수": _numcol(dv['pace_ratio']).round(2),
            "페이스": dv['pace_adj'], "재고": dv['inv_adj'],
            "이전 칸": dv['p_lab'], "현재 칸": dv['lab'], "이동": dv['rung_move'],
        })
        st.dataframe(t, use_container_width=True, hide_index=True, height=420)
        st.caption("소진 배수 = 소진예상일 ÷ 남은 일수. 1보다 작으면 남은 시간보다 빨리 "
                   "팔린다는 뜻이고, 0.50 이하부터 페이스가 칸을 올립니다. "
                   "페이스·재고 열의 음수는 비싼 칸 방향입니다.")

    if type_cmp is not None and not type_cmp.empty:
        st.divider()
        st.markdown("##### 객실타입별 변화")
        mode = st.radio("표시", ["칸이 바뀐 셀만", "재고가 움직인 셀만", "전체"],
                        horizontal=True, key="new_chg_tmode")
        if mode == "칸이 바뀐 셀만":
            tv = type_cmp[type_cmp['rung_move'] != 0]
        elif mode == "재고가 움직인 셀만":
            tv = type_cmp[type_cmp['sold'].fillna(0) != 0]
        else:
            tv = type_cmp
        if tv.empty:
            st.info("해당 조건의 셀이 없습니다.")
        else:
            t = pd.DataFrame({
                "일자": tv['date'].map(lambda x: x.strftime('%Y-%m-%d')),
                "요일": tv['dow'], "D-": tv['dta'].map(lambda x: f"D-{x}"),
                "객실": tv['rt'].astype(str),
                "전체": tv['cap'], "이전 잔여": tv['p_avail'], "현재 잔여": tv['avail'],
                "판매(실)": tv['sold'],
                "잔여율(%)": _numcol(tv['remt'], 100).round(1),
                "이전 칸": tv['p_lab'], "현재 칸": tv['lab'], "이동": tv['rung_move'],
                "이전 회원가": tv['p_member'], "현재 회원가": tv['member'],
                "요금 차이": tv['price_move'],
                "상태": tv['state'],
            })
            st.dataframe(t, use_container_width=True, hide_index=True, height=440)


# =============================================================================
# 11-B. 가로 매트릭스 (기존 앱과 같은 문법: 행 = 객실 · 열 = 날짜)
# -----------------------------------------------------------------------------
#  기존 render_master_table 의 구조를 그대로 따릅니다.
#    · 2단 헤더 — 위 MM-DD, 아래 요일 (일=빨강 / 토=파랑)
#    · 첫 열 고정(sticky) + 오른쪽 굵은 경계선
#    · HDF · PPV 행 아래 굵은 구분선 (메인 호텔동 / 특수객실 블록 구분)
#    · 셀은 3줄 (칸 / 요금 / 잔여)
#    · 좌우 스크롤
# =============================================================================
NEW_MX_CSS = """
<style>
.mxwrap{overflow-x:auto;white-space:nowrap;border:1px solid #ddd;background:#fff}
.mx{border-collapse:collapse;font-size:11px;min-width:1000px;
    font-variant-numeric:tabular-nums}
.mx th,.mx td{border:1px solid #ddd;padding:4px 5px;text-align:center;white-space:nowrap}
.mx thead th{background:#f9f9f9;font-weight:700;font-size:11px}
.mx thead th.hd{background:#FBEEE2}
.mx th.rh,.mx td.rh{position:sticky;left:0;z-index:3;background:#fff;text-align:left;
    border-right:4px solid #000;min-width:132px;font-weight:600}
.mx thead th.rh{background:#f9f9f9;z-index:4}
.mx tr.gend td,.mx tr.gend th{border-bottom:3.4px solid #000}
.mx td.c3{line-height:1.18}
.mx td.c3 em{display:block;font-style:normal;font-size:9.5px;opacity:.85;font-weight:400}
.mx td.c3 i{display:block;font-style:normal;font-size:9px;color:#7d858c;font-weight:400}
.mx td.off{background:#F2F3F4;color:#9AA1A8;font-weight:400}
.mx td.mut{color:#8A929A;font-weight:400}
.mx tr.alt td.rh{background:#FAFBFC}
.mx tr:hover td:not(.rh){filter:brightness(.97)}
.mxtitle{margin:22px 0 8px;font-weight:700;font-size:15px;padding:9px 12px;
    background:#f0f2f6;border-left:9px solid #16202B}
.mxtitle.acc{background:#E9F1F8;border-left-color:#1F5C8B}
</style>
"""

# 기존 앱과 같은 행 순서 · 같은 위치에 굵은 구분선
NEW_ROW_ORDER = list(NEW_ROOMS)
NEW_GROUP_END = {"HDF", "PPV"}


def _mx_head(dates, dmap=None, first_col="객실"):
    """2단 날짜 헤더 (위 MM-DD / 아래 요일). 연휴 열은 배경을 살짝 물들입니다."""
    h1 = [f"<th class='rh' rowspan='2'>{first_col}</th>"]
    h2 = []
    for d in dates:
        hol = ""
        if dmap is not None and d in dmap.index:
            hol = str(dmap.loc[d, 'hol'] or "")
        cls = "hd" if hol else ""
        h1.append(f"<th class='{cls}' title='{hol}'>{d.strftime('%m-%d')}</th>")
        wd = WD_KR[d.weekday()]
        col = "#D32F2F" if wd == '일' else ("#1565C0" if wd == '토' else "#333")
        h2.append(f"<th class='{cls}' style='color:{col}'>{wd}</th>")
    return ("<thead><tr>" + "".join(h1) + "</tr><tr>" + "".join(h2)
            + "</tr></thead>")


def _mx_title(text, accent=False):
    return f"<div class='mxtitle{' acc' if accent else ''}'>{text}</div>"


def _date_window(day_df, key):
    """월 단위로 표시 범위를 줄입니다 (열이 100개를 넘으면 읽기 어려우니)."""
    if day_df is None or day_df.empty:
        return []
    all_d = sorted(day_df['date'].unique())
    months = sorted({(d.year, d.month) for d in all_d})
    labels = [f"{y}-{m:02d}" for y, m in months]
    c1, c2 = st.columns([3, 1])
    with c1:
        pick = st.multiselect("표시 월", labels, default=labels, key=f"{key}_mon")
    with c2:
        past = st.checkbox("과거 날짜", value=False, key=f"{key}_past")
    keep = {tuple(int(x) for x in p.split('-')) for p in pick}
    out = [d for d in all_d if (d.year, d.month) in keep]
    if not past:
        sub = day_df.set_index('date')
        out = [d for d in out if int(sub.loc[d, 'dta']) >= 0] if len(sub) else out
    return out


# =============================================================================
# 11-C. 요금표 (앵커 → 칸 → 타입별 요금) — 데이터 없이도 항상 볼 수 있습니다
# =============================================================================
def _new_tab_ratecard():
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
    st.markdown(f"""
<div class="renote"><b>이 탭은 재고와 무관한 '고정 자료'입니다.</b>
사다리 16칸, 타입별 배수, 앵커 캘린더 84셀, 연휴·Floor 규칙 — 계산의 재료가 전부 여기 있습니다.
날짜 계산이 어떻게 나왔는지 확인할 때 이 표와 대조하십시오. 판 <b>{NEW_EDITION}</b>.</div>
""", unsafe_allow_html=True)

    view = st.radio("표시 요금", ["로드(BAR) 정가", "회원 노출가 (x0.90)",
                                "해외 랙 (x1.30)", "Flexible 하한 (x0.72)",
                                "NRF 하한 (x0.66)"],
                    horizontal=True, key="new_rc_view")
    k = {"로드(BAR) 정가": 1.0, "회원 노출가 (x0.90)": NEW_MEMBER_K,
         "해외 랙 (x1.30)": NEW_RACK_MULT, "Flexible 하한 (x0.72)": NEW_FLOOR_FLEX,
         "NRF 하한 (x0.66)": NEW_FLOOR_NRF}[view]

    # ── ① 타입별 x 16칸 요금표 ─────────────────────────────────────
    st.markdown(_mx_title("① 객실타입별 16칸 요금표 — 행 = 객실 · 열 = 칸", True),
                unsafe_allow_html=True)
    h1 = ["<th class='rh' rowspan='2'>객실</th>"]
    h2 = []
    for i in range(1, NEW_N + 1):
        bg, fg = new_color(i)
        h1.append(f"<th style='background:{bg};color:{fg}'>{new_lab(i)}</th>")
        h2.append(f"<th style='font-weight:400;color:#7d858c'>{i}</th>")
    head = "<thead><tr>" + "".join(h1) + "</tr><tr>" + "".join(h2) + "</tr></thead>"
    body = []
    for rt in NEW_ROW_ORDER:
        cls = "gend" if rt in NEW_GROUP_END else ""
        cells = []
        for i in range(1, NEW_N + 1):
            v = new_k_price(rt, i, k) if k != 1.0 else new_load_price(rt, i)
            cells.append(f"<td>{_won(v)}</td>")
        body.append(
            f"<tr class='{cls}'><td class='rh'>{rt}"
            f"<em style='display:block;font-style:normal;font-size:9px;font-weight:400;"
            f"color:#7d858c'>{NEW_ROOM_NAMES.get(rt,'')} · x{NEW_MULT[rt]:.3f}</em></td>"
            + "".join(cells) + "</tr>")
    st.markdown(NEW_MX_CSS + "<div class='mxwrap'><table class='mx'>" + head
                + "<tbody>" + "".join(body) + "</tbody></table></div>",
                unsafe_allow_html=True)
    st.caption(f"칸 간격 8%. 왼쪽이 비쌉니다. 아래 숫자는 칸 인덱스(1~16)입니다. "
               f"{view} 기준. 로드 정가는 발행된 타입별 요금표 그대로이고, "
               f"파생 요금은 반올림 전 원가(칸 x 배수)에서 한 번만 천원 단위로 반올림합니다.")

    # ── ② 앵커 캘린더 ─────────────────────────────────────────────
    st.markdown(_mx_title("② 앵커 캘린더 84셀 — 행 = 월 · 열 = 요일 (시작 칸)", True),
                unsafe_allow_html=True)
    h = "<thead><tr><th class='rh'>월</th>" + "".join(
        f"<th style=\"color:{'#D32F2F' if w==6 else ('#1565C0' if w==5 else '#333')}\">"
        f"{WD_KR[w]}</th>" for w in range(7)) + "</tr></thead>"
    rows = []
    for m in range(1, 13):
        cells = []
        for w in range(7):
            idx = NEW_ANCHOR[m][w]
            bg, fg = new_color(idx)
            price = new_k_price("HDT", idx, k) if k != 1.0 else new_load_price("HDT", idx)
            cells.append(f"<td class='c3' style='background:{bg};color:{fg}'>"
                         f"{new_lab(idx)}<em>{_won(price)}</em></td>")
        rows.append(f"<tr><td class='rh'>{m}월</td>" + "".join(cells) + "</tr>")
    st.markdown("<div class='mxwrap'><table class='mx'>" + h + "<tbody>"
                + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption(f"셀 안의 금액은 HDT 기준 {view} 입니다. 다른 객실은 ① 표의 배수를 곱하십시오. "
               f"이 표는 연도와 무관합니다 — 월 x 요일만 봅니다.")

    # ── ③ 연휴 · Floor 규칙 ───────────────────────────────────────
    st.markdown(_mx_title("③ 앵커 위에 올라가는 규칙"), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**연휴 · 페이스 · 재고**")
        st.dataframe(pd.DataFrame([
            {"단계": "2 연휴", "조건": "공휴일 · 연휴", "조정": f"{NEW_HOLIDAY_STEP}칸 상향",
             "배수": f"x{1.08**NEW_HOLIDAY_STEP:.3f}"},
            {"단계": "3 페이스", "조건": "소진 배수 ≤ 0.25", "조정": "2칸 상향", "배수": "x1.166"},
            {"단계": "3 페이스", "조건": "소진 배수 ≤ 0.50", "조정": "1칸 상향", "배수": "x1.080"},
            {"단계": "3 페이스", "조건": "소진 배수 2.0 ~ 4.0", "조정": "1칸 하향", "배수": "x0.926"},
            {"단계": "3 페이스", "조건": "소진 배수 > 4.0", "조정": "2칸 하향", "배수": "x0.857"},
            {"단계": "4 재고", "조건": "총잔여율 ≤ 20%", "조정": "1칸 상향", "배수": "x1.080"},
            {"단계": "4 재고", "조건": "총잔여율 ≤ 12%", "조정": "2칸 상향", "배수": "x1.166"},
            {"단계": "4 재고", "조건": "총잔여율 ≤ 5%", "조정": "3칸 상향", "배수": "x1.260"},
        ]), use_container_width=True, hide_index=True)
        st.caption("페이스 상향은 D-44 이내, 하향은 D-21 이내에서만. "
                   "총잔여율 25% 미만이면 하향 보류. 재고 단계는 리드타임 무관.")
    with c2:
        st.markdown("**Floor — 이 칸보다 싸게 못 내려갑니다**")
        st.dataframe(pd.DataFrame([
            {"종류": "Peak Event (Opening)", "대상": "추석 · 설날 핵심 3일",
             "최소 칸": "B3", "HDT": _won(new_load_price("HDT", NEW_RI["3"]))},
            {"종류": "Peak Event (Opening)", "대상": "10/1~10/5 · 한글날 연휴",
             "최소 칸": "B3", "HDT": _won(new_load_price("HDT", NEW_RI["3"]))},
            {"종류": "Peak Event (Opening)", "대상": "크리스마스 이브 (12/24)",
             "최소 칸": "B3", "HDT": _won(new_load_price("HDT", NEW_RI["3"]))},
            {"종류": "Peak Event (Opening)", "대상": "크리스마스 · 연휴 · 연말",
             "최소 칸": "B2", "HDT": _won(new_load_price("HDT", NEW_RI["2"]))},
            {"종류": "Scarcity (Absolute)", "대상": "총잔여율 ≤ 20%",
             "최소 칸": "B4", "HDT": _won(new_load_price("HDT", NEW_RI["4"]))},
            {"종류": "Scarcity (Absolute)", "대상": "총잔여율 ≤ 12%",
             "최소 칸": "B3", "HDT": _won(new_load_price("HDT", NEW_RI["3"]))},
            {"종류": "Scarcity (Absolute)", "대상": "총잔여율 ≤ 5%",
             "최소 칸": "B1", "HDT": _won(new_load_price("HDT", NEW_RI["1"]))},
        ]), use_container_width=True, hide_index=True)
        st.caption("Opening 은 D-46 이상 하향 금지 · D-45 1회 재심사(3조건 + RM 승인, "
                   "최대 1칸 완화). Absolute 는 자동 해제도 승인 완화도 없습니다.")

    st.markdown("**객실타입 조정 (7단계)**")
    st.dataframe(pd.DataFrame([
        {"조건": "타입 잔여율 ≤ 15%", "조정": "2칸 상향"},
        {"조건": "타입 잔여율 ≤ 30%", "조정": "1칸 상향"},
        {"조건": "타입 잔여 ≥ 85% + 총잔여 ≥ 60% + D-44 이내", "조정": "2칸 하향 (GDB 제외)"},
        {"조건": "타입 잔여 ≥ 70% + 총잔여 ≥ 40% + D-44 이내", "조정": "1칸 하향 (GDB 제외)"},
        {"조건": "그날 총잔여율 ≤ 20%", "조정": "남은 타입 1칸 추가 상향 (희소재)"},
        {"조건": "타입 잔여 0 이하", "조정": "판매 마감 — 요금은 참고값"},
    ]), use_container_width=True, hide_index=True)
    st.caption(f"하향은 B10(칸 {NEW_TYPE_RUNG_MAX})에서 멈춥니다 — B11~B13 은 자동 진입 금지 "
               f"구간(승인 항목)입니다. 칸 B1 이상(칸 인덱스 {NEW_APPROVAL_RUNG} 이하)은 "
               f"헤드룸으로 RM 승인 대상입니다.")


# =============================================================================
# 14. 탭 3 — 일자별 칸 (가로: 행 = 단계 · 열 = 날짜)
# =============================================================================
_STEP_ROWS = [
    ("1 앵커",         'anchor_lab',  'mut'),
    ("2 연휴 반영",     '_afterhol',   'mut'),
    ("3 페이스",        '_pace',       ''),
    ("4 재고",          '_inv',        ''),
    ("소계 (floor 전)", 'pre_lab',     'mut'),
    ("5 이벤트 floor",  'ev_floor',    ''),
    ("6 희소 floor",    'sc_floor',    ''),
]


def _new_tab_days(day_df):
    if day_df is None or day_df.empty:
        st.info("리포트를 업로드하세요.")
        return
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)

    dates = _date_window(day_df, "new_days")
    if not dates:
        st.warning("표시할 날짜가 없습니다. 위에서 월을 선택하세요.")
        return
    dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')

    st.markdown(_mx_title("일자별 확정 칸 — 행 = 단계 · 열 = 날짜", True),
                unsafe_allow_html=True)
    head = _mx_head(dates, dmap, "단계")

    def _cell_val(r, field):
        if field == '_afterhol':
            return new_lab(int(r['after_hol']))
        if field == '_pace':
            v = int(r['pace_adj'])
            return "—" if v == 0 else (f"▲{-v}" if v < 0 else f"▼{v}")
        if field == '_inv':
            v = int(r['inv_adj'])
            return "—" if v == 0 else f"▲{-v}"
        return str(r[field] or "—")

    rows = []
    # 연휴 이름
    cells = []
    for d in dates:
        hol = str(dmap.loc[d, 'hol'] or "")
        cells.append(f"<td class='mut' style='font-size:9px;"
                     f"{'color:#B5602C;font-weight:700' if hol else ''}'>"
                     f"{hol[:6] if hol else '—'}</td>")
    rows.append("<tr><td class='rh'>연휴</td>" + "".join(cells) + "</tr>")
    # 리드타임
    cells = [f"<td class='mut'>D-{int(dmap.loc[d,'dta'])}</td>" for d in dates]
    rows.append("<tr class='gend'><td class='rh'>리드타임</td>" + "".join(cells) + "</tr>")

    for label, field, cls in _STEP_ROWS:
        cells = []
        for d in dates:
            r = dmap.loc[d]
            cells.append(f"<td class='{cls}'>{_cell_val(r, field)}</td>")
        end = " gend" if field == 'sc_floor' else ""
        rows.append(f"<tr class='{end.strip()}'><td class='rh'>{label}</td>"
                    + "".join(cells) + "</tr>")

    # 확정 칸 (색칠)
    cells = []
    for d in dates:
        r = dmap.loc[d]
        bg, fg = new_color(int(r['rung']))
        mark = " ✋" if bool(r['is_override']) else ""
        cells.append(f"<td style='background:{bg};color:{fg};font-weight:700'>"
                     f"{r['lab']}{mark}</td>")
    rows.append("<tr><td class='rh'>확정 칸</td>" + "".join(cells) + "</tr>")

    for label, field in [("HDT 로드가", 'hdt_load'), ("HDT 회원가", 'hdt_member')]:
        cells = [f"<td{' style=font-weight:700' if field=='hdt_member' else ''}>"
                 f"{_won(dmap.loc[d, field])}</td>" for d in dates]
        end = " gend" if field == 'hdt_member' else ""
        rows.append(f"<tr class='{end.strip()}'><td class='rh'>{label}</td>"
                    + "".join(cells) + "</tr>")

    cells = []
    for d in dates:
        v = dmap.loc[d, 'occ']
        cells.append(f"<td class='mut'>{'-' if v != v else '%.0f%%' % v}</td>")
    rows.append("<tr><td class='rh'>총점유</td>" + "".join(cells) + "</tr>")
    cells = [f"<td class='mut'>{_pct(_num(dmap.loc[d,'remh']), 0)}</td>" for d in dates]
    rows.append("<tr><td class='rh'>총잔여율</td>" + "".join(cells) + "</tr>")
    cells = [f"<td class='mut'>{_won(dmap.loc[d,'tot_avail'])}</td>" for d in dates]
    rows.append("<tr><td class='rh'>잔여(실)</td>" + "".join(cells) + "</tr>")

    st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption("▲ = 비싼 칸으로, ▼ = 싼 칸으로. ✋ 는 수동 예외로 고정된 날. "
               "확정 칸이 '소계'보다 비싸면 floor 가 구속한 것입니다. "
               "주황색 열 머리는 연휴입니다.")

    with st.expander("📋 세로 상세 — floor 근거 · 재심사 판정까지", expanded=False):
        df = day_df[day_df['date'].isin(dates)]
        t = pd.DataFrame({
            "일자": df['date'].map(lambda x: x.strftime('%Y-%m-%d')),
            "요일": df['dow'], "D-": df['dta'].map(lambda x: f"D-{x}"),
            "구간": df['zone'], "연휴": df['hol'].replace("", "—"),
            "앵커": df['anchor_lab'], "페이스": df['pace_adj'], "재고": df['inv_adj'],
            "소계": df['pre_lab'],
            "이벤트 floor": df['ev_floor'].replace("", "—"),
            "희소 floor": df['sc_floor'].replace("", "—"),
            "확정 floor": df['floor'].replace("", "—"),
            "floor 종류": df['floor_kind'].replace("", "—"),
            "floor 근거": df['floor_by'].replace("", "—"),
            "확정 칸": df['lab'],
            "HDT 로드": df['hdt_load'], "HDT 회원가": df['hdt_member'],
            "총점유(%)": _numcol(df['occ']).round(1),
            "총잔여율(%)": _numcol(df['remh'], 100).round(1),
            "재심사일": df['review_date'].replace("", "—"),
            "재심사 판정": df['review'].replace("", "—"),
        })
        st.dataframe(t, use_container_width=True, hide_index=True, height=460)


# =============================================================================
# 15. 탭 4 — 타입별 칸 · 요금 (가로: 행 = 객실 · 열 = 날짜)
# =============================================================================
def _new_tab_types(day_df, type_df):
    if type_df is None or type_df.empty:
        st.info("리포트를 업로드하세요.")
        return
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        view = st.radio("셀에 표시할 요금", ["회원 노출가", "로드(BAR)가", "해외 랙",
                                       "Flexible 하한", "NRF 하한", "칸만"],
                        horizontal=True, key="new_mtx_view")
    with c2:
        rooms = st.multiselect("객실타입", NEW_ROW_ORDER, default=NEW_ROW_ORDER,
                               key="new_mtx_rooms")
    dates = _date_window(day_df, "new_mtx")
    if not dates or not rooms:
        st.warning("표시할 날짜 또는 객실이 없습니다.")
        return

    field = {"회원 노출가": 'member', "로드(BAR)가": 'load', "해외 랙": 'rack',
             "Flexible 하한": 'floor_flex', "NRF 하한": 'floor_nrf',
             "칸만": None}[view]
    order = [r for r in NEW_ROW_ORDER if r in rooms]
    dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
    tix = type_df.drop_duplicates(subset=['date', 'rt'], keep='first')
    tix = tix.set_index(['date', 'rt'])

    st.markdown(_mx_title(f"객실타입별 확정 칸 · {view} — 행 = 객실 · 열 = 날짜", True),
                unsafe_allow_html=True)
    head = _mx_head(dates, dmap, "객실")
    rows = []

    # 맨 위: 날짜 칸 (그날의 기준)
    cells = []
    for d in dates:
        r = dmap.loc[d]
        bg, fg = new_color(int(r['rung']))
        cells.append(f"<td class='c3' style='background:{bg};color:{fg};font-weight:700'>"
                     f"{r['lab']}<em>{_won(r['hdt_member'])}</em></td>")
    rows.append("<tr class='gend'><td class='rh'>날짜 칸 (기준)"
                "<em style='display:block;font-style:normal;font-size:9px;"
                "font-weight:400;color:#7d858c'>HDT 회원가</em></td>"
                + "".join(cells) + "</tr>")

    for rt in order:
        cls = "gend" if rt in NEW_GROUP_END else ""
        cells = []
        for d in dates:
            key = (d, rt)
            if key not in tix.index:
                cells.append("<td class='mut'>—</td>")
                continue
            row = tix.loc[key]
            if bool(row['stop']):
                cells.append(f"<td class='off c3'>{row['state']}"
                             f"<em>{row['lab']}</em><i>{_won(row['avail'])}실</i></td>")
                continue
            bg, fg = new_color(int(row['rung']))
            mark = "✋" if bool(row['is_override']) else (
                "★" if row['approval'] else "")
            if field is None:
                main, sub = f"{row['lab']}{mark}", _won(row['member'])
            else:
                main, sub = _won(row[field]), f"{row['lab']}{mark}"
            cells.append(f"<td class='c3' style='background:{bg};color:{fg};"
                         f"font-weight:700'>{main}<em>{sub}</em>"
                         f"<i style='color:{fg};opacity:.75'>{_won(row['avail'])}실</i></td>")
        rows.append(
            f"<tr class='{cls}'><td class='rh'>{rt}"
            f"<em style='display:block;font-style:normal;font-size:9px;font-weight:400;"
            f"color:#7d858c'>{NEW_ROOM_NAMES.get(rt,'')} · x{NEW_MULT[rt]:.3f}</em></td>"
            + "".join(cells) + "</tr>")

    st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption("셀 = 요금 / 칸 / 잔여 3줄 (칸만 보기에서는 칸 / 회원가 / 잔여). "
               "★ = 칸 B1 이상 헤드룸(RM 승인 구간), ✋ = 수동 예외. "
               "회색 셀은 잔여 0 이하 — 요금 조정이 아니라 판매를 닫아야 합니다. "
               "굵은 가로선은 메인 호텔동(~HDF) / 특수객실(~PPV) 블록 구분입니다.")

    st.divider()
    st.markdown("##### 날짜 하나 골라 보는 판매 시트")
    tgt = st.selectbox("날짜", dates,
                       format_func=lambda x: f"{x.strftime('%Y-%m-%d')} ({WD_KR[x.weekday()]})",
                       key="new_sheet_date")
    one = type_df[(type_df['date'] == tgt) & (type_df['rt'].astype(str).isin(rooms))].copy()
    if not one.empty:
        info = dmap.loc[tgt]
        st.markdown(
            f"**{tgt.strftime('%Y-%m-%d')} ({WD_KR[tgt.weekday()]})** · D-{int(info['dta'])} · "
            f"날짜 칸 **{info['lab']}** · 총점유 "
            f"{'-' if info['occ'] != info['occ'] else '%.1f%%' % info['occ']} · "
            f"총잔여 {_pct(_num(info['remh']))}"
            + (f" · 연휴 {info['hol']}" if info['hol'] else "")
            + (f" · floor {info['floor']} ({info['floor_by']})" if info['floor_by'] else ""))
        one['_o'] = one['rt'].astype(str).map({r: i for i, r in enumerate(NEW_ROW_ORDER)})
        one = one.sort_values('_o')
        sheet = pd.DataFrame({
            "객실": one['rt'].astype(str),
            "객실명": one['rt'].astype(str).map(NEW_ROOM_NAMES),
            "전체": one['cap'], "잔여": one['avail'],
            "잔여율(%)": _numcol(one['remt'], 100).round(1),
            "칸": one['lab'], "타입조정": one['tadj'],
            "로드(BAR)": one['load'], "회원 노출가": one['member'],
            "해외 랙": one['rack'], "Flex 하한": one['floor_flex'],
            "NRF 하한": one['floor_nrf'],
            "상태": one['state'], "승인": one['approval'].replace("", "—"),
            "근거": one['why'].replace("", "—"),
        })
        st.dataframe(sheet, use_container_width=True, hide_index=True)


# =============================================================================
# 16. 탭 5 — Floor & 재심사
# =============================================================================
def _new_tab_floor(day_df):
    if day_df is None or day_df.empty:
        st.info("리포트를 업로드하세요.")
        return

    st.markdown("""
<div class="renote warn"><b>floor는 자동 계산 과정에서는 올리기만 합니다.</b>
단, <b>Peak Event Opening Floor</b>에 한해 D-45 재심사에서 3조건을 모두 충족하면 RM 승인으로
1칸 완화할 수 있습니다. <b>Scarcity Absolute Floor는 완화하지 않습니다.</b><br>
재심사 3조건 — ① floor가 실제로 구속 중 (= 계산 칸 번호가 floor보다 큼, 예: B5 vs B2)
② 페이스가 기준 미달 ③ 총잔여율 25% 초과. 세 개가 모두 참일 때만 후보입니다.</div>
""", unsafe_allow_html=True)

    ch = day_df[day_df['floor_by'] != ""].copy()
    c = st.columns(4)
    c[0].metric("floor 적용일", f"{len(ch)}일")
    c[1].metric("이벤트 (Opening)", f"{int(ch['floor_by'].str.startswith('이벤트').sum())}일")
    c[2].metric("희소재고 (Absolute)", f"{int(ch['floor_by'].str.startswith('희소').sum())}일")
    cand = day_df[day_df['review'].str.startswith("★", na=False)]
    c[3].metric("완화 후보", f"{len(cand)}일")

    if ch.empty:
        st.success("현재 재고에서 floor가 구속하는 날은 없습니다. 계산 칸이 모두 floor보다 비쌉니다.")
    else:
        t = ch[['date', 'dow', 'dta', 'pre_lab', 'ev_floor', 'sc_floor', 'floor',
                'lab', 'hdt_member', 'floor_kind', 'floor_by']].copy()
        t['date'] = t['date'].map(lambda x: x.strftime('%Y-%m-%d'))
        t['dta'] = t['dta'].map(lambda x: f"D-{x}")
        t.columns = ['일자', '요일', '리드타임', '계산 칸', '이벤트 floor', '희소 floor',
                     '확정 floor', '최종 칸', 'HDT 회원가', 'floor 종류', '근거']
        st.dataframe(t, use_container_width=True, hide_index=True, height=340)

    st.divider()
    st.markdown("##### Opening Floor 재심사 현황 (재심사일 = 입실일 − 45일)")
    rv = day_df[day_df['ev_floor'] != ""].copy()
    if rv.empty:
        st.info("이 기간에는 Peak Event Floor가 걸린 날이 없습니다.")
    else:
        t = rv[['review_date', 'date', 'dow', 'dta', 'ev_floor', 'ev_relax',
                'pre_lab', 'lab', 'review']].copy()
        t['date'] = t['date'].map(lambda x: x.strftime('%Y-%m-%d'))
        t['dta'] = t['dta'].map(lambda x: f"D-{x}")
        t.columns = ['재심사일', '입실일', '요일', '리드타임', 'Opening Floor',
                     '완화 시', '계산 칸', '최종 칸', '판정']
        st.dataframe(t, use_container_width=True, hide_index=True, height=340)

    st.divider()
    st.markdown("##### 강한 신호 — 앵커 재검토 후보")
    st.caption("D-45 이상이라 페이스가 아직 닿지 않는데 이미 재고가 빠진 날입니다. "
               "개별 날짜를 하루씩 따라가지 말고, 재검증 창의 마지막 날에 전체를 한 번 취합해 "
               "해당 월 앵커를 1칸 올릴지 결정하는 방식이 실무적으로 가장 깔끔합니다.")
    sig = day_df[(day_df['dta'] > NEW_PACE_LEAD_UP_MAX) &
                 (day_df['remh'].notna()) & (day_df['remh'] <= 0.35)].copy()
    if sig.empty:
        st.info("현재 강한 신호로 분류된 날은 없습니다.")
    else:
        sig = sig.sort_values('date')
        t = sig[['date', 'dow', 'dta', 'occ', 'remh', 'anchor_lab', 'lab']].copy()
        t['review'] = sig['date'].map(
            lambda x: (x - timedelta(days=NEW_REVIEW_LEAD)).strftime('%Y-%m-%d'))
        t['date'] = t['date'].map(lambda x: x.strftime('%Y-%m-%d'))
        t['dta'] = t['dta'].map(lambda x: f"D-{x}")
        t['occ'] = _numcol(t['occ']).round(1)
        t['remh'] = _numcol(t['remh'], 100).round(1)
        t = t[['review', 'date', 'dow', 'dta', 'occ', 'remh', 'anchor_lab', 'lab']]
        t.columns = ['재검증일', '입실일', '요일', '리드타임', '총점유(%)', '총잔여(%)',
                     '앵커', '현재 칸']
        st.dataframe(t, use_container_width=True, hide_index=True, height=300)
        win = sig['date'].map(lambda x: x - timedelta(days=NEW_REVIEW_LEAD))
        st.markdown(
            f"<div class='renote'><b>재검증 창 = {win.min().strftime('%Y-%m-%d')} ~ "
            f"{win.max().strftime('%Y-%m-%d')}</b> ({len(sig)}일). "
            f"창의 마지막 날 <b>{win.max().strftime('%m/%d')}</b>에 전체를 취합해 판단하십시오. "
            f"Opening Floor 재심사와는 별개 일정입니다.</div>", unsafe_allow_html=True)


# =============================================================================
# 17. 탭 6 — 할인 레이어 · 채널 판매가
# =============================================================================
def _new_tab_promo(type_df, promotions, channel_list):
    st.markdown(f"""
<div class="renote stop"><b>아래 하한은 전부 '순실수령' 기준입니다 — 노출가가 아닙니다.</b>
상시 Flexible <b>{NEW_FLOOR_FLEX:.2f}</b> · 상시 NRF <b>{NEW_FLOOR_NRF:.2f}</b> ·
경영 승인선 <b>{NEW_FLOOR_APPROVAL:.2f}</b> · 노출가 절대선 BAR x <b>{NEW_FLOOR_DISPLAY:.2f}</b>.
캠페인 레이어가 {NEW_FLOOR_NRF:.2f} 미만으로 내려가려면 환불불가 · 기간한정 · 물량상한
3조건을 모두 충족하고 RM 승인을 받아야 합니다.</div>
""", unsafe_allow_html=True)

    st.markdown("##### 부킹 로드 정책 3단")
    st.dataframe(pd.DataFrame(NEW_BOOKING_POLICY, columns=["단계", "범위", "규칙"]),
                 use_container_width=True, hide_index=True)

    st.markdown("##### 상시 · 캠페인 레이어")
    lay = []
    for nm, k, mem, pt, flo in NEW_LAYERS:
        # 회원 중첩이 있는 레이어는 랙 기준 명목 할인율 = 1 − k ÷ (배수 x 0.90)
        nom = 1 - k / (NEW_RACK_MULT * NEW_MEMBER_K) if mem else 1 - k / NEW_RACK_MULT
        net18 = k * (1 - NEW_OTA_COMM)
        lay.append({
            "레이어": nm, "목표계수 k": round(k, 4),
            "회원 중첩": "O" if mem else "X", "취소정책": pt,
            "랙 기준 표기 할인율": f"{nom*100:.1f}%",
            "순실수령 (직판)": round(k, 4),
            "순실수령 (OTA 18%)": round(net18, 4),
            "하한": flo,
            "판정": "OK" if k >= flo else ("승인 필요" if k >= NEW_FLOOR_NRF - 0.08 else "불가"),
        })
    st.dataframe(pd.DataFrame(lay), use_container_width=True, hide_index=True)
    st.caption(
        f"해외 프로모션은 회원 할인과 중첩되지 않으므로 랙을 가산합니다 — "
        f"랙 = BAR x {NEW_RACK_MULT:.2f}, 랙 x (1 − {NEW_RACK_DISPLAY_DISCOUNT*100:.0f}%) "
        f"= BAR x {NEW_RACK_MULT*(1-NEW_RACK_DISPLAY_DISCOUNT):.2f}. "
        f"부킹닷컴처럼 수수료 18%를 무는 판매가 채널은 순실수령 "
        f"{NEW_RACK_MULT*(1-NEW_RACK_DISPLAY_DISCOUNT)*(1-NEW_OTA_COMM):.4f}로 하한을 "
        f"{(NEW_FLOOR_NRF - NEW_RACK_MULT*(1-NEW_RACK_DISPLAY_DISCOUNT)*(1-NEW_OTA_COMM))*100:+.2f}%p 밑돕니다 "
        f"(환불불가 확정 수취가치로 상계 — 손익분기 징수율 56.1%).")

    st.markdown("##### 해외 채널별 랙 운용")
    ch = []
    for nm, prog, form, comm in NEW_RACK_CHANNELS:
        net = NEW_RACK_MULT * (1 - NEW_RACK_DISPLAY_DISCOUNT) * (1 - comm)
        ch.append({"채널": nm, "프로그램": prog, "요금 형태": form,
                   "수수료": f"{comm*100:.0f}%",
                   "랙 배수": NEW_RACK_MULT, "순실수령": round(net, 4)})
    st.dataframe(pd.DataFrame(ch), use_container_width=True, hide_index=True)

    if type_df is None or type_df.empty:
        return

    st.divider()
    st.markdown("##### 레이어별 실제 판매가 — 날짜 x 타입")
    c1, c2 = st.columns([3, 2])
    with c1:
        names = [l[0] for l in NEW_LAYERS]
        pick = st.selectbox("레이어", names, key="new_layer_pick")
    with c2:
        rt = st.selectbox("객실타입", NEW_ROOMS, key="new_layer_room")
    lay_d = {l[0]: l for l in NEW_LAYERS}[pick]
    k = lay_d[1]
    df = type_df[(type_df['rt'] == rt) & (type_df['dta'] >= 0)].copy()
    if df.empty:
        st.info("표시할 날짜가 없습니다.")
        return
    out = pd.DataFrame({
        "일자": df['date'].map(lambda x: x.strftime('%Y-%m-%d')),
        "요일": df['dow'], "칸": df['lab'],
        "로드(BAR)": df['load'],
        "회원 노출가": df['member'],
        f"{pick} 판매가": df['rung'].map(lambda r: new_k_price(rt, r, k)),
        "순실수령(직판)": df['rung'].map(lambda r: new_k_price(rt, r, k)),
        "순실수령(OTA18%)": df['rung'].map(
            lambda r: int(round(new_raw(rt, r) * k * (1 - NEW_OTA_COMM) / 1000) * 1000)),
        "Flex 하한": df['floor_flex'], "NRF 하한": df['floor_nrf'],
        "판매": df['state'],
    })
    st.dataframe(out, use_container_width=True, hide_index=True, height=420)

    if channel_list:
        st.divider()
        st.markdown("##### 이지에디터 채널 상품 — 신 요금 기준 재계산")
        st.caption("사이드바 이지에디터에 등록된 상품(할인% · 추가금)을 그대로 신 사다리에 얹었습니다. "
                   "설정 자체는 현행 엔진과 공유합니다.")
        promos = promotions if isinstance(promotions, dict) else {}
        for cname in (channel_list or []):
            # ※ settings/channels 구조가 예상과 다를 수 있어 단계마다 형태를 확인합니다.
            conf = promos.get(cname)
            items = conf.get("items") if isinstance(conf, dict) else None
            if not isinstance(items, (list, tuple)) or not items:
                continue
            with st.expander(f"📦 {cname} ({len(items)}개 상품)", expanded=False):
                recs, skipped = [], []
                for it in items:
                    if not isinstance(it, dict):
                        skipped.append("형식 오류 (행이 비어 있음)")
                        continue
                    irt = it.get('객실타입')
                    irt = str(irt).strip().upper() if irt is not None else ""
                    pname = _txt(it.get('상품명'), "(이름 없음)")
                    if irt not in NEW_TABLE:
                        skipped.append(f"{pname}: 객실타입 '{it.get('객실타입')}' 을 못 알아봄")
                        continue
                    # ※ 이지에디터의 빈 칸은 NaN 으로 저장됩니다. 파이썬에서 NaN 은
                    #   참(truthy)이라 `float(x) or 0` 이 NaN 을 그대로 통과시켜
                    #   int(round(NaN)) 에서 ValueError 가 납니다. _numf 로 받습니다.
                    disc = _numf(it.get('할인(%)'), 0.0) / 100.0
                    add = _numf(it.get('추가금'), 0.0)
                    if not (0.0 <= disc <= 1.0):
                        skipped.append(f"{pname}: 할인율 {it.get('할인(%)')!r} 이 0~100 범위 밖")
                        continue
                    sub = type_df[(type_df['rt'] == irt) & (type_df['dta'] >= 0)]
                    for r in sub.itertuples():
                        base = new_raw(irt, r.rung)
                        if not base:
                            continue
                        price = int(round((base * (1 - disc) + add) / 1000) * 1000)
                        net_k = price / base
                        recs.append({
                            "일자": r.date.strftime('%m/%d'), "요일": r.dow,
                            "객실": irt, "상품": pname, "칸": r.lab,
                            "로드(BAR)": r.load, "판매가": price,
                            "계수": round(net_k, 4),
                            "하한": "OK" if net_k >= NEW_FLOOR_NRF else "⚠️ 하한 미달",
                            "판매": r.state,
                        })
                if skipped:
                    st.warning("건너뛴 상품 %d건 — 이지에디터에서 값을 확인하세요.\n\n- %s"
                               % (len(skipped), "\n- ".join(skipped[:12])))
                if recs:
                    st.dataframe(pd.DataFrame(recs), use_container_width=True,
                                 hide_index=True, height=360)
                elif not skipped:
                    st.info("표시할 날짜가 없습니다 (전부 과거 날짜).")


# =============================================================================
# 18. 탭 7 — 신 로직 예외 설정
# =============================================================================
def _new_tab_override(day_df, type_df, db, today):
    st.markdown("""
<div class="renote warn"><b>여기서 만든 예외는 신 로직 전용 저장소에만 들어갑니다.</b>
메인 페이지(기존 로직)의 '예외 설정'(applied_rates)과 완전히 분리돼 있어, 어느 쪽을 고쳐도
다른 쪽 요금은 바뀌지 않습니다. 칸 라벨은 <code>B0pp B0p B0 B1 ... B13</code> 형식입니다.</div>
""", unsafe_allow_html=True)

    if day_df is None or day_df.empty:
        st.info("리포트를 업로드하세요.")
        return

    _dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
    raw = new_load_overrides(db)
    dates = sorted(day_df[day_df['dta'] >= 0]['date'].unique())
    if not dates:
        dates = sorted(day_df['date'].unique())

    tgt = st.selectbox("예외를 걸 날짜", dates,
                       format_func=lambda x: (
                           f"{x.strftime('%Y-%m-%d')} ({WD_KR[x.weekday()]}) "
                           f"— 현재 {_dmap.loc[x, 'lab']}"),
                       key="new_ov_date")
    ds = tgt.strftime('%Y-%m-%d')
    cur = (raw.get(ds) or {}).get('rooms', {})
    memo_cur = (raw.get(ds) or {}).get('memo', "")

    info = _dmap.loc[tgt]
    st.markdown(
        f"**계산 결과** — 앵커 {info['anchor_lab']} → 소계 {info['pre_lab']} → 확정 **{info['lab']}**"
        + (f" · floor {info['floor']} ({info['floor_by']})" if info['floor_by'] else "")
        + f" · 총잔여 {_pct(info['remh'])}")

    opts = ["(예외 없음)"] + [new_lab(i) for i in range(1, NEW_N + 1)]
    st.markdown("###### 날짜 전체 고정")
    day_pick = st.selectbox("_DAY (모든 타입의 기준 칸을 이 값으로)", opts,
                            index=(opts.index(cur['_DAY']) if cur.get('_DAY') in opts else 0),
                            key="new_ov_day")

    st.markdown("###### 객실타입별 고정")
    tsub = None
    if type_df is not None and not type_df.empty:
        tsub = type_df[type_df['date'] == tgt].set_index('rt')
        tsub = tsub[~tsub.index.duplicated(keep='first')]
    picks = {}
    cols = st.columns(5)
    for i, rt in enumerate(NEW_ROOMS):
        with cols[i % 5]:
            calc = tsub.loc[rt, 'lab'] if (tsub is not None and rt in tsub.index) else "-"
            picks[rt] = st.selectbox(
                f"{rt} · 계산 {calc}", opts,
                index=(opts.index(cur[rt]) if cur.get(rt) in opts else 0),
                key=f"new_ov_{rt}")

    memo = st.text_input("메모 (왜 예외를 걸었는지)", value=memo_cur, key="new_ov_memo")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("💾 이 날짜 예외 저장", type="primary", use_container_width=True, key="new_ov_save"):
            rooms = {}
            if day_pick != "(예외 없음)":
                rooms['_DAY'] = day_pick
            for rt, v in picks.items():
                if v != "(예외 없음)":
                    rooms[rt] = v
            if not rooms:
                ok, msg = new_delete_override(db, ds)
                st.info(f"선택된 칸이 없어 {ds} 예외를 해제했습니다. ({msg})")
            else:
                ok, msg = new_save_override(db, ds, rooms, memo)
                (st.success if ok else st.error)(f"{ds} — {msg}")
            st.rerun()
    with b2:
        if st.button("🗑️ 이 날짜 예외 해제", use_container_width=True, key="new_ov_del"):
            ok, msg = new_delete_override(db, ds)
            (st.success if ok else st.error)(f"{ds} — {msg}")
            st.rerun()

    st.divider()
    st.markdown("##### 현재 활성 예외 (신 로직)")
    if not raw:
        st.info("설정된 예외가 없습니다.")
    else:
        recs = []
        for k in sorted(raw):
            info2 = raw[k] or {}
            rooms = info2.get('rooms') or {}
            recs.append({
                "날짜": k,
                "고정 칸": ", ".join(f"{a}={b}" for a, b in sorted(rooms.items())),
                "메모": (info2.get('memo') or "")[:60],
                "저장 시각": info2.get('saved_at', ""),
            })
        st.dataframe(pd.DataFrame(recs), use_container_width=True, hide_index=True, height=300)


# =============================================================================
# 19. 탭 8 — 다운로드
# =============================================================================
def _new_excel(day_df, type_df, day_cmp=None, type_cmp=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        # 읽어주세요
        notes = [
            ["엠버 퓨어힐 · 신 요금로직 적용표 (16칸 사다리)", ""],
            ["판", NEW_EDITION],
            ["생성 시각", datetime.now().strftime('%Y-%m-%d %H:%M')],
            ["", ""],
            ["칸은 6단계로 정합니다", ""],
            ["1 앵커", "월 x 요일 84셀"],
            ["2 연휴", "공휴일·연휴 2칸 상향 (x1.166)"],
            ["3 페이스", "이전 기록 대비 판매 속도로 +-2칸 (상향 D-44 이내 / 하향 D-21 이내)"],
            ["4 재고", "호텔 총잔여율 20/12/5% 이하 → 1/2/3칸 상향 (리드타임 무관)"],
            ["5 Peak Event Floor", "Opening — D-46 이상 하향 금지, D-45 1회 재심사 (3조건 + RM 승인, 최대 1칸)"],
            ["6 Scarcity Floor", "Absolute — 총잔여 20/12/5% 이하 최소 B4/B3/B1, 해제 없음"],
            ["7 객실타입", "타입 잔여율로 +-2칸, 잔여 0 이하는 판매 마감"],
            ["", ""],
            ["하한 단위", "0.72(Flexible) / 0.66(NRF) / 0.70(승인선)은 모두 순실수령입니다"],
            ["노출가 절대선", "BAR x 0.70"],
            ["회원 노출가", "로드(BAR) x 0.90"],
            ["해외 프로모션 랙", "BAR x 1.30 · 표기 40% 할인 → BAR x 0.78 (회원 중첩 없음)"],
        ]
        pd.DataFrame(notes, columns=["항목", "내용"]).to_excel(
            w, index=False, sheet_name="읽어주세요")

        if day_df is not None and not day_df.empty:
            d = day_df.copy()
            d['date'] = d['date'].map(lambda x: x.strftime('%Y-%m-%d'))
            d = d[['date', 'dow', 'dta', 'zone', 'hol', 'anchor_lab', 'pace_adj', 'inv_adj',
                   'pre_lab', 'ev_floor', 'sc_floor', 'floor', 'floor_kind', 'floor_by',
                   'lab', 'hdt_load', 'hdt_member', 'occ', 'remh', 'review_date', 'review']]
            d.columns = ['일자', '요일', 'D-', '구간', '연휴', '앵커', '페이스', '재고',
                         '소계', '이벤트 floor', '희소 floor', '확정 floor', 'floor 종류',
                         'floor 근거', '확정 칸', 'HDT 로드', 'HDT 회원가', '총점유(%)',
                         '총잔여율', '재심사일', '재심사 판정']
            d.to_excel(w, index=False, sheet_name="일자별 칸")

        if type_df is not None and not type_df.empty:
            t = type_df.copy()
            t['date'] = t['date'].map(lambda x: x.strftime('%Y-%m-%d'))
            t['객실명'] = t['rt'].map(NEW_ROOM_NAMES)
            t = t[['date', 'dow', 'dta', 'rt', '객실명', 'cap', 'avail', 'remt',
                   'day_lab', 'tadj', 'lab', 'load', 'member', 'rack', 'floor_flex',
                   'floor_nrf', 'state', 'approval', 'why']]
            t.columns = ['일자', '요일', 'D-', '객실', '객실명', '전체', '잔여', '잔여율',
                         '날짜 칸', '타입 조정', '확정 칸', '로드(BAR)', '회원 노출가',
                         '해외 랙', 'Flex 하한', 'NRF 하한', '상태', '승인', '근거']
            t.to_excel(w, index=False, sheet_name="타입별 칸")

            # ※ 매트릭스는 화면과 같은 방향으로 — 행 = 객실, 열 = 날짜
            for nm, fld in [("칸 매트릭스", 'lab'), ("회원 노출가 매트릭스", 'member'),
                            ("로드 요금 매트릭스", 'load'), ("해외 랙 매트릭스", 'rack')]:
                p = type_df.pivot_table(index='rt', columns='date', values=fld,
                                        aggfunc='first')
                p = p.reindex(index=[r for r in NEW_ROOMS if r in p.index])
                p.columns = [f"{x.strftime('%m-%d')}({WD_KR[x.weekday()]})"
                             for x in p.columns]
                p.index.name = "객실"
                p.to_excel(w, sheet_name=nm)

        if day_df is not None and not day_df.empty:
            fl = day_df[day_df['floor_by'] != ""].copy()
            if not fl.empty:
                fl['date'] = fl['date'].map(lambda x: x.strftime('%Y-%m-%d'))
                fl = fl[['date', 'dow', 'dta', 'pre_lab', 'ev_floor', 'sc_floor',
                         'floor', 'lab', 'hdt_member', 'floor_kind', 'floor_by',
                         'review_date', 'review']]
                fl.columns = ['일자', '요일', 'D-', '계산 칸', '이벤트 floor', '희소 floor',
                              '확정 floor', '최종 칸', 'HDT 회원가', 'floor 종류',
                              '근거', '재심사일', '재심사 판정']
                fl.to_excel(w, index=False, sheet_name="Floor 적용 내역")

        # 사다리 · 앵커 · 레이어
        # 사다리 요금표 — 행 = 객실, 열 = 칸 (화면 요금표 탭과 동일)
        for nm, kk in [("요금표 로드(BAR)", 1.0), ("요금표 회원가", NEW_MEMBER_K),
                       ("요금표 해외랙", NEW_RACK_MULT),
                       ("요금표 Flex하한", NEW_FLOOR_FLEX),
                       ("요금표 NRF하한", NEW_FLOOR_NRF)]:
            lad = pd.DataFrame(
                {new_lab(i): [(new_load_price(rt, i) if kk == 1.0
                               else new_k_price(rt, i, kk)) for rt in NEW_ROOMS]
                 for i in range(1, NEW_N + 1)},
                index=NEW_ROOMS)
            lad.insert(0, "객실명", [NEW_ROOM_NAMES.get(r, "") for r in NEW_ROOMS])
            lad.insert(1, "배수", [NEW_MULT[r] for r in NEW_ROOMS])
            lad.index.name = "객실"
            lad.to_excel(w, sheet_name=nm)

        # 앵커 캘린더 — 행 = 월, 열 = 요일
        anc = pd.DataFrame(
            {WD_KR[i]: [new_lab(NEW_ANCHOR[m][i]) for m in range(1, 13)]
             for i in range(7)},
            index=[f"{m}월" for m in range(1, 13)])
        anc.index.name = "월"
        anc.to_excel(w, sheet_name="앵커 캘린더")
        ancp = pd.DataFrame(
            {WD_KR[i]: [new_load_price("HDT", NEW_ANCHOR[m][i]) for m in range(1, 13)]
             for i in range(7)},
            index=[f"{m}월" for m in range(1, 13)])
        ancp.index.name = "월 (HDT 로드가)"
        ancp.to_excel(w, sheet_name="앵커 캘린더 요금")

        lay = pd.DataFrame([{
            "레이어": nm, "목표계수 k": k, "회원 중첩": "O" if mem else "X",
            "취소정책": pt, "하한(순실수령)": flo,
            "랙 기준 표기 할인율":
                (1 - k / (NEW_RACK_MULT * NEW_MEMBER_K)) if mem else (1 - k / NEW_RACK_MULT),
            "순실수령 (OTA 18%)": k * (1 - NEW_OTA_COMM),
        } for nm, k, mem, pt, flo in NEW_LAYERS])
        lay.to_excel(w, index=False, sheet_name="할인 레이어")

        if day_cmp is not None and not day_cmp.empty:
            dv = day_cmp.copy()
            dv['date'] = dv['date'].map(lambda x: x.strftime('%Y-%m-%d'))
            dv = dv[['date', 'dow', 'dta', 'hol', 'p_avail', 'tot_avail', 'sold',
                     'p_occ', 'occ', 'occ_move', 'pace_ratio', 'pace_adj', 'inv_adj',
                     'p_lab', 'lab', 'rung_move', 'hdt_member']]
            dv.columns = ['일자', '요일', 'D-', '연휴', '이전 잔여', '현재 잔여', '판매(실)',
                          '이전 총점유(%)', '현재 총점유(%)', '점유 변화(%p)', '소진 배수',
                          '페이스', '재고', '이전 칸', '현재 칸', '칸 이동', 'HDT 회원가']
            dv.to_excel(w, index=False, sheet_name="이전 대비 변화")

        if type_cmp is not None and not type_cmp.empty:
            tv = type_cmp.copy()
            tv['date'] = tv['date'].map(lambda x: x.strftime('%Y-%m-%d'))
            tv['rt'] = tv['rt'].astype(str)
            tv = tv[['date', 'dow', 'dta', 'rt', 'cap', 'p_avail', 'avail', 'sold',
                     'remt', 'p_lab', 'lab', 'rung_move', 'p_member', 'member',
                     'price_move', 'state']]
            tv.columns = ['일자', '요일', 'D-', '객실', '전체', '이전 잔여', '현재 잔여',
                          '판매(실)', '잔여율', '이전 칸', '현재 칸', '칸 이동',
                          '이전 회원가', '현재 회원가', '요금 차이', '상태']
            tv.to_excel(w, index=False, sheet_name="타입별 변화")

    return buf.getvalue()


def _new_tab_download(day_df, type_df, day_cmp=None, type_cmp=None):
    st.markdown("""
<div class="renote"><b>엑셀 한 파일에 전부 들어갑니다.</b>
읽어주세요 / 일자별 칸 / 타입별 칸 / <b>매트릭스 4종</b>(칸 · 회원가 · 로드가 · 해외랙 —
모두 행 = 객실 · 열 = 날짜) / Floor 내역 / <b>요금표 5종</b>(로드 · 회원가 · 해외랙 ·
Flex하한 · NRF하한) / 앵커 캘린더 2종 / 할인 레이어
(+ 이전 기록이 있으면 이전 대비 변화 · 타입별 변화).</div>
""", unsafe_allow_html=True)
    if day_df is None or day_df.empty:
        st.info("리포트를 업로드하세요.")
        return
    data = _new_excel(day_df, type_df, day_cmp, type_cmp)
    st.download_button(
        "📥 신 요금로직 적용표 다운로드", data=data,
        file_name=f"AmberPureHill_NewRate_Apply_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True, key="new_dl")
    st.caption("※ 기존 로직과 대조하려면 왼쪽 페이지 목록에서 메인으로 돌아가 같은 날짜의 "
               "1번 시장 분석 표를 보십시오. 두 로직의 계산식을 한 파일에 섞지 않으려고 "
               "비교 탭은 넣지 않았습니다.")


# =============================================================================
# 20. 진입점
# =============================================================================
def _safe(fn, *a, **k):
    """탭 하나가 터져도 페이지 전체가 죽지 않게 하고, 실제 오류를 화면에 보여줍니다.

    ※ Streamlit Cloud 는 잡히지 않은 예외의 메시지를 가려버려서 원인을 알 수 없습니다.
      여기서 잡아 st.exception 으로 띄우면 트레이스백이 그대로 보입니다.
    """
    try:
        fn(*a, **k)
    except Exception as e:                     # noqa: BLE001 — 진단이 목적
        st.error(f"이 탭을 그리는 중 오류가 났습니다: {type(e).__name__}: {e}")
        st.caption("다른 탭은 정상입니다. 아래 트레이스백을 그대로 알려주시면 고칩니다.")
        st.exception(e)



def render_page(curr_df, prev_df=None, db=None, promotions=None, channel_list=None,
                today=None, compare_label=""):
    """pages/ 아래 페이지가 이 함수 하나만 부릅니다. app.py 와는 완전히 무관합니다."""
    if today is None:
        today = date.today()

    st.markdown(NEW_CSS, unsafe_allow_html=True)
    st.markdown(
        f"<div style='border-bottom:2px solid #16202B;padding-bottom:12px;margin-bottom:8px'>"
        f"<div style='font-size:11px;letter-spacing:.15em;text-transform:uppercase;"
        f"color:#1F5C8B;font-weight:700'>Amber Pure Hill · New Rate Logic</div>"
        f"<div style='font-size:26px;font-weight:700;letter-spacing:-.02em'>"
        f"신 요금로직 <span style='font-size:14px;font-weight:400;color:#78848F'>"
        f"[{NEW_EDITION}] · 16칸 사다리 + 앵커 84셀 + Opening/Absolute Floor "
        f"· 연도 무관</span></div></div>",
        unsafe_allow_html=True)

    if curr_df is None or curr_df.empty:
        st.warning("재고 데이터가 없습니다. 왼쪽 사이드바에서 리포트를 올리거나 "
                   "DB 최신 스냅샷을 불러오십시오. 메인 페이지에서 올린 데이터도 "
                   "그대로 넘어옵니다.")
        tabs = st.tabs(["📐 규칙 & 요약", "📋 요금표", "🏷️ 할인 레이어"])
        with tabs[0]:
            _safe(_new_tab_rules, None, None, today)
        with tabs[1]:
            _safe(_new_tab_ratecard)
        with tabs[2]:
            _safe(_new_tab_promo, None, promotions, channel_list)
        return

    ov = new_override_map(new_load_overrides(db))
    try:
        day_df = new_compute_days(curr_df, prev_df, today=today, overrides=ov)
        type_df = new_compute_types(curr_df, day_df, today=today, overrides=ov)
    except Exception as e:
        st.error(f"신 로직 계산 실패: {type(e).__name__}: {e}")
        st.exception(e)
        return

    if day_df.empty:
        st.warning("계산할 날짜가 없습니다.")
        return

    # ── 이전 기록 대비 자동 비교 ──────────────────────────────
    try:
        day_cmp, type_cmp, chg = new_compute_change(curr_df, prev_df, day_df,
                                                    type_df, today=today)
    except Exception as e:
        day_cmp, type_cmp, chg = pd.DataFrame(), pd.DataFrame(), {}
        st.warning(f"이전 기록 비교 실패 — 나머지는 정상 계산됩니다. ({e})")

    if chg and chg.get('stale'):
        st.markdown(
            "<div class='renote stop'><b>⚠️ 이전 기록이 현재 데이터와 완전히 같습니다.</b> "
            "모든 날짜의 판매가 0으로 잡혔습니다 — 같은 스냅샷을 '이전 기록'으로 "
            "붙였을 가능성이 큽니다. 이 상태에서는 판매 속도를 알 수 없으므로 "
            "<b>페이스 단계를 0으로 두고</b> 앵커 · 연휴 · 재고 · Floor 만으로 계산했습니다. "
            "제대로 비교하려면 <b>다른 날 저장된</b> 스냅샷을 이전 기록으로 잡거나, "
            "새 리포트를 올리십시오.</div>", unsafe_allow_html=True)
    elif chg:
        if chg['moved_days']:
            st.markdown(
                f"<div class='renote warn'><b>🔔 이전 기록 대비 칸이 바뀐 날 "
                f"{chg['moved_days']}일</b> (비싼 칸 {chg['moved_up']} · 싼 칸 "
                f"{chg['moved_down']}) — 그 사이 {chg['sold_total']:,.0f}실 팔렸습니다. "
                f"<b>2번 탭</b>에서 어느 날 요금을 바꿔야 하는지 확인하십시오."
                + (f"<br><span style='color:#78848F'>비교 기준: {compare_label}</span>"
                   if compare_label else "") + "</div>",
                unsafe_allow_html=True)
        else:
            st.success(f"이전 기록 대비 칸이 바뀐 날이 없습니다 "
                       f"(그 사이 {chg['sold_total']:,.0f}실 판매)."
                       + (f" · {compare_label}" if compare_label else ""))
    elif prev_df is None or (hasattr(prev_df, 'empty') and prev_df.empty):
        st.info("이전 기록이 없어 자동 비교와 페이스 단계가 비어 있습니다. "
                "사이드바의 `🔄 최신 스냅샷을 이전 기록으로` 를 누르거나 "
                "리포트를 올리면 붙습니다. (앵커·연휴·재고·Floor 는 정상)")

    n_ov = len(ov)
    if n_ov:
        st.info(f"✋ 예외 {n_ov}일이 적용된 상태입니다. (6번 탭에서 관리)")

    chg_label = "📈 이전 대비 변화"
    if chg and chg.get('moved_days'):
        chg_label = f"📈 이전 대비 변화 ({chg['moved_days']})"
    tabs = st.tabs([
        "📐 규칙 & 요약", chg_label, "📅 일자별 칸", "🛏️ 타입별 칸 · 요금",
        "📋 요금표", "🛡️ Floor & 재심사", "🏷️ 할인 레이어 · 채널가",
        "✋ 예외 설정", "📥 다운로드",
    ])
    with tabs[0]:
        _safe(_new_tab_rules, day_df, type_df, today)
    with tabs[1]:
        _safe(_new_tab_change, day_cmp, type_cmp, chg, compare_label, day_df)
    with tabs[2]:
        _safe(_new_tab_days, day_df)
    with tabs[3]:
        _safe(_new_tab_types, day_df, type_df)
    with tabs[4]:
        _safe(_new_tab_ratecard)
    with tabs[5]:
        _safe(_new_tab_floor, day_df)
    with tabs[6]:
        _safe(_new_tab_promo, type_df, promotions, channel_list)
    with tabs[7]:
        _safe(_new_tab_override, day_df, type_df, db, today)
    with tabs[8]:
        _safe(_new_tab_download, day_df, type_df, day_cmp, type_cmp)
