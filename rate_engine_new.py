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
# HDT(힐 엠버 트윈) 기준 16칸, 칸 간격 8%.
#
# ※ 3차 정렬 — 타입별 차액을 '정액 + 정률 하이브리드'로 (사다리 x0.953484)
#
#   [왜]  기존 앱 요금표는 배수(정률)가 아니라 **정액 차액**이었습니다.
#         HDT 기준 +30,000(HDP) / +65,000(FDB) / +102,000(FDE) / +170,000(HDF) —
#         10개 BAR 전부 같은 금액. 실현 ADR 회귀로 뽑은 배수 1.044(4.4%)는
#         올해 1~3월에 두 객실이 같은 요금이었던 기간이 섞여 희석된 값이었습니다.
#
#   [문제]  · 정액만 쓰면  성수기에 차액이 칸 간격(8%)보다 작아져 역전이 납니다.
#             (B0pp 728,000 에서 1칸 = 58,000원인데 차액은 30,000원)
#           · 정률만 쓰면  비수기에 차액이 1~2만원으로 쪼그라듭니다.
#             (B13 에서 8% = 17,000원)
#
#   [해법]  차액 = max(정액, 하급 요금 x 정률).
#           저가 구간은 정액이 받치고, 고가 구간은 정률이 받칩니다.
#           한 칸 아래 요금은 현재의 0.926배이므로, 차액이 하급가격의 7.4%를
#           넘으면 1칸 어긋나도 역전이 나지 않습니다 — 두 방식이 서로의
#           약점을 정확히 메웁니다.
#
#   [결과]  파인 더블 − 엠버 트윈 = 비수기 30,000원 ~ 성수기 59,000원.
#           포레스트 가든 − 파인 더블 = 60,000 ~ 120,000원 (프리미엄 포지션).
#           전체 사다리를 x0.953484 재역산해 믹스가중 BAR 418,886원을 유지합니다
#           (변경 전 418,899 · 필요 이론 BAR 418,849) — 100억 목표에 영향 없습니다.
#           그린밸리 · 펫 · 풀빌라는 요금 수준이 그대로 유지되도록 배수를 역보정.
#
#   [주의]  요금은 이제 '칸 x 배수'가 아니라 아래 NEW_TABLE 이 원장입니다.
#           NEW_MULT 는 B7 기준 참고 비율일 뿐이며, 파생 요금(회원가 · 랙 · 하한)은
#           모두 NEW_TABLE 값에서 계산합니다.

# 타입별 차액 규칙 — (객실, 기준 객실, 정액, 정률).  NEW_TABLE 을 만든 근거입니다.
#   ※ 루나 패밀리는 플로라가 아니라 '가든 더블 EB' 를 기준으로 잡습니다.
#     EB 와 플로라는 같은 가격대의 대체재(동일 티어)라, 플로라가 재고 때문에
#     내려가도 루나가 흔들리지 않게 하려는 것입니다.
NEW_DIFF_RULE = [
    ("HDP", "HDT", 30000, 0.085),
    ("FDB", "HDP", 60000, 0.160),
    ("FDE", "FDB", 40000, 0.100),
    ("FFD", "FDE", 15000, 0.040),
    ("HDF", "FDE", 75000, 0.150),
]
NEW_RUNG = {
    1: 690000, 2: 640000, 3: 592000, 4: 548000, 5: 507000, 6: 470000, 7: 435000, 8: 403000,
    9: 373000, 10: 345000, 11: 320000, 12: 297000, 13: 275000, 14: 254000, 15: 236000, 16: 217000,
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


# B7 기준 참고 비율. 하이브리드 차액이라 칸마다 실제 비율이 다릅니다.
#   요금의 원장은 NEW_TABLE 이고, 이 값은 화면 표시와
#   그린밸리 · 펫 · 풀빌라(칸 x 배수 그대로) 계산에만 씁니다.
NEW_MULT = {
    "FDB": 1.261,
    "FDE": 1.386,
    "HDP": 1.087,
    "HDT": 1.0,
    "HDF": 1.603,
    "GDB": 0.855,
    "GDF": 1.406,
    "FFD": 1.441,
    "FPT": 1.991,
    "PPV": 2.983,
}
# 표시 순서는 기존 앱 ALL_ROOMS 와 동일합니다 (메인 호텔동 → 특수객실).
NEW_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF", "GDB", "GDF", "FFD", "FPT", "PPV"]
NEW_ROOM_NAMES = {
    "HDT": "힐 엠버 트윈", "HDP": "힐 파인 더블", "HDF": "힐 루나 패밀리",
    "FDB": "포레스트 가든 더블", "FDE": "포레스트 가든 더블 EB",
    "FFD": "포레스트 플로라 더블", "FPT": "포레스트 펫 더블",
    "GDB": "그린밸리 디럭스 더블", "GDF": "그린밸리 디럭스 패밀리",
    "PPV": "프라이빗 풀 빌라",
}

# 타입별 16칸 요금표 = round(RUNG x MULT, 천원). 로드(BAR) 기준가입니다.
NEW_TABLE = {
    "FDB": {"0pp": 869000, "0p": 805000, "0": 745000, "1": 690000, "2": 638000, "3": 592000, "4": 548000, "5": 507000, "6": 470000, "7": 435000, "8": 410000, "9": 387000, "10": 365000, "11": 344000, "12": 326000, "13": 307000},
    "FDE": {"0pp": 956000, "0p": 886000, "0": 820000, "1": 759000, "2": 702000, "3": 651000, "4": 603000, "5": 558000, "6": 517000, "7": 478000, "8": 451000, "9": 427000, "10": 405000, "11": 384000, "12": 366000, "13": 347000},
    "HDP": {"0pp": 749000, "0p": 694000, "0": 642000, "1": 595000, "2": 550000, "3": 510000, "4": 472000, "5": 437000, "6": 405000, "7": 375000, "8": 350000, "9": 327000, "10": 305000, "11": 284000, "12": 266000, "13": 247000},
    "HDT": {"0pp": 690000, "0p": 640000, "0": 592000, "1": 548000, "2": 507000, "3": 470000, "4": 435000, "5": 403000, "6": 373000, "7": 345000, "8": 320000, "9": 297000, "10": 275000, "11": 254000, "12": 236000, "13": 217000},
    "HDF": {"0pp": 1099000, "0p": 1019000, "0": 943000, "1": 873000, "2": 807000, "3": 749000, "4": 693000, "5": 642000, "6": 595000, "7": 553000, "8": 526000, "9": 502000, "10": 480000, "11": 459000, "12": 441000, "13": 422000},
    "GDB": {"0pp": 591000, "0p": 548000, "0": 507000, "1": 469000, "2": 434000, "3": 402000, "4": 372000, "5": 345000, "6": 319000, "7": 295000, "8": 274000, "9": 254000, "10": 235000, "11": 217000, "12": 202000, "13": 186000},
    "GDF": {"0pp": 971000, "0p": 900000, "0": 833000, "1": 771000, "2": 713000, "3": 661000, "4": 612000, "5": 567000, "6": 525000, "7": 485000, "8": 450000, "9": 418000, "10": 387000, "11": 357000, "12": 332000, "13": 305000},
    "FFD": {"0pp": 994000, "0p": 921000, "0": 853000, "1": 789000, "2": 730000, "3": 677000, "4": 627000, "5": 580000, "6": 538000, "7": 497000, "8": 469000, "9": 444000, "10": 421000, "11": 399000, "12": 381000, "13": 362000},
    "FPT": {"0pp": 1374000, "0p": 1274000, "0": 1179000, "1": 1091000, "2": 1009000, "3": 936000, "4": 866000, "5": 802000, "6": 743000, "7": 687000, "8": 637000, "9": 591000, "10": 548000, "11": 506000, "12": 470000, "13": 432000},
    "PPV": {"0pp": 2058000, "0p": 1908000, "0": 1765000, "1": 1634000, "2": 1512000, "3": 1402000, "4": 1297000, "5": 1202000, "6": 1112000, "7": 1029000, "8": 954000, "9": 886000, "10": 820000, "11": 757000, "12": 704000, "13": 647000},
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
NEW_APPROVAL_RUNG = 4

# =============================================================================
# 3-B. 역전방지 계단 (rate integrity) — 가격 서열을 지킵니다
# -----------------------------------------------------------------------------
# 왜 필요한가
#   타입 조정이 등급별로 독립이라, 상급 객실이 하급보다 싸지는 일이 생깁니다.
#   그러면 하급을 사려던 고객이 상급으로 올라가고 → 하급 재고가 안 팔리고
#   상급을 제값보다 싸게 팝니다 (이중 손실 = 카니발라이제이션).
#   배수 재정렬 전에는 113일 중 40일에서 이런 역전이 났습니다.
#
# 언제 거는가 — OCC 가 아니라 "하급에 잠식당할 재고가 실제로 남아 있는가"
#   · 하급에 팔 재고 충분        → 최소 간격 전액
#   · 하급 매진 임박             → 최소 간격 x NEW_LADDER_SHRINK
#   · 하급 거의 소진             → 계단에서 제외 (잠식할 재고가 없으니 상급을
#                                안 끌어올립니다 = "엠버 트윈만 소진됐는데
#                                다른 타입까지 올라가는" 문제를 막습니다)
#
# 어떻게 올리는가
#   가격을 임의값으로 밀어올리지 않고 '칸'을 올립니다. 그래서 모든 요금은
#   항상 사다리 위에 있고, 화면·엑셀·채널 계산이 전부 일관됩니다.
# =============================================================================
# 메인 가격 계층 (낮은 등급 → 높은 등급).
#   튜플은 '동일 티어' — 같은 가격대의 대체재라 그 안에서는 서열을 강제하지 않고,
#   각자 재고에 따라 자유롭게 움직입니다. 위 등급은 티어에서 가장 비싼 값을
#   기준으로 계단을 겁니다 (티어가 내려가면 위가 흔들리지 않고,
#   티어가 올라가면 위도 따라 올라갑니다).
NEW_LADDER_CHAIN = ["HDT", "HDP", "FDB", ("FDE", "FFD"), "HDF"]
NEW_LADDER_GAP = {
    "HDP": 30000,   # 힐 엠버 트윈 → 힐 파인 더블          (차액 규칙과 동일)
    "FDB": 60000,   # 힐 파인 더블 → 포레스트 가든 더블
    "FDE": 40000,   # 포레스트 가든 더블 → EB
    "FFD": 40000,   # 포레스트 가든 더블 → 플로라 (같은 티어라 EB 와 같은 기준)
    "HDF": 30000,   # [EB · 플로라] 티어 → 힐 루나 패밀리
}
# 그린밸리는 펜션형으로 상품군이 달라 별도 계층을 씁니다.
NEW_LADDER_CHAIN_GV = ["GDB", "GDF"]
NEW_LADDER_GAP_GV = {"GDF": 90000}
# 하급이 이 상태면 계단에서 제외 (실수 또는 잔여율 중 하나만 걸려도)
NEW_LADDER_DROP_N = 0
NEW_LADDER_DROP_PCT = 0.08
# 하급이 이 상태면 최소 간격을 축소
NEW_LADDER_SHRINK_N = 3
NEW_LADDER_SHRINK_PCT = 0.20
NEW_LADDER_SHRINK = 0.35
NEW_LADDER_ON = True                          # 칸 4(B1) 이상 고가는 헤드룸 = RM 승인

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
    """파생 요금(회원가 · 랙 · 하한)의 기준값 = 발행된 로드(BAR) 요금.

    ※ 하이브리드 차액을 쓰면 요금이 '칸 x 배수'로 표현되지 않으므로,
      NEW_TABLE 값을 그대로 기준으로 씁니다. 발행 요금에 계수를 곱하는 것이
      운영상으로도 맞습니다 (노출가는 발행가를 할인한 값입니다).
    """
    v = new_load_price(rt, rung)
    if v:
        return float(v)
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
def _ladder_factor(avail_low, cap_low):
    """하급 객실 상태 → 최소 간격 배수. None 이면 계단에서 제외."""
    a = _num(avail_low)
    c = _num(cap_low)
    sh = (a / c) if (a is not None and c and c > 0) else None
    if a is None:
        return 1.0
    if a <= NEW_LADDER_DROP_N or (sh is not None and sh <= NEW_LADDER_DROP_PCT):
        return None
    if a <= NEW_LADDER_SHRINK_N or (sh is not None and sh <= NEW_LADDER_SHRINK_PCT):
        return NEW_LADDER_SHRINK
    return 1.0


def new_apply_ladder(rows):
    """한 날짜의 타입 결과에 가격 서열을 강제합니다 (칸을 올려서).

    rows: {rt: dict(rung, avail, cap, ...)} — 제자리에서 수정하고
          {rt: 올린 칸 수} 를 돌려줍니다.
    계층 원소가 튜플이면 '동일 티어' — 그 안에서는 서열을 강제하지 않고,
    위 등급은 티어에서 가장 비싼 값을 기준으로 삼습니다.
    """
    moved = {}
    if not NEW_LADDER_ON:
        return moved
    for chain, gaps in ((NEW_LADDER_CHAIN, NEW_LADDER_GAP),
                        (NEW_LADDER_CHAIN_GV, NEW_LADDER_GAP_GV)):
        last = None            # (기준 요금, 기준 잔여, 기준 전체) — 직전 티어
        for step in chain:
            mem = [step] if isinstance(step, str) else list(step)
            here = [(rt, rows[rt]) for rt in mem if rt in rows]
            if not here:
                continue
            if last is not None:
                ref_px, ref_av, ref_cap = last
                f = _ladder_factor(ref_av, ref_cap)
                if f is not None:
                    for rt, r in here:
                        need = ref_px + int(gaps.get(rt, 0) * f)
                        rung, up = int(r['rung']), 0
                        while rung > NEW_TYPE_RUNG_MIN \
                                and new_load_price(rt, rung) < need:
                            rung -= 1
                            up += 1
                        if up:
                            r['rung'] = rung
                            moved[rt] = up
            # 이 티어를 다음 단계의 기준으로 (판매 중인 객실만)
            live = []
            for rt, r in here:
                av = _num(r.get('avail'))
                if av is None or av > 0:
                    live.append((rt, r))
            if live:
                top = max(live, key=lambda x: new_load_price(x[0], x[1]['rung']))
                last = (new_load_price(top[0], top[1]['rung']),
                        sum(_num(r.get('avail')) or 0 for _, r in live),
                        sum(_num(r.get('cap')) or 0 for _, r in live))
    return moved


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
            rung=rung, pre_ladder_rung=rung, lab=new_lab(rung),
            state=state, why=why, is_override=is_ov,
            stop=bool(av is not None and av <= 0),
        ))
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # ── 역전방지 계단: 날짜별로 가격 서열을 강제합니다 ──────────────
    lad = {}
    if NEW_LADDER_ON:
        by = {}
        for i, r in enumerate(rows):
            by.setdefault(r['date'], {})[r['rt']] = r
        for d, grp in by.items():
            fixed = {rt for rt, r in grp.items() if r['is_override']}
            mv = new_apply_ladder({rt: r for rt, r in grp.items() if rt not in fixed})
            for rt, up in mv.items():
                lad[(d, rt)] = up

    out = []
    for r in rows:
        rt, rung = r['rt'], int(r['rung'])
        up = lad.get((r['date'], rt), 0)
        why = r['why']
        if up:
            why = (why + " · " if why else "") + "역전방지 계단 %d칸" % up
        out.append(dict(
            r, rung=rung, lab=new_lab(rung), why=why, ladder_up=up,
            approval=("헤드룸 (RM 승인)" if rung <= NEW_APPROVAL_RUNG else ""),
            load=new_load_price(rt, rung), member=new_member_price(rt, rung),
            rack=new_k_price(rt, rung, NEW_RACK_MULT),
            floor_flex=new_k_price(rt, rung, NEW_FLOOR_FLEX),
            floor_nrf=new_k_price(rt, rung, NEW_FLOOR_NRF),
            floor_display=new_k_price(rt, rung, NEW_FLOOR_DISPLAY),
        ))
    df = pd.DataFrame(out)
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


def new_auto_labels(day_raw, type_raw):
    """예외를 걸지 않았을 때 엔진이 내놓는 칸. {(YYYY-MM-DD, rt|'_DAY'): 'B7'}"""
    out = {}
    if day_raw is not None and not day_raw.empty:
        for r in day_raw.itertuples():
            out[(r.date.strftime('%Y-%m-%d'), '_DAY')] = r.lab
    if type_raw is not None and not type_raw.empty:
        for r in type_raw.itertuples():
            out[(r.date.strftime('%Y-%m-%d'), str(r.rt))] = r.lab
    return out


def new_review_overrides(raw_docs, auto_now):
    """예외를 걸어둔 날의 '자동 계산값'이 그 뒤에 바뀐 것을 찾아냅니다.

    기존 앱의 재검토 알림(rec_bar_at_apply 대비)과 같은 개념입니다.
    예외는 새 파일을 올려도 그대로 유지되므로, 자동 계산이 달라졌는데 예외가
    그대로 남아 있는 상태를 사람이 알아채야 합니다.
    """
    rows = []
    for ds, info in (raw_docs or {}).items():
        info = info or {}
        rooms = info.get('rooms') or {}
        saved = info.get('rec_at_apply') or {}
        for key, fixed in rooms.items():
            if new_idx(fixed) is None:
                continue
            was = saved.get(key)
            now = auto_now.get((ds, key))
            if not was or not now or was == now:
                continue
            rows.append({
                "날짜": ds,
                "대상": "날짜 전체" if key == '_DAY' else key,
                "고정한 칸": str(fixed),
                "걸었을 때 자동값": was,
                "지금 자동값": now,
                "차이": (new_idx(was) or 0) - (new_idx(now) or 0),
                "메모": (info.get('memo') or "")[:40],
            })
    return pd.DataFrame(rows)


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


def new_save_override(db, date_str, rooms, memo="", auto_now=None):
    clean = {k: v for k, v in (rooms or {}).items() if new_idx(v) is not None}
    # ※ 예외를 건 시점의 '자동 계산값'을 함께 남깁니다. 나중에 재고가 바뀌어
    #   자동 계산이 달라지면 재검토 알림을 띄우기 위한 기준입니다.
    rec = {}
    if auto_now:
        for k in clean:
            v = auto_now.get((date_str, k))
            if v:
                rec[k] = v
    payload = {
        'rooms': clean,
        'rec_at_apply': rec,
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
 <div><h5>8 · 역전방지 계단</h5><p>상급이 하급보다 싸지지 않게 <b>칸을 올려</b> 최소 간격을
   강제합니다. 단 <b>하급이 거의 소진되면 계단에서 제외</b> — 엠버 트윈만 팔렸는데
   다른 타입까지 올라가는 일을 막습니다. 차액은 <b>max(정액, 정률)</b> 하이브리드.</p></div>
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
    n_lad = 0
    if type_df is not None and not type_df.empty and 'ladder_up' in type_df.columns:
        n_lad = int((type_df['ladder_up'] > 0).sum())
    c[5].metric("역전방지 계단", f"{n_lad:,}셀", f"타입≠날짜 {diff_cells:,}셀")

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

    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
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
        st.markdown(
            "<div class='renote stop' style='font-size:14px'>"
            "<b style='font-size:16px'>🔔 지금 손대야 하는 날 "
            f"{s['moved_days']}일</b><br>"
            "이전 기록만 보고 정했을 칸과 지금 확정 칸이 다른 날입니다. "
            "오른쪽 <b>이전 칸 ▶ 현재 칸</b> 두 열이 실제로 바꿔야 하는 값이고, "
            "<b>페이스 / 재고</b> 열을 보면 왜 움직였는지 알 수 있습니다 "
            "(재고가 빠져서 vs 판매 속도 때문에).</div>",
            unsafe_allow_html=True)
        mv = day_cmp[day_cmp['rung_move'] != 0].copy()
        head = ("<tr><th>일자</th><th>요일</th><th>D-</th><th>연휴</th>"
                "<th>이전 잔여</th><th>현재 잔여</th><th>판매</th>"
                "<th>페이스</th><th>재고</th><th>floor</th>"
                "<th style='background:#FFF3E6'>이전 칸</th>"
                "<th style='background:#FFE4CC'>▶ 현재 칸</th>"
                "<th style='background:#FFE4CC'>이동</th>"
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
                f"<tr class='hitrow{' hol' if r.hol else ''}'>"
                f"<td class='dt'>{r.date.strftime('%m/%d')}</td><td>{r.dow}</td>"
                f"<td class='mut'>D-{r.dta}</td>"
                f"<td class='l' style='font-size:11px'>{r.hol or '—'}</td>"
                f"<td class='mut'>{_won(r.p_avail)}</td>"
                f"<td class='mut'>{_won(r.tot_avail)}</td>"
                f"<td><b>{_won(r.sold)}</b></td>"
                f"<td style='font-weight:700'>{pace}</td>"
                f"<td style='font-weight:700'>{inv}</td>"
                f"<td>{r.floor or '—'}</td>"
                f"<td class='mvbig' style='background:{pbg};color:{pfg};opacity:.5'>"
                f"{r.p_lab}</td>"
                f"<td class='mvbig' style='background:{bg};color:{fg};"
                f"outline:3px solid #16202B;outline-offset:-3px'>{r.lab}</td>"
                f"<td class='arw' style='color:{acol}'>{arrow}</td>"
                f"<td><b>{_won(r.hdt_member)}</b></td></tr>")
        st.markdown(NEW_CSS + "<div class='rewrap'><div class='rescroll'>"
                    "<table class='retbl'><thead>" + head + "</thead><tbody>"
                    + "".join(body) + "</tbody></table></div></div>",
                    unsafe_allow_html=True)
        _dl("📥 손대야 하는 날 엑셀 (서식 유지)",
            [{'sheet': '손대야 하는 날', 'title': "🔔 지금 손대야 하는 날",
              'firstcol': '일자',
              'head1': ['요일', 'D-', '연휴', '이전 잔여', '현재 잔여', '판매(실)',
                        '페이스', '재고', 'floor', '이전 칸', '현재 칸', '이동',
                        'HDT 회원가'],
              'head2': None,
              'headc': ['#F3F5F7'] * 9 + ['#FFF3E6', '#FFE4CC', '#FFE4CC', '#F3F5F7'],
              'rows': [{'label': r.date.strftime('%m/%d'), 'cells': [
                  {'t': r.dow, 'bold': False},
                  {'t': f"D-{r.dta}", 'bold': False},
                  {'t': r.hol or "—", 'bold': False},
                  {'t': _won(r.p_avail), 'bold': False},
                  {'t': _won(r.tot_avail), 'bold': False},
                  {'t': _won(r.sold)},
                  {'t': ("—" if r.pace_adj == 0 else
                         (f"▲{-r.pace_adj}" if r.pace_adj < 0 else f"▼{r.pace_adj}"))},
                  {'t': ("—" if r.inv_adj == 0 else f"▲{-r.inv_adj}")},
                  {'t': r.floor or "—", 'bold': False},
                  {'t': r.p_lab, 'bg': new_color(r.p_rung)[0],
                   'fg': new_color(r.p_rung)[1]},
                  {'t': r.lab, 'bg': new_color(r.rung)[0], 'fg': new_color(r.rung)[1]},
                  {'t': (f"▲{r.rung_move}" if r.rung_move > 0 else f"▼{-r.rung_move}"),
                   'fg': '#C62828' if r.rung_move > 0 else '#1565C0'},
                  {'t': _won(r.hdt_member)},
              ]} for r in mv.itertuples()], 'cw': 12, 'wide': 11,
              'note': "이전 칸 ▶ 현재 칸 두 열이 실제로 바꿔야 하는 값입니다."}],
            "손대야하는날", "dl_chg_list")

    # ── 가로 매트릭스: 행 = 객실 · 열 = 날짜 ──────────────────────
    if type_cmp is not None and not type_cmp.empty and day_df is not None \
            and not day_df.empty:
        st.divider()
        st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
        mvonly = st.checkbox("바뀐 셀만 강조 (안 바뀐 셀은 흐리게)", value=True,
                             key="new_chg_mxonly")
        dts, _m, _r = _mx_controls(day_df, "new_chg_mx")
        if dts:
            dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
            tix = type_cmp.drop_duplicates(subset=['date', 'rt'], keep='first')
            tix = tix.set_index(['date', 'rt'])
            st.markdown(_mx_title("이전 대비 변화 — 행 = 객실 · 열 = 날짜", True),
                        unsafe_allow_html=True)
            st.markdown(_legend("<b>굵은 테두리</b> 바꿔야 할 셀 "
                                "<b>흐린 셀</b> 그대로"), unsafe_allow_html=True)
            head = _mx_head(dts, dmap, "객실")
            rows, xrows = [], []
            cells, xcells = [], []
            for d in dts:
                sub = day_cmp[day_cmp['date'] == d]
                if sub.empty:
                    cells.append("<td class='mut'>—</td>")
                    xcells.append({'t': "—", 'bold': False})
                    continue
                r = sub.iloc[0]
                mvv = int(r['rung_move'])
                bg, fg = new_color(int(r['rung']))
                if mvv == 0:
                    kls = "c3 dim" if mvonly else "c3"
                    stl = "" if mvonly else f"background:{bg};color:{fg}"
                    cells.append(f"<td class='{kls}' style='{stl}'>{r['lab']}"
                                 f"<em>— · {_won(r['sold'])}실</em></td>")
                    xcells.append({'t': r['lab'], 's': f"— · {_won(r['sold'])}실",
                                   'bg': '#FCFCFD' if mvonly else bg,
                                   'fg': '#CBD0D5' if mvonly else fg, 'bold': False})
                else:
                    arw = f"▲{mvv}" if mvv > 0 else f"▼{-mvv}"
                    cells.append(f"<td class='c3 hit' style='background:{bg};color:{fg}'>"
                                 f"{r['lab']}<em>{r['p_lab']} {arw}</em>"
                                 f"<i style='color:{fg};opacity:.85'>"
                                 f"{_won(r['sold'])}실</i></td>")
                    xcells.append({'t': r['lab'], 's': f"{r['p_lab']} {arw}",
                                   's2': f"{_won(r['sold'])}실", 'bg': bg, 'fg': fg})
            rows.append("<tr class='gend'><td class='rh'>날짜 칸 (기준)"
                        "<em>현재 칸 · 이전 ▲▼ · 판매</em></td>"
                        + "".join(cells) + "</tr>")
            xrows.append({'label': '날짜 칸 (기준)', 'sub': '현재 · 이전▲▼ · 판매',
                          'group_end': True, 'cells': xcells})
            for rt in NEW_ROW_ORDER:
                cls = "gend" if rt in NEW_GROUP_END else ""
                cells, xcells = [], []
                for d in dts:
                    key = (d, rt)
                    if key not in tix.index:
                        cells.append("<td class='mut'>—</td>")
                        xcells.append({'t': "—", 'bold': False})
                        continue
                    row = tix.loc[key]
                    mvv = int(row['rung_move'])
                    sold = row['sold']
                    bg, fg = new_color(int(row['rung']))
                    pm = int(row['price_move'] or 0)
                    if mvv == 0:
                        if mvonly:
                            cells.append(f"<td class='c3 dim'>{row['lab']}"
                                         f"<em>— · {_won(sold)}실</em></td>")
                        else:
                            cells.append(f"<td class='c3' style='background:{bg};"
                                         f"color:{fg};font-weight:700'>{row['lab']}"
                                         f"<em>— · {_won(sold)}실</em></td>")
                        xcells.append({'t': row['lab'], 's': f"— · {_won(sold)}실",
                                       'bg': '#FCFCFD' if mvonly else bg,
                                       'fg': '#CBD0D5' if mvonly else fg,
                                       'bold': False})
                        continue
                    arw = f"▲{mvv}" if mvv > 0 else f"▼{-mvv}"
                    cells.append(f"<td class='c3 hit' style='background:{bg};color:{fg}'>"
                                 f"{row['lab']}<em>{row['p_lab']} {arw}</em>"
                                 f"<i style='color:{fg};opacity:.85'>{pm:+,}원</i></td>")
                    xcells.append({'t': row['lab'], 's': f"{row['p_lab']} {arw}",
                                   's2': f"{pm:+,}원", 'bg': bg, 'fg': fg})
                rows.append(
                    f"<tr class='{cls}'><td class='rh'>{rt}"
                    f"<em>{NEW_ROOM_NAMES.get(rt,'')}</em></td>"
                    + "".join(cells) + "</tr>")
                xrows.append({'label': rt, 'sub': NEW_ROOM_NAMES.get(rt, ''),
                              'group_end': rt in NEW_GROUP_END, 'cells': xcells})
            st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                        + "".join(rows) + "</tbody></table></div>",
                        unsafe_allow_html=True)
            st.caption("**굵은 테두리 + 큰 글씨 = 바꿔야 할 셀**입니다. "
                       "큰 글씨가 현재 칸, 그 아래가 '이전 칸 ▲▼이동칸수', 맨 아래가 "
                       "회원가 차액입니다. 흐린 셀은 칸이 그대로라 손댈 필요가 없습니다. "
                       "맨 윗줄은 그날의 날짜 칸(기준)이고 아래가 객실타입별입니다.")
            _dl("📥 이 표 엑셀 (서식 유지)",
                [{'sheet': '이전 대비 변화',
                  'title': "이전 대비 변화 — 행 = 객실 · 열 = 날짜",
                  'firstcol': '객실',
                  'head1': [d.strftime('%m-%d') for d in dts],
                  'head2': [WD_KR[d.weekday()] for d in dts],
                  'headc': ['#FBEADB' if str(dmap.loc[d, 'hol'] or "") else '#F3F5F7'
                            for d in dts],
                  'rows': xrows, 'cw': 11,
                  'note': "색칠 + 굵은 글씨 = 칸이 바뀐 셀. 흐린 셀은 그대로."}],
                "이전대비변화", "dl_chg_mx")

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
# 11-A. 서식이 살아 있는 엑셀 내보내기
# -----------------------------------------------------------------------------
#  화면 표를 '텍스트만' 뽑으면 색이 사라져서 읽는 맛이 없어집니다.
#  여기서는 셀 배경 · 글자색 · 굵기 · 굵은 구분선 · 첫 열 고정까지 그대로 옮깁니다.
# =============================================================================
def _hx(c):
    """'#RRGGBB' → openpyxl 이 쓰는 'FFRRGGBB'."""
    c = (c or "").lstrip('#')
    return ("FF" + c.upper()) if len(c) == 6 else "FFFFFFFF"


def _xl_styled(blocks):
    """서식을 유지한 엑셀 바이트를 만듭니다.

    blocks: [{
      'sheet': 시트명, 'title': 제목줄, 'note': 하단 설명,
      'head1': [1행 헤더], 'head2': [2행 헤더(없으면 None)],
      'headc': [헤더 배경색(없으면 None)],
      'rows': [{'label','sub','group_end',
                'cells':[{'t','s','s2','bg','fg','bold'}]}],
      'wide': 첫 열 너비(기본 20)
    }]
    """
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    thin = Side(style='thin', color='FFD9DEE3')
    thick = Side(style='medium', color='FF16202B')
    wb = Workbook()
    wb.remove(wb.active)

    for blk in blocks:
        ws = wb.create_sheet((blk.get('sheet') or 'Sheet')[:31])
        h1 = blk.get('head1') or []
        h2 = blk.get('head2')
        headc = blk.get('headc') or [None] * len(h1)
        ncol = len(h1) + 1

        r = 1
        if blk.get('title'):
            ws.cell(row=1, column=1, value=blk['title'])
            ws.cell(row=1, column=1).font = Font(bold=True, size=13, color='FF16202B')
            ws.merge_cells(start_row=1, start_column=1,
                           end_row=1, end_column=max(2, min(ncol, 40)))
            ws.row_dimensions[1].height = 24
            r = 2

        hr1 = r
        ws.cell(row=hr1, column=1, value=blk.get('firstcol') or "")
        for j, v in enumerate(h1, start=2):
            c = ws.cell(row=hr1, column=j, value=v)
            c.font = Font(bold=True, size=9)
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = PatternFill('solid', fgColor=_hx(headc[j - 2] or '#F3F5F7'))
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        ws.cell(row=hr1, column=1).font = Font(bold=True, size=9)
        ws.cell(row=hr1, column=1).fill = PatternFill('solid', fgColor=_hx('#F3F5F7'))
        ws.cell(row=hr1, column=1).border = Border(left=thin, right=thick,
                                                  top=thin, bottom=thin)
        ws.row_dimensions[hr1].height = 18
        rr = hr1 + 1

        if h2:
            for j, v in enumerate(h2, start=2):
                c = ws.cell(row=rr, column=j, value=v)
                c.font = Font(bold=True, size=9)
                c.alignment = Alignment(horizontal='center', vertical='center')
                c.fill = PatternFill('solid', fgColor=_hx(headc[j - 2] or '#F3F5F7'))
                c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            c = ws.cell(row=rr, column=1, value="")
            c.fill = PatternFill('solid', fgColor=_hx('#F3F5F7'))
            c.border = Border(left=thin, right=thick, top=thin, bottom=thin)
            ws.row_dimensions[rr].height = 16
            rr += 1

        first_data = rr
        for row in blk.get('rows') or []:
            lab = row.get('label') or ""
            if row.get('sub'):
                lab = f"{lab}\n{row['sub']}"
            c = ws.cell(row=rr, column=1, value=lab)
            c.font = Font(bold=True, size=9)
            c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            bot = thick if row.get('group_end') else thin
            c.border = Border(left=thin, right=thick, top=thin, bottom=bot)
            for j, cell in enumerate(row.get('cells') or [], start=2):
                txt = "\n".join([x for x in (cell.get('t'), cell.get('s'),
                                             cell.get('s2')) if x])
                cc = ws.cell(row=rr, column=j, value=txt)
                cc.font = Font(bold=bool(cell.get('bold', True)), size=9,
                               color=_hx(cell.get('fg') or '#16202B'))
                cc.alignment = Alignment(horizontal='center', vertical='center',
                                         wrap_text=True)
                if cell.get('bg'):
                    cc.fill = PatternFill('solid', fgColor=_hx(cell['bg']))
                cc.border = Border(left=thin, right=thin, top=thin, bottom=bot)
            ws.row_dimensions[rr].height = 34
            rr += 1

        if blk.get('note'):
            ws.cell(row=rr + 1, column=1, value=blk['note'])
            ws.cell(row=rr + 1, column=1).font = Font(size=9, color='FF6B7280')
            ws.cell(row=rr + 1, column=1).alignment = Alignment(wrap_text=True,
                                                                vertical='top')
            ws.merge_cells(start_row=rr + 1, start_column=1,
                           end_row=rr + 3, end_column=max(2, min(ncol, 14)))

        ws.column_dimensions['A'].width = blk.get('wide', 20)
        for j in range(2, ncol + 1):
            ws.column_dimensions[get_column_letter(j)].width = blk.get('cw', 10)
        ws.freeze_panes = ws.cell(row=first_data, column=2)
        ws.sheet_view.showGridLines = False

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _dl(label, blocks, fname, key):
    """표 바로 아래 붙는 서식 유지 엑셀 다운로드 버튼."""
    try:
        data = _xl_styled(blocks)
    except Exception as e:                              # noqa: BLE001
        st.caption(f"엑셀 만들기 실패: {type(e).__name__}: {e}")
        return
    st.download_button(
        label, data=data,
        file_name=f"{fname}_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key)


# =============================================================================
# 11-B. 가로 매트릭스 — 행 = 객실 · 열 = 날짜 (기존 앱과 같은 문법)
# -----------------------------------------------------------------------------
#    · 2단 헤더 — 위 MM-DD, 아래 요일 (일=빨강 / 토=파랑), 연휴 열은 주황
#    · 첫 열 고정 + 오른쪽 굵은 경계선
#    · HDF · PPV 행 아래 굵은 구분선
#    · 월요일 앞에 주 구분선 — 주 단위로 눈이 끊어져 훑기 쉬워집니다
# =============================================================================
NEW_MX_CSS = """
<style>
.mxwrap{overflow-x:auto;white-space:nowrap;border:1px solid #D9DEE3;border-radius:6px;
    background:#fff}
.mx{border-collapse:separate;border-spacing:0;font-size:11.5px;
    font-variant-numeric:tabular-nums}
.mx th,.mx td{border-right:1px solid #E7EBEF;border-bottom:1px solid #E7EBEF;
    padding:4px 5px;text-align:center;white-space:nowrap;min-width:58px}
.mx thead th{background:#F3F5F7;font-weight:700;font-size:10.5px;color:#414A54;
    position:sticky;top:0;z-index:5}
.mx thead tr:nth-child(2) th{top:22px}
.mx thead th.hd{background:#FBEADB;color:#8C4A1E}
.mx th.rh,.mx td.rh{position:sticky;left:0;z-index:6;background:#fff;text-align:left;
    border-right:3px solid #16202B;min-width:140px;font-weight:700;padding:5px 9px}
.mx thead th.rh{background:#F3F5F7;z-index:7}
.mx td.rh em{display:block;font-style:normal;font-size:9px;font-weight:400;color:#7D858C}
.mx tr.gend td,.mx tr.gend th{border-bottom:3px solid #16202B}
.mx td.wk,.mx th.wk{border-left:2px solid #B9C1C9}
.mx td.c3{line-height:1.15}
.mx td.c3 em{display:block;font-style:normal;font-size:9.5px;opacity:.9;font-weight:600}
.mx td.c3 i{display:block;font-style:normal;font-size:8.5px;opacity:.75;font-weight:400}
/* 칸 크게 */
.mx td.big{font-size:19px;font-weight:800;line-height:1.08;letter-spacing:-.03em;
    padding:6px 4px}
.mx td.big em{font-size:10px;font-weight:600}
.mx td.big i{font-size:8.5px}
.mx td.rgbig{font-size:16px;font-weight:800;letter-spacing:-.02em}
.mx td.rgsub em{font-size:12.5px;font-weight:800;letter-spacing:-.02em;opacity:1}
/* 판매 마감 — 사선으로 확실히 죽입니다 */
.mx td.off{color:#A8AEB4;font-weight:500;
    background:repeating-linear-gradient(135deg,#F4F5F6 0 5px,#EAECEE 5px 10px)}
.mx td.off em,.mx td.off i{color:#B4BAC0}
.mx td.mut{color:#8A929A;font-weight:400}
/* 이전 대비 변화 강조 */
.mx td.hit{outline:3px solid #16202B;outline-offset:-3px;font-size:17px;font-weight:800;
    line-height:1.06;letter-spacing:-.03em;padding:5px 4px}
.mx td.hit em{font-size:10.5px;font-weight:800;opacity:1}
.mx td.hit i{font-size:9px;font-weight:600}
.mx td.dim{background:#FCFCFD!important;color:#CBD0D5!important;font-weight:400!important;
    font-size:10px}
.mx td.dim em,.mx td.dim i{color:#DCE0E4!important}
.retbl tr.hitrow td{background:#FFFAF4}
.retbl tr.hitrow td.dt{border-left:5px solid #B5602C;background:#FFF2E4}
.retbl td.mvbig{font-size:16px;font-weight:800;letter-spacing:-.02em;padding:3px 7px}
.retbl td.arw{font-size:15px;font-weight:800}
/* 제목 · 범례 */
.mxtitle{margin:20px 0 6px;font-weight:700;font-size:15px;padding:9px 13px;
    background:#F0F2F6;border-left:9px solid #16202B;border-radius:0 5px 5px 0}
.mxtitle.acc{background:#E9F1F8;border-left-color:#1F5C8B}
.mxlg{display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin:4px 0 8px;
    font-size:10.5px;color:#6B7280}
.mxlg b{color:#414A54;font-weight:700;margin-right:3px}
.mxlg span.sw{display:inline-block;width:22px;height:13px;border:1px solid #D9DEE3;
    border-radius:2px}
.mxlg span.sep{margin:0 6px;color:#C9CFD5}
.mxlg span.hz{display:inline-block;width:22px;height:13px;border:1px solid #D9DEE3;
    border-radius:2px;
    background:repeating-linear-gradient(135deg,#F4F5F6 0 4px,#EAECEE 4px 8px)}
</style>
"""

NEW_ROW_ORDER = list(NEW_ROOMS)
NEW_GROUP_END = {"HDF", "PPV"}


def _mx_head(dates, dmap=None, first_col="객실"):
    """2단 날짜 헤더. 연휴 열은 물들이고, 월요일 앞에 주 구분선을 넣습니다."""
    h1 = [f"<th class='rh' rowspan='2'>{first_col}</th>"]
    h2 = []
    for i, d in enumerate(dates):
        hol = ""
        if dmap is not None and d in dmap.index:
            hol = str(dmap.loc[d, 'hol'] or "")
        cls = ("hd " if hol else "") + ("wk" if (d.weekday() == 0 and i) else "")
        h1.append(f"<th class='{cls}' title='{hol}'>{d.strftime('%m-%d')}</th>")
        wd = WD_KR[d.weekday()]
        col = "#D32F2F" if wd == '일' else ("#1565C0" if wd == '토' else "#5A636B")
        h2.append(f"<th class='{cls}' style='color:{col}'>{wd}</th>")
    return "<thead><tr>" + "".join(h1) + "</tr><tr>" + "".join(h2) + "</tr></thead>"


def _wkcls(dates, i):
    return " wk" if (i and dates[i].weekday() == 0) else ""


def _mx_title(text, accent=False):
    return f"<div class='mxtitle{' acc' if accent else ''}'>{text}</div>"


def _legend(extra=None):
    sw = "".join(f"<span class='sw' style='background:{new_color(i)[0]}'></span>"
                 for i in (1, 3, 5, 7, 9, 11, 13, 15, 16))
    parts = [f"<b>칸</b>{sw} <span style='margin-left:4px'>B0pp(비쌈) → B13(쌈)</span>",
             "<span class='sep'>|</span><b>마감</b><span class='hz'></span>",
             "<span class='sep'>|</span><b>★</b> RM 승인 구간(B1↑)",
             "<span class='sep'>|</span><b>✋</b> 수동 예외",
             "<span class='sep'>|</span><b>주황 머리</b> 연휴"]
    if extra:
        parts.append("<span class='sep'>|</span>" + extra)
    return "<div class='mxlg'>" + "".join(parts) + "</div>"


def _mx_controls(day_df, key, cell_modes=None, default_mode=0):
    """표 위 컨트롤을 한 줄로 모읍니다 — 기본은 '한 달씩'.

    반환: (dates, mode, rooms)
    """
    if day_df is None or day_df.empty:
        return [], None, list(NEW_ROW_ORDER)
    all_d = sorted(day_df['date'].unique())
    sub = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
    months = sorted({(d.year, d.month) for d in all_d})
    labels = [f"{y}년 {m}월" for y, m in months]
    fut = [d for d in all_d if int(sub.loc[d, 'dta']) >= 0]
    cur_key = None
    if fut:
        cur_key = f"{fut[0].year}년 {fut[0].month}월"

    c = st.columns([2, 3, 2] if cell_modes else [3, 3])
    with c[0]:
        span = st.radio("보기 범위", ["한 달씩", "전체 기간"], horizontal=True,
                        key=f"{key}_span")
    idx = 0
    if span == "한 달씩":
        with c[1]:
            if cur_key in labels:
                idx = labels.index(cur_key)
            pick = st.radio("월", labels, index=idx, horizontal=True, key=f"{key}_mon")
        keep = {tuple(int(x.rstrip('년월')) for x in pick.split())}
        dates = [d for d in all_d if (d.year, d.month) in keep]
    else:
        dates = list(all_d)
        with c[1]:
            st.caption("전체 기간을 한 표에 펼칩니다. 좌우로 스크롤하세요.")

    mode = None
    if cell_modes:
        with c[2]:
            mode = st.radio("셀 내용", cell_modes, index=default_mode,
                            key=f"{key}_mode")

    with st.expander("🔧 더 좁히기 — 객실타입 · 과거 날짜", expanded=False):
        e1, e2 = st.columns([4, 1])
        with e1:
            rooms = st.multiselect("객실타입", NEW_ROW_ORDER, default=NEW_ROW_ORDER,
                                   key=f"{key}_rooms")
        with e2:
            past = st.checkbox("과거 포함", value=False, key=f"{key}_past")
    if not past:
        dates = [d for d in dates if int(sub.loc[d, 'dta']) >= 0]
    return dates, mode, (rooms or list(NEW_ROW_ORDER))


# =============================================================================
# 15-B. 탭 5 — 최종 요금 (원장)
# -----------------------------------------------------------------------------
#  왜 이 탭이 따로 있는가 — 다른 탭과 목적이 다릅니다.
#
#    다른 탭 (일자별 · 타입별 · 변화)  = "무엇을 바꿔야 하나"  → 판단용
#      · 미래 날짜만, 한 달씩, 조정 근거를 강조
#      · 마감 셀은 눌러서 죽임 (지금 팔 수 없는 재고니까)
#
#    이 탭                            = "지금 무엇이 확정돼 있나" → 조회용 원장
#      · 전 기간 · 과거 포함 · 마감 포함이 기본
#      · 마감·오버부킹도 요금을 끝까지 표시합니다. 이유:
#          ① 마감된 날도 채널에 로드된 요금은 실재합니다 (대조 필요)
#          ② 취소가 나면 그 요금으로 다시 열립니다
#          ③ 사후 검증 — "그날 얼마로 닫았나"를 봐야 합니다
#      · 셀 하나를 고르면 앵커부터 최종까지 계산 이력을 한 장으로 봅니다
#      · 플랫 원장(날짜 x 타입 한 행씩)으로 검색·정렬·엑셀
# =============================================================================
_FIN_FIELDS = [("로드(BAR)", 'load'), ("회원 노출가", 'member'), ("해외 랙", 'rack'),
               ("Flexible 하한", 'floor_flex'), ("NRF 하한", 'floor_nrf')]


def _new_tab_final(day_df, type_df, ov_raw=None):
    if day_df is None or day_df.empty or type_df is None or type_df.empty:
        st.info("리포트를 업로드하세요.")
        return
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='renote'><b>지금 확정돼 있는 요금을 그대로 보여주는 원장입니다.</b> "
        "다른 탭은 '무엇을 바꿔야 하나'를 보는 판단용이라 미래 날짜만 · 한 달씩 · 마감 셀은 "
        "눌러서 보여주지만, 이 탭은 <b>전 기간 · 과거 포함 · 마감 포함</b>이 기본입니다.<br>"
        "마감·오버부킹된 셀도 요금을 끝까지 표시합니다 — 마감된 날도 채널에 로드된 요금은 "
        "실재하고, 취소가 나면 그 요금으로 다시 열리며, 사후에 \\u201c그날 얼마로 닫았나\\u201d를 "
        "확인해야 하기 때문입니다.</div>", unsafe_allow_html=True)

    all_d = sorted(day_df['date'].unique())
    dsub = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
    months = sorted({(d.year, d.month) for d in all_d})
    mlabels = [f"{y}년 {m}월" for y, m in months]

    c1, c2, c3 = st.columns([2, 3, 2])
    with c1:
        span = st.radio("기간", ["전 기간", "월별"], horizontal=True, key="fin_span")
    with c2:
        if span == "월별":
            pick = st.multiselect("월", mlabels, default=mlabels, key="fin_mon")
            keep = {tuple(int(x.rstrip('년월')) for x in p.split()) for p in pick}
            dates = [d for d in all_d if (d.year, d.month) in keep]
        else:
            dates = list(all_d)
            st.caption(f"{len(all_d)}일 전체 · {all_d[0]} ~ {all_d[-1]}")
    with c3:
        fld_nm = st.selectbox("표시 요금", [n for n, _ in _FIN_FIELDS], key="fin_fld")
    field = dict(_FIN_FIELDS)[fld_nm]
    with st.expander("🔧 객실타입 좁히기", expanded=False):
        rooms = st.multiselect("객실타입", NEW_ROW_ORDER, default=NEW_ROW_ORDER,
                               key="fin_rooms")
    order = [r for r in NEW_ROW_ORDER if r in (rooms or NEW_ROW_ORDER)]
    if not dates or not order:
        st.warning("표시할 날짜 또는 객실이 없습니다.")
        return

    tix = type_df.drop_duplicates(subset=['date', 'rt'], keep='first')
    tix = tix.set_index(['date', 'rt'])
    view = type_df[type_df['date'].isin(dates)
                   & type_df['rt'].astype(str).isin(order)].copy()

    # ── ④ 기간 요약 ───────────────────────────────────────────────
    open_cells = view[~view['stop']]
    c = st.columns(6)
    c[0].metric("조회 셀", f"{len(view):,}")
    c[1].metric("판매 마감", f"{int(view['stop'].sum()):,}")
    c[2].metric(f"{fld_nm} 중앙",
                f"{int(open_cells[field].median()):,}원" if len(open_cells) else "—")
    c[3].metric("칸 범위",
                f"{new_lab(int(view['rung'].min()))} ~ {new_lab(int(view['rung'].max()))}")
    c[4].metric("계단 상향", f"{int((view['ladder_up'] > 0).sum()):,}셀")
    c[5].metric("수동 예외", f"{int(view['is_override'].sum()):,}셀")

    # ── ① 원장 매트릭스 (마감 포함) ────────────────────────────────
    st.markdown(_mx_title(f"① 확정 요금 원장 · {fld_nm} — 마감 셀도 그대로 표시", True),
                unsafe_allow_html=True)
    st.markdown(_legend("<b>점선 테두리</b> 판매 마감 · <b>⇧</b> 계단 상향"),
                unsafe_allow_html=True)
    head = _mx_head(dates, dsub, "객실")
    rows, xrows = [], []

    cs, xs = [], []
    for i, d in enumerate(dates):
        r = dsub.loc[d]
        bg, fg = new_color(int(r['rung']))
        cs.append(f"<td class='c3{_wkcls(dates, i)}' style='background:{bg};color:{fg};"
                  f"font-weight:700'>{r['lab']}<em>D-{int(r['dta'])}</em></td>")
        xs.append({'t': r['lab'], 's': f"D-{int(r['dta'])}", 'bg': bg, 'fg': fg})
    rows.append("<tr class='gend'><td class='rh'>날짜 칸 (기준)<em>리드타임</em></td>"
                + "".join(cs) + "</tr>")
    xrows.append({'label': '날짜 칸 (기준)', 'sub': '리드타임', 'group_end': True,
                  'cells': xs})

    for rt in order:
        gend = rt in NEW_GROUP_END
        cs, xs = [], []
        for i, d in enumerate(dates):
            wk = _wkcls(dates, i)
            key = (d, rt)
            if key not in tix.index:
                cs.append(f"<td class='mut{wk}'>—</td>")
                xs.append({'t': "—", 'bold': False})
                continue
            row = tix.loc[key]
            bg, fg = new_color(int(row['rung']))
            mk = ""
            if bool(row['is_override']):
                mk += "✋"
            elif row['approval']:
                mk += "★"
            if int(row.get('ladder_up', 0) or 0):
                mk += "⇧"
            closed = bool(row['stop'])
            # ※ 마감이어도 요금을 지우지 않습니다. 점선 테두리 + 배지로만 구분.
            extra = ("outline:2px dashed #6B7280;outline-offset:-2px;"
                     if closed else "")
            badge = (f"<i style='color:{fg};opacity:.9;font-weight:700'>"
                     f"{row['state']} {_won(row['avail'])}실</i>" if closed else
                     f"<i style='color:{fg};opacity:.75'>{_won(row['avail'])}실</i>")
            cs.append(f"<td class='c3{wk}' style='background:{bg};color:{fg};"
                      f"font-weight:700;{extra}'>{_won(row[field])}"
                      f"<em>{row['lab']}{mk}</em>{badge}</td>")
            xs.append({'t': _won(row[field]),
                       's': f"{row['lab']}{mk}",
                       's2': (f"{row['state']} {_won(row['avail'])}실" if closed
                              else f"{_won(row['avail'])}실"),
                       'bg': bg, 'fg': fg})
        rows.append(f"<tr class='{'gend' if gend else ''}'><td class='rh'>{rt}"
                    f"<em>{NEW_ROOM_NAMES.get(rt,'')}</em></td>"
                    + "".join(cs) + "</tr>")
        xrows.append({'label': rt, 'sub': NEW_ROOM_NAMES.get(rt, ''),
                      'group_end': gend, 'cells': xs})

    st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption("셀 = 요금 / 칸 / 잔여. **점선 테두리 + '마감·오버부킹' 배지**가 붙은 셀은 "
               "지금 팔 수 없지만 요금은 그대로 로드돼 있는 상태입니다. "
               "★ RM 승인 구간 · ✋ 수동 예외 · ⇧ 역전방지 계단.")
    _dl(f"📥 이 원장 엑셀 (서식 유지) — {fld_nm}",
        [{'sheet': '확정 요금 원장', 'title': f"확정 요금 원장 · {fld_nm} (마감 포함)",
          'firstcol': '객실',
          'head1': [d.strftime('%m-%d') for d in dates],
          'head2': [WD_KR[d.weekday()] for d in dates],
          'headc': ['#FBEADB' if str(dsub.loc[d, 'hol'] or "") else '#F3F5F7'
                    for d in dates],
          'rows': xrows, 'cw': 11,
          'note': "마감·오버부킹 셀도 요금을 그대로 표시합니다 "
                  "(채널 로드 대조 · 취소 시 재오픈 · 사후 검증)."}],
        f"확정요금원장_{fld_nm}", "dl_final_mx")

    # ── ② 셀 드릴다운 — 이 요금이 왜 이렇게 나왔나 ─────────────────
    st.divider()
    st.markdown("##### ② 이 요금은 왜 이렇게 나왔나 — 계산 이력")
    st.caption("날짜와 객실을 고르면 앵커부터 최종 요금까지 단계별로 펼칩니다. "
               "날짜 단계(3번 탭)와 타입 단계(4번 탭)가 한 화면에 이어집니다.")
    q1, q2 = st.columns([3, 2])
    with q1:
        qd = st.selectbox(
            "날짜", dates,
            format_func=lambda x: (f"{x.strftime('%Y-%m-%d')} ({WD_KR[x.weekday()]}) "
                                   f"· {dsub.loc[x, 'lab']}"
                                   + (f" · {dsub.loc[x, 'hol']}"
                                      if dsub.loc[x, 'hol'] else "")),
            key="fin_qd")
    with q2:
        qr = st.selectbox("객실", order,
                          format_func=lambda x: f"{x} {NEW_ROOM_NAMES.get(x,'')}",
                          key="fin_qr")
    if (qd, qr) in tix.index:
        dr = dsub.loc[qd]
        tr = tix.loc[(qd, qr)]
        steps = []

        def add(no, nm, val, note=""):
            steps.append({"단계": no, "내용": nm, "결과": val, "근거": note})

        add("1", "앵커 (월 x 요일)", dr['anchor_lab'],
            f"{qd.month}월 {WD_KR[qd.weekday()]}요일 앵커")
        add("2", "연휴 반영", new_lab(int(dr['after_hol'])),
            f"{dr['hol']} → {NEW_HOLIDAY_STEP}칸 상향" if dr['hol'] else "연휴 아님")
        pa = int(dr['pace_adj'])
        add("3", "페이스 (이전 기록 대비)",
            new_lab(int(dr['after_hol']) + pa),
            ("소진 배수 %.2f → %s%d칸" % (dr['pace_ratio'], "▲" if pa < 0 else "▼", abs(pa))
             if pa and dr['pace_ratio'] == dr['pace_ratio'] else
             ("D-%d — 페이스 창 밖" % int(dr['dta']) if int(dr['dta']) > NEW_PACE_LEAD_UP_MAX
              else "조정 없음")))
        ia = int(dr['inv_adj'])
        add("4", "호텔 재고", dr['pre_lab'],
            (f"총잔여율 {_pct(_num(dr['remh']))} → ▲{-ia}칸" if ia else
             f"총잔여율 {_pct(_num(dr['remh']))} — 조정 없음"))
        add("5", "Peak Event Floor", dr['ev_floor'] or "—",
            f"{dr['ev']} 최소 {dr['ev_floor']}" if dr['ev_floor'] else "해당 없음")
        add("6", "Scarcity Floor", dr['sc_floor'] or "—",
            f"총잔여율 기준 최소 {dr['sc_floor']}" if dr['sc_floor'] else "해당 없음")
        add("=", "날짜 확정 칸", dr['lab'],
            dr['floor_by'] or ("수동 예외" if dr['is_override'] else "floor 구속 없음"))
        ta = int(tr['tadj'])
        add("7", "객실타입 조정", new_lab(int(tr['day_rung']) + ta),
            (f"잔여 {_won(tr['avail'])}/{tr['cap']}실 "
             f"({_pct(_num(tr['remt']))}) → {'▲' if ta < 0 else '▼'}{abs(ta)}칸"
             if ta else f"잔여 {_won(tr['avail'])}/{tr['cap']}실 — 조정 없음"))
        lu = int(tr.get('ladder_up', 0) or 0)
        add("8", "역전방지 계단", new_lab(int(tr['rung'])) if lu else "—",
            f"하급 객실 서열 보장 → ▲{lu}칸" if lu else "발동 안 함")
        if bool(tr['is_override']):
            add("✋", "수동 예외", tr['lab'], "사람이 고정한 칸 (자동 계산을 덮음)")
        st.dataframe(pd.DataFrame(steps), use_container_width=True, hide_index=True)

        bg, fg = new_color(int(tr['rung']))
        cards = [("확정 칸", tr['lab']), ("로드(BAR)", _won(tr['load'])),
                 ("회원 노출가", _won(tr['member'])), ("해외 랙", _won(tr['rack'])),
                 ("Flexible 하한", _won(tr['floor_flex'])),
                 ("NRF 하한", _won(tr['floor_nrf']))]
        st.markdown(
            "<div style='display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 2px'>"
            + "".join(
                f"<div style='flex:1 1 120px;border:1px solid #D9DEE3;border-radius:6px;"
                f"padding:9px 12px;background:"
                f"{bg if i == 0 else '#fff'};color:{fg if i == 0 else '#16202B'}'>"
                f"<div style='font-size:10.5px;opacity:.8'>{k}</div>"
                f"<div style='font-size:19px;font-weight:800;letter-spacing:-.02em'>"
                f"{v}</div></div>" for i, (k, v) in enumerate(cards))
            + "</div>", unsafe_allow_html=True)
        st.caption(f"{qd.strftime('%Y-%m-%d')} ({WD_KR[qd.weekday()]}) · "
                   f"{qr} {NEW_ROOM_NAMES.get(qr,'')} · {tr['state']} · "
                   f"잔여 {_won(tr['avail'])}/{tr['cap']}실"
                   + (f" · {tr['approval']}" if tr['approval'] else "")
                   + (f"  |  {tr['why']}" if tr['why'] else ""))

    # ── ③ 플랫 원장 ───────────────────────────────────────────────
    st.divider()
    st.markdown("##### ③ 플랫 원장 — 날짜 x 객실 한 행씩")
    st.caption("검색·정렬이 되는 표입니다. 채널에 로드한 값과 대조하거나 "
               "특정 조건(예: 마감인데 요금이 낮은 셀)을 찾을 때 씁니다.")
    f1, f2 = st.columns([2, 3])
    with f1:
        only = st.radio("행 필터", ["전체", "판매 중만", "마감·오버부킹만",
                                 "계단·예외 걸린 셀만"], key="fin_only")
    v = view
    if only == "판매 중만":
        v = v[~v['stop']]
    elif only == "마감·오버부킹만":
        v = v[v['stop']]
    elif only == "계단·예외 걸린 셀만":
        v = v[(v['ladder_up'] > 0) | v['is_override']]
    with f2:
        st.caption(f"{len(v):,}행")
    v = v.copy()
    v['_o'] = v['rt'].astype(str).map({r: i for i, r in enumerate(NEW_ROW_ORDER)})
    v = v.sort_values(['date', '_o'])
    dmapf = dsub
    flat = pd.DataFrame({
        "일자": v['date'].map(lambda x: x.strftime('%Y-%m-%d')),
        "요일": v['dow'], "D-": v['dta'].map(lambda x: f"D-{x}"),
        "연휴": v['date'].map(lambda x: str(dmapf.loc[x, 'hol'] or "—")),
        "객실": v['rt'].astype(str),
        "객실명": v['rt'].astype(str).map(NEW_ROOM_NAMES),
        "전체": v['cap'], "잔여": v['avail'],
        "잔여율(%)": _numcol(v['remt'], 100).round(1),
        "날짜 칸": v['day_lab'], "타입 조정": v['tadj'], "계단": v['ladder_up'],
        "확정 칸": v['lab'],
        "로드(BAR)": v['load'], "회원 노출가": v['member'], "해외 랙": v['rack'],
        "Flex 하한": v['floor_flex'], "NRF 하한": v['floor_nrf'],
        "상태": v['state'], "승인": v['approval'].replace("", "—"),
        "예외": v['is_override'].map({True: "✋", False: ""}),
        "근거": v['why'].replace("", "—"),
    })
    st.dataframe(flat, use_container_width=True, hide_index=True, height=460)
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine='openpyxl') as w:
        flat.to_excel(w, index=False, sheet_name="확정 요금 원장")
        for nm2, f2_ in _FIN_FIELDS:
            p = view.pivot_table(index='rt', columns='date', values=f2_,
                                 aggfunc='first')
            p = p.reindex(index=[r for r in NEW_ROOMS if r in p.index])
            p.columns = [f"{x.strftime('%m-%d')}({WD_KR[x.weekday()]})" for x in p.columns]
            p.index.name = "객실"
            p.to_excel(w, sheet_name=nm2[:31])
        pl = view.pivot_table(index='rt', columns='date', values='lab',
                              aggfunc='first')
        pl = pl.reindex(index=[r for r in NEW_ROOMS if r in pl.index])
        pl.columns = [f"{x.strftime('%m-%d')}({WD_KR[x.weekday()]})" for x in pl.columns]
        pl.index.name = "객실"
        pl.to_excel(w, sheet_name="칸")
    st.download_button("📥 플랫 원장 + 요금 매트릭스 6종 엑셀", data=b.getvalue(),
                       file_name=f"확정요금원장_{date.today().strftime('%Y%m%d')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key="dl_final_flat")


# =============================================================================
# 11-C. 요금표 (앵커 → 칸 → 타입별 요금) — 데이터 없이도 항상 볼 수 있습니다
# =============================================================================
def _diff_tag(rt):
    """행 라벨에 붙는 차액 규칙 한 줄 (없으면 B7 기준 배수)."""
    for c, base, D, g in NEW_DIFF_RULE:
        if c == rt:
            return f"{base} +{D//1000}만" + (f"/{g*100:.1f}%" if g else "")
    return f"x{NEW_MULT.get(rt, 1.0):.3f}"


_RC_VIEWS = {"로드(BAR) 정가": 1.0, "회원 노출가 x0.90": NEW_MEMBER_K,
             "해외 랙 x1.30": NEW_RACK_MULT, "Flexible 하한 x0.72": NEW_FLOOR_FLEX,
             "NRF 하한 x0.66": NEW_FLOOR_NRF}


def _new_tab_ratecard():
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='renote'><b>재고와 무관한 고정 자료입니다.</b> 사다리 16칸, "
        "타입별 배수, 앵커 캘린더 84셀, 연휴·Floor 규칙 — 계산의 재료가 전부 여기 "
        f"있습니다. 판 <b>{NEW_EDITION}</b>.</div>", unsafe_allow_html=True)

    view = st.radio("표시 요금", list(_RC_VIEWS), horizontal=True, key="new_rc_view")
    k = _RC_VIEWS[view]

    def px(rt, i):
        return new_load_price(rt, i) if k == 1.0 else new_k_price(rt, i, k)

    # ── ① 타입별 x 16칸 ───────────────────────────────────────────
    st.markdown(_mx_title(f"① 객실타입별 16칸 요금표 · {view} — 행 = 객실 · 열 = 칸",
                          True), unsafe_allow_html=True)
    h1, h2, hc = [], [], []
    for i in range(1, NEW_N + 1):
        bg, fg = new_color(i)
        h1.append(f"<th style='background:{bg};color:{fg}'>{new_lab(i)}</th>")
        h2.append(f"<th style='font-weight:400;color:#8A929A'>{i}</th>")
        hc.append(bg)
    head = "<thead><tr><th class='rh' rowspan='2'>객실</th>" + "".join(h1) + \
           "</tr><tr>" + "".join(h2) + "</tr></thead>"
    body, xrows = [], []
    for rt in NEW_ROW_ORDER:
        cls = "gend" if rt in NEW_GROUP_END else ""
        body.append(
            f"<tr class='{cls}'><td class='rh'>{rt}"
            f"<em>{NEW_ROOM_NAMES.get(rt,'')} · {_diff_tag(rt)}</em></td>"
            + "".join(f"<td>{_won(px(rt, i))}</td>" for i in range(1, NEW_N + 1))
            + "</tr>")
        xrows.append({'label': rt, 'sub': _diff_tag(rt),
                      'group_end': rt in NEW_GROUP_END,
                      'cells': [{'t': _won(px(rt, i)), 'bold': False}
                                for i in range(1, NEW_N + 1)]})
    st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                + "".join(body) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption("칸 간격 8%. 왼쪽이 비쌉니다. 헤더 아래 숫자는 칸 인덱스(1~16)입니다.")
    _dl(f"📥 요금표 엑셀 (서식 유지) — {view}",
        [{'sheet': '타입별 요금표', 'title': f"객실타입별 16칸 요금표 · {view}",
          'firstcol': '객실', 'head1': [new_lab(i) for i in range(1, NEW_N + 1)],
          'head2': [str(i) for i in range(1, NEW_N + 1)], 'headc': hc,
          'rows': xrows, 'cw': 11,
          'note': "칸 간격 8%. 왼쪽이 비쌉니다. 배수는 HDT=1.0 기준입니다."},
         {'sheet': '앵커 캘린더', 'title': f"앵커 캘린더 84셀 (HDT {view})",
          'firstcol': '월', 'head1': list(WD_KR), 'head2': None,
          'headc': ['#F3F5F7'] * 7,
          'rows': [{'label': f"{m}월", 'cells': [
              {'t': new_lab(NEW_ANCHOR[m][w]), 's': _won(px("HDT", NEW_ANCHOR[m][w])),
               'bg': new_color(NEW_ANCHOR[m][w])[0],
               'fg': new_color(NEW_ANCHOR[m][w])[1]} for w in range(7)]}
              for m in range(1, 13)], 'cw': 13,
          'note': "월 x 요일만 봅니다 — 연도와 무관합니다."}],
        "요금표", "dl_rc1")

    # ── ② 앵커 캘린더 ─────────────────────────────────────────────
    st.markdown(_mx_title("② 앵커 캘린더 84셀 — 행 = 월 · 열 = 요일 (시작 칸)", True),
                unsafe_allow_html=True)
    h = "<thead><tr><th class='rh'>월</th>" + "".join(
        f"<th style=\"color:{'#D32F2F' if w == 6 else ('#1565C0' if w == 5 else '#5A636B')}\">"
        f"{WD_KR[w]}</th>" for w in range(7)) + "</tr></thead>"
    rows = []
    for m in range(1, 13):
        cs = []
        for w in range(7):
            i = NEW_ANCHOR[m][w]
            bg, fg = new_color(i)
            cs.append(f"<td class='c3 big' style='background:{bg};color:{fg}'>"
                      f"{new_lab(i)}<em>{_won(px('HDT', i))}</em></td>")
        rows.append(f"<tr><td class='rh'>{m}월</td>" + "".join(cs) + "</tr>")
    st.markdown("<div class='mxwrap'><table class='mx' style='min-width:640px'>"
                + h + "<tbody>" + "".join(rows) + "</tbody></table></div>",
                unsafe_allow_html=True)
    st.caption(f"금액은 HDT 기준 {view}. 다른 객실은 ① 표의 배수를 곱하십시오. "
               f"이 표는 연도와 무관합니다 — 월 x 요일만 봅니다.")

    # ── ③ 규칙 ────────────────────────────────────────────────────
    st.markdown(_mx_title("③ 앵커 위에 올라가는 규칙"), unsafe_allow_html=True)
    step_df = pd.DataFrame([
        {"단계": "2 연휴", "조건": "공휴일 · 연휴", "조정": "2칸 상향", "배수": "x1.166"},
        {"단계": "3 페이스", "조건": "소진 배수 ≤ 0.25", "조정": "2칸 상향", "배수": "x1.166"},
        {"단계": "3 페이스", "조건": "소진 배수 ≤ 0.50", "조정": "1칸 상향", "배수": "x1.080"},
        {"단계": "3 페이스", "조건": "소진 배수 2.0~4.0", "조정": "1칸 하향", "배수": "x0.926"},
        {"단계": "3 페이스", "조건": "소진 배수 > 4.0", "조정": "2칸 하향", "배수": "x0.857"},
        {"단계": "4 재고", "조건": "총잔여율 ≤ 20%", "조정": "1칸 상향", "배수": "x1.080"},
        {"단계": "4 재고", "조건": "총잔여율 ≤ 12%", "조정": "2칸 상향", "배수": "x1.166"},
        {"단계": "4 재고", "조건": "총잔여율 ≤ 5%", "조정": "3칸 상향", "배수": "x1.260"},
    ])
    floor_df = pd.DataFrame([
        {"종류": "Peak Event (Opening)", "대상": "추석·설날 핵심 3일", "최소 칸": "B3"},
        {"종류": "Peak Event (Opening)", "대상": "10/1~10/5 · 한글날 연휴", "최소 칸": "B3"},
        {"종류": "Peak Event (Opening)", "대상": "크리스마스 이브", "최소 칸": "B3"},
        {"종류": "Peak Event (Opening)", "대상": "크리스마스 · 연휴 · 연말", "최소 칸": "B2"},
        {"종류": "Scarcity (Absolute)", "대상": "총잔여율 ≤ 20%", "최소 칸": "B4"},
        {"종류": "Scarcity (Absolute)", "대상": "총잔여율 ≤ 12%", "최소 칸": "B3"},
        {"종류": "Scarcity (Absolute)", "대상": "총잔여율 ≤ 5%", "최소 칸": "B1"},
    ])
    floor_df["HDT 로드가"] = floor_df["최소 칸"].map(
        lambda x: new_load_price("HDT", new_idx(x)))
    type_df_r = pd.DataFrame([
        {"조건": "타입 잔여율 ≤ 15%", "조정": "2칸 상향"},
        {"조건": "타입 잔여율 ≤ 30%", "조정": "1칸 상향"},
        {"조건": "타입 잔여 ≥85% + 총잔여 ≥60% + D-44 이내", "조정": "2칸 하향 (GDB 제외)"},
        {"조건": "타입 잔여 ≥70% + 총잔여 ≥40% + D-44 이내", "조정": "1칸 하향 (GDB 제외)"},
        {"조건": "그날 총잔여율 ≤ 20%", "조정": "남은 타입 1칸 추가 상향 (희소재)"},
        {"조건": "타입 잔여 0 이하", "조정": "판매 마감 — 요금은 참고값"},
    ])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**연휴 · 페이스 · 재고**")
        st.dataframe(step_df, use_container_width=True, hide_index=True)
        st.caption("페이스 상향은 D-44 이내, 하향은 D-21 이내에서만. 총잔여율 25% 미만이면 "
                   "하향 보류. 재고 단계는 리드타임 무관.")
    with c2:
        st.markdown("**Floor — 이 칸보다 싸게 못 내려갑니다**")
        st.dataframe(floor_df, use_container_width=True, hide_index=True)
        st.caption("Opening 은 D-46 이상 하향 금지 · D-45 1회 재심사(3조건 + RM 승인, "
                   "최대 1칸). Absolute 는 자동 해제도 승인 완화도 없습니다.")
    st.markdown("**객실타입 조정 (7단계)**")
    st.dataframe(type_df_r, use_container_width=True, hide_index=True)
    st.caption(f"하향은 B10(칸 {NEW_TYPE_RUNG_MAX})에서 멈춥니다 — B11~B13은 자동 진입 "
               f"금지(승인 항목). 칸 B1 이상은 헤드룸으로 RM 승인 대상입니다.")

    st.markdown(_mx_title("④ 타입별 차액 규칙 — 정액 + 정률 하이브리드"), unsafe_allow_html=True)
    st.markdown(
        "<div class='renote'>차액 = <b>max(정액, 하급 요금 x 정률)</b>. "
        "정액만 쓰면 성수기에 차액이 칸 간격(8%)보다 작아져 역전이 나고, "
        "정률만 쓰면 비수기에 차액이 1~2만원으로 쪼그라듭니다. "
        "둘 중 큰 값을 쓰면 <b>저가 구간은 정액이, 고가 구간은 정률이</b> 받쳐 줍니다.<br>"
        "한 칸 아래 요금은 현재의 0.926배이므로, 차액이 하급 요금의 <b>7.4%</b>를 넘으면 "
        "한 칸 어긋나도 서열이 뒤집히지 않습니다.</div>", unsafe_allow_html=True)
    dr = []
    for c, base, D, g in NEW_DIFF_RULE:
        row = {"객실": f"{c} {NEW_ROOM_NAMES[c]}",
               "기준 객실": f"{base} {NEW_ROOM_NAMES[base]}",
               "정액": f"{D:,}원", "정률": f"{g*100:.1f}%",
               "교차점": f"{int(D/g):,}원" if g else "—"}
        for lab_i in (1, 5, 10, 16):
            row[f"B{NEW_LAB[lab_i-1]} 차액"] = (
                f"{new_load_price(c, lab_i) - new_load_price(base, lab_i):,}")
        dr.append(row)
    st.dataframe(pd.DataFrame(dr), use_container_width=True, hide_index=True)
    st.caption("교차점 = 정액과 정률이 같아지는 하급 요금. 그보다 싼 칸에서는 정액이, "
               "비싼 칸에서는 정률이 차액을 정합니다. "
               "루나 패밀리는 플로라가 아니라 **가든 더블 EB** 를 기준으로 잡습니다 — "
               "EB 와 플로라는 같은 가격대 대체재라, 플로라가 재고 때문에 내려가도 "
               "루나가 흔들리지 않게 하려는 것입니다.")

    st.markdown(_mx_title("⑤ 역전방지 계단 — 가격 서열을 지킵니다"), unsafe_allow_html=True)
    st.markdown(
        "<div class='renote warn'>타입 조정이 등급별로 독립이라 <b>상급이 하급보다 싸지는</b> "
        "일이 생깁니다. 그러면 하급을 사려던 고객이 상급으로 올라가 <b>하급 재고가 죽고 "
        "상급을 제값보다 싸게 파는 이중 손실</b>이 납니다. 그래서 타입 조정을 마친 뒤 "
        "최소 간격을 강제합니다 — 가격을 임의로 밀지 않고 <b>칸을 올려서</b> 맞추므로 "
        "모든 요금은 항상 사다리 위에 있습니다.<br><br>"
        "발동 기준은 OCC 가 아니라 <b>\u201c하급에 잠식당할 재고가 실제로 남아 있는가\u201d</b> "
        "입니다. 하급이 거의 소진되면 계단에서 빼기 때문에, <b>엠버 트윈만 팔려나갔는데 "
        "다른 타입까지 끌려 올라가는 일이 없습니다.</b></div>", unsafe_allow_html=True)
    _CIR = "\u2460\u2461\u2462\u2463\u2464\u2465\u2466"
    chain_rows = []
    prev_mem = None
    for i, step in enumerate(NEW_LADDER_CHAIN):
        mem = [step] if isinstance(step, str) else list(step)
        nm = " · ".join(f"{r} {NEW_ROOM_NAMES[r]}" for r in mem)
        if len(mem) > 1:
            nm += "  [동일 티어 — 이 안에서는 서열 강제 안 함]"
        if prev_mem is None:
            chain_rows.append({"계층": f"{_CIR[i]} {nm}",
                               "최소 간격": "기준 (가장 낮은 등급)",
                               "같은 칸 실제 간격": "—"})
        else:
            gaps = " / ".join(f"{NEW_LADDER_GAP.get(r, 0):,}" for r in mem)
            nat = [new_load_price(mem[0], j) - new_load_price(prev_mem[0], j)
                   for j in range(1, NEW_N + 1)]
            chain_rows.append({
                "계층": f"{_CIR[i]} {nm}",
                "최소 간격": f"{gaps}원",
                "같은 칸 실제 간격": f"{min(nat):,} ~ {max(nat):,}원"})
        prev_mem = mem
    chain_rows.append({"계층": "별도 · GDB 그린밸리 디럭스 더블 → GDF 패밀리",
                       "최소 간격": f"{NEW_LADDER_GAP_GV['GDF']:,}원",
                       "같은 칸 실제 간격": "—"})
    ladder_df = pd.DataFrame(chain_rows)
    trig_df = pd.DataFrame([
        {"하급 객실 상태": f"잔여 {NEW_LADDER_DROP_N}실 이하 또는 잔여율 "
                      f"{NEW_LADDER_DROP_PCT*100:.0f}% 이하",
         "계단": "제외 — 상급을 끌어올리지 않음",
         "이유": "잠식당할 재고가 없으니 상급을 싸게 둬도 손실이 없습니다"},
        {"하급 객실 상태": f"잔여 {NEW_LADDER_SHRINK_N}실 이하 또는 잔여율 "
                      f"{NEW_LADDER_SHRINK_PCT*100:.0f}% 이하",
         "계단": f"최소 간격 x {NEW_LADDER_SHRINK:.2f}",
         "이유": "지킬 재고가 얼마 없어 간격을 좁힙니다"},
        {"하급 객실 상태": "그 외 (팔 재고 충분)", "계단": "최소 간격 전액",
         "이유": "상급을 싸게 두면 하급이 죽습니다"},
        {"하급 객실 상태": "수동 예외로 고정된 셀", "계단": "적용 안 함",
         "이유": "사람이 정한 값을 계단이 덮지 않습니다"},
    ])
    c3, c4 = st.columns([3, 4])
    with c3:
        st.markdown("**가격 계층과 최소 간격**")
        st.dataframe(ladder_df, use_container_width=True, hide_index=True)
    with c4:
        st.markdown("**발동 기준 (하급 객실 상태 기준)**")
        st.dataframe(trig_df, use_container_width=True, hide_index=True)
    st.caption("화면·엑셀에서 계단으로 올라간 셀은 \u21e7 로 표시되고 '근거' 열에 "
               "'역전방지 계단 N칸'이 들어갑니다.")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        step_df.to_excel(w, index=False, sheet_name="연휴·페이스·재고")
        floor_df.to_excel(w, index=False, sheet_name="Floor")
        type_df_r.to_excel(w, index=False, sheet_name="객실타입 조정")
        ladder_df.to_excel(w, index=False, sheet_name="역전방지 계단")
        trig_df.to_excel(w, index=False, sheet_name="계단 발동 기준")
    st.download_button("📥 규칙표 엑셀", data=buf.getvalue(),
                       file_name=f"신요금로직_규칙표_{date.today().strftime('%Y%m%d')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key="dl_rc2")


# =============================================================================
# 14. 탭 3 — 일자별 칸 (가로: 행 = 단계 · 열 = 날짜)
# =============================================================================
_STEP_ROWS = [
    ("1 앵커", 'anchor_lab'),
    ("2 연휴 반영", '_afterhol'),
    ("3 페이스", '_pace'),
    ("4 재고", '_inv'),
    ("소계 (floor 전)", 'pre_lab'),
    ("5 이벤트 floor", 'ev_floor'),
    ("6 희소 floor", 'sc_floor'),
]


def _step_val(r, field):
    if field == '_afterhol':
        return new_lab(int(r['after_hol']))
    if field == '_pace':
        v = int(r['pace_adj'])
        return "—" if v == 0 else (f"▲{-v}" if v < 0 else f"▼{v}")
    if field == '_inv':
        v = int(r['inv_adj'])
        return "—" if v == 0 else f"▲{-v}"
    return str(r[field] or "—")


def _new_tab_days(day_df):
    if day_df is None or day_df.empty:
        st.info("리포트를 업로드하세요.")
        return
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
    dates, _, _ = _mx_controls(day_df, "new_days")
    if not dates:
        st.warning("표시할 날짜가 없습니다. 위에서 월을 고르거나 '과거 포함'을 켜세요.")
        return
    dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')

    st.markdown(_mx_title("일자별 확정 칸 — 행 = 단계 · 열 = 날짜", True),
                unsafe_allow_html=True)
    st.markdown(_legend("<b>▲</b> 비싼 칸으로 <b>▼</b> 싼 칸으로"),
                unsafe_allow_html=True)
    head = _mx_head(dates, dmap, "단계")
    rows, xrows = [], []

    def add(label, cells, xcells, gend=False, sub=""):
        rows.append(f"<tr class='{'gend' if gend else ''}'><td class='rh'>{label}"
                    + (f"<em>{sub}</em>" if sub else "") + "</td>"
                    + "".join(cells) + "</tr>")
        xrows.append({'label': label, 'sub': sub, 'group_end': gend,
                      'cells': xcells})

    cs, xs = [], []
    for i, d in enumerate(dates):
        hol = str(dmap.loc[d, 'hol'] or "")
        stl = "color:#B5602C;font-weight:700" if hol else ""
        cs.append(f"<td class='mut{_wkcls(dates, i)}' style='font-size:9px;{stl}'>"
                  f"{hol[:7] if hol else '—'}</td>")
        xs.append({'t': hol or "—", 'bold': bool(hol),
                   'fg': '#B5602C' if hol else '#8A929A'})
    add("연휴", cs, xs)

    cs = [f"<td class='mut{_wkcls(dates, i)}'>D-{int(dmap.loc[d,'dta'])}</td>"
          for i, d in enumerate(dates)]
    xs = [{'t': f"D-{int(dmap.loc[d,'dta'])}", 'bold': False, 'fg': '#8A929A'}
          for d in dates]
    add("리드타임", cs, xs, gend=True)

    for label, field in _STEP_ROWS:
        cs, xs = [], []
        for i, d in enumerate(dates):
            v = _step_val(dmap.loc[d], field)
            cs.append(f"<td class='mut{_wkcls(dates, i)}'>{v}</td>")
            xs.append({'t': v, 'bold': False, 'fg': '#5A636B'})
        add(label, cs, xs, gend=(field == 'sc_floor'))

    cs, xs = [], []
    for i, d in enumerate(dates):
        r = dmap.loc[d]
        bg, fg = new_color(int(r['rung']))
        mark = " ✋" if bool(r['is_override']) else ""
        cs.append(f"<td class='rgbig{_wkcls(dates, i)}' "
                  f"style='background:{bg};color:{fg}'>{r['lab']}{mark}</td>")
        xs.append({'t': f"{r['lab']}{mark}", 'bg': bg, 'fg': fg})
    add("확정 칸", cs, xs)

    for label, field in [("HDT 로드가", 'hdt_load'), ("HDT 회원가", 'hdt_member')]:
        cs, xs = [], []
        for i, d in enumerate(dates):
            v = _won(dmap.loc[d, field])
            b = "font-weight:700" if field == 'hdt_member' else ""
            cs.append(f"<td class='{_wkcls(dates, i).strip()}' style='{b}'>{v}</td>")
            xs.append({'t': v, 'bold': field == 'hdt_member'})
        add(label, cs, xs, gend=(field == 'hdt_member'))

    for label, fn in [("총점유", lambda r: '-' if r['occ'] != r['occ'] else '%.0f%%' % r['occ']),
                      ("총잔여율", lambda r: _pct(_num(r['remh']), 0)),
                      ("잔여(실)", lambda r: _won(r['tot_avail']))]:
        cs, xs = [], []
        for i, d in enumerate(dates):
            v = fn(dmap.loc[d])
            cs.append(f"<td class='mut{_wkcls(dates, i)}'>{v}</td>")
            xs.append({'t': v, 'bold': False, 'fg': '#8A929A'})
        add(label, cs, xs)

    st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption("확정 칸이 '소계'보다 비싸면 floor 가 구속한 것입니다. "
               "굵은 세로선은 주 구분(월요일), 주황 머리는 연휴입니다.")

    _dl("📥 이 표 엑셀 (서식 유지)",
        [{'sheet': '일자별 칸', 'title': "일자별 확정 칸 — 행 = 단계 · 열 = 날짜",
          'firstcol': '단계',
          'head1': [d.strftime('%m-%d') for d in dates],
          'head2': [WD_KR[d.weekday()] for d in dates],
          'headc': ['#FBEADB' if str(dmap.loc[d, 'hol'] or "") else '#F3F5F7'
                    for d in dates],
          'rows': xrows, 'cw': 10, 'wide': 18,
          'note': "▲ 비싼 칸으로 / ▼ 싼 칸으로. 확정 칸이 소계보다 비싸면 floor 가 구속."}],
        "일자별칸", "dl_days")

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
        b = io.BytesIO()
        with pd.ExcelWriter(b, engine='openpyxl') as w:
            t.to_excel(w, index=False, sheet_name="일자별 상세")
        st.download_button("📥 세로 상세 엑셀", data=b.getvalue(),
                           file_name=f"일자별상세_{date.today().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_days_detail")


# =============================================================================
# 15. 탭 4 — 타입별 칸 · 요금 (가로: 행 = 객실 · 열 = 날짜)
# =============================================================================
_CELL_MODES = ["칸 크게", "칸 + 회원가", "회원 노출가", "로드(BAR)가",
               "해외 랙", "Flex 하한", "NRF 하한"]
_CELL_FIELD = {"회원 노출가": 'member', "로드(BAR)가": 'load', "해외 랙": 'rack',
               "Flex 하한": 'floor_flex', "NRF 하한": 'floor_nrf'}


def _new_tab_types(day_df, type_df):
    if type_df is None or type_df.empty:
        st.info("리포트를 업로드하세요.")
        return
    st.markdown(NEW_MX_CSS, unsafe_allow_html=True)
    dates, mode, rooms = _mx_controls(day_df, "new_mtx", _CELL_MODES, 0)
    if not dates or not rooms:
        st.warning("표시할 날짜 또는 객실이 없습니다.")
        return

    field = _CELL_FIELD.get(mode)
    order = [r for r in NEW_ROW_ORDER if r in rooms]
    dmap = day_df.drop_duplicates(subset=['date'], keep='first').set_index('date')
    tix = type_df.drop_duplicates(subset=['date', 'rt'], keep='first')
    tix = tix.set_index(['date', 'rt'])

    st.markdown(_mx_title(f"객실타입별 확정 칸 · {mode} — 행 = 객실 · 열 = 날짜", True),
                unsafe_allow_html=True)
    st.markdown(_legend("<b>⇧</b> 역전방지 계단으로 상향"), unsafe_allow_html=True)
    head = _mx_head(dates, dmap, "객실")
    rows, xrows = [], []

    cs, xs = [], []
    for i, d in enumerate(dates):
        r = dmap.loc[d]
        bg, fg = new_color(int(r['rung']))
        cs.append(f"<td class='c3 big{_wkcls(dates, i)}' "
                  f"style='background:{bg};color:{fg}'>{r['lab']}"
                  f"<em>{_won(r['hdt_member'])}</em></td>")
        xs.append({'t': r['lab'], 's': _won(r['hdt_member']), 'bg': bg, 'fg': fg})
    rows.append("<tr class='gend'><td class='rh'>날짜 칸 (기준)"
                "<em>HDT 회원가</em></td>" + "".join(cs) + "</tr>")
    xrows.append({'label': '날짜 칸 (기준)', 'sub': 'HDT 회원가',
                  'group_end': True, 'cells': xs})

    for rt in order:
        gend = rt in NEW_GROUP_END
        cs, xs = [], []
        for i, d in enumerate(dates):
            wk = _wkcls(dates, i)
            key = (d, rt)
            if key not in tix.index:
                cs.append(f"<td class='mut{wk}'>—</td>")
                xs.append({'t': "—", 'bold': False})
                continue
            row = tix.loc[key]
            bg, fg = new_color(int(row['rung']))
            if bool(row['stop']):
                # ※ 마감이어도 요금을 지우지 않습니다. 채널에 로드된 값은 실재하고,
                #   취소가 나면 그 요금으로 다시 열립니다. 사선 + 배지로만 구분.
                cs.append(f"<td class='off c3{wk}'>{_won(row['member'])}"
                          f"<em>{row['lab']} · {row['state']}</em>"
                          f"<i>{_won(row['avail'])}실</i></td>")
                xs.append({'t': _won(row['member']),
                           's': f"{row['lab']} · {row['state']}",
                           's2': f"{_won(row['avail'])}실",
                           'bg': '#EFF1F2', 'fg': '#7B8288', 'bold': False})
                continue
            mark = "✋" if bool(row['is_override']) else ("★" if row['approval'] else "")
            if int(row.get('ladder_up', 0) or 0):
                mark += "⇧"
            if mode == "칸 크게":
                t1, t2, t3 = f"{row['lab']}{mark}", _won(row['member']), ""
                kls = "c3 big"
            elif mode == "칸 + 회원가":
                t1, t2, t3 = f"{row['lab']}{mark}", _won(row['member']), \
                    f"{_won(row['avail'])}실"
                kls = "c3 big"
            else:
                t1, t2, t3 = _won(row[field]), f"{row['lab']}{mark}", \
                    f"{_won(row['avail'])}실"
                kls = "c3 rgsub"
            cs.append(f"<td class='{kls}{wk}' style='background:{bg};color:{fg};"
                      f"font-weight:700'>{t1}<em>{t2}</em>"
                      + (f"<i style='color:{fg}'>{t3}</i>" if t3 else "") + "</td>")
            xs.append({'t': t1, 's': t2, 's2': t3, 'bg': bg, 'fg': fg})
        rows.append(f"<tr class='{'gend' if gend else ''}'><td class='rh'>{rt}"
                    f"<em>{NEW_ROOM_NAMES.get(rt,'')}</em></td>"
                    + "".join(cs) + "</tr>")
        xrows.append({'label': rt, 'sub': NEW_ROOM_NAMES.get(rt, ''),
                      'group_end': gend, 'cells': xs})

    st.markdown("<div class='mxwrap'><table class='mx'>" + head + "<tbody>"
                + "".join(rows) + "</tbody></table></div>", unsafe_allow_html=True)
    st.caption("**색은 칸의 절대 위치입니다** — 비쌀수록 진한 빨강, 쌀수록 연한 초록. "
               "사선 셀은 잔여 0 이하 — 요금 조정이 아니라 판매를 닫아야 합니다 "
        "(요금은 회원 노출가로 계속 표시됩니다). "
               "굵은 세로선은 주 구분입니다. **⇧ 는 역전방지 계단으로 칸이 올라간 셀**입니다 — "
               "하급 객실보다 싸지지 않게 강제한 것이고, 하급에 팔 재고가 거의 없으면 "
               "계단을 걸지 않습니다. 이전 대비 변화는 2번 탭에서 보십시오.")

    _dl(f"📥 이 표 엑셀 (서식 유지) — {mode}",
        [{'sheet': '타입별 칸', 'title': f"객실타입별 확정 칸 · {mode}",
          'firstcol': '객실',
          'head1': [d.strftime('%m-%d') for d in dates],
          'head2': [WD_KR[d.weekday()] for d in dates],
          'headc': ['#FBEADB' if str(dmap.loc[d, 'hol'] or "") else '#F3F5F7'
                    for d in dates],
          'rows': xrows, 'cw': 11,
          'note': "색 = 칸의 절대 위치. 회색 사선 셀은 잔여 0 이하(판매 마감)."}],
        "타입별칸", "dl_types")

    st.divider()
    st.markdown("##### 날짜 하나 골라 보는 판매 시트")
    tgt = st.selectbox("날짜", dates,
                       format_func=lambda x: f"{x.strftime('%Y-%m-%d')} ({WD_KR[x.weekday()]})",
                       key="new_sheet_date")
    one = type_df[(type_df['date'] == tgt) & (type_df['rt'].astype(str).isin(rooms))].copy()
    if one.empty:
        return
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
        "칸": one['lab'], "타입조정": one['tadj'], "계단": one['ladder_up'],
        "로드(BAR)": one['load'], "회원 노출가": one['member'],
        "해외 랙": one['rack'], "Flex 하한": one['floor_flex'],
        "NRF 하한": one['floor_nrf'],
        "상태": one['state'], "승인": one['approval'].replace("", "—"),
        "근거": one['why'].replace("", "—"),
    })
    st.dataframe(sheet, use_container_width=True, hide_index=True)
    _dl("📥 이 날짜 판매 시트 엑셀 (서식 유지)",
        [{'sheet': tgt.strftime('%m-%d'),
          'title': f"{tgt.strftime('%Y-%m-%d')} ({WD_KR[tgt.weekday()]}) 판매 시트 · "
                   f"날짜 칸 {info['lab']}",
          'firstcol': '객실', 'head1': list(sheet.columns[1:]), 'head2': None,
          'headc': ['#F3F5F7'] * (len(sheet.columns) - 1),
          'rows': [{'label': r['객실'],
                    'cells': [{'t': ("" if pd.isna(r[c]) else
                                     (_won(r[c]) if isinstance(r[c], (int, float))
                                      else str(r[c]))),
                               'bold': c == '칸',
                               'bg': (new_color(new_idx(r['칸']) or 16)[0]
                                      if c == '칸' else None),
                               'fg': (new_color(new_idx(r['칸']) or 16)[1]
                                      if c == '칸' else '#16202B')}
                              for c in sheet.columns[1:]]}
                   for _, r in sheet.iterrows()],
          'cw': 13, 'wide': 10}],
        f"판매시트_{tgt.strftime('%m%d')}", "dl_sheet")


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
def _new_tab_override(day_df, type_df, db, today, auto_now=None, review_df=None):
    st.markdown("""
<div class="renote warn"><b>여기서 만든 예외는 신 로직 전용 저장소에만 들어갑니다.</b>
메인 페이지(기존 로직)의 '예외 설정'(applied_rates)과 완전히 분리돼 있어, 어느 쪽을 고쳐도
다른 쪽 요금은 바뀌지 않습니다. 칸 라벨은 <code>B0pp B0p B0 B1 ... B13</code> 형식입니다.<br><br>
<b>새 파일을 올려도 예외는 그대로 유지됩니다.</b> 재고가 바뀌어 자동 계산이 다른 칸을
가리켜도 예외가 그 위를 덮습니다 — 해제할 때까지 그 날짜는 자동으로 안 움직입니다.
그래서 자동 계산값이 달라지면 아래 <b>재검토</b> 표에 올려 알려드립니다.</div>
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
                ok, msg = new_save_override(db, ds, rooms, memo, auto_now)
                (st.success if ok else st.error)(f"{ds} — {msg}")
            st.rerun()
    with b2:
        if st.button("🗑️ 이 날짜 예외 해제", use_container_width=True, key="new_ov_del"):
            ok, msg = new_delete_override(db, ds)
            (st.success if ok else st.error)(f"{ds} — {msg}")
            st.rerun()

    st.divider()
    if review_df is not None and not review_df.empty:
        st.markdown(
            f"<div class='renote stop'><b>⚠️ 재검토 필요 {len(review_df)}건</b> — "
            f"예외를 걸었을 때의 자동 계산값이 그 뒤에 바뀌었습니다. 예외는 그대로 "
            f"유지되고 있으니, 아직 그 칸이 맞는지 확인하거나 예외를 해제하십시오.</div>",
            unsafe_allow_html=True)
        st.dataframe(review_df, use_container_width=True, hide_index=True)
        st.caption("'차이'가 양수면 지금 자동 계산이 더 비싼 칸을 가리킵니다 "
                   "(= 예외 때문에 싸게 팔고 있을 수 있음). 음수면 그 반대입니다.")
        st.divider()

    st.markdown("##### 현재 활성 예외 (신 로직)")
    if not raw:
        st.info("설정된 예외가 없습니다.")
    else:
        recs = []
        for k in sorted(raw):
            info2 = raw[k] or {}
            rooms = info2.get('rooms') or {}
            rec2 = info2.get('rec_at_apply') or {}
            recs.append({
                "날짜": k,
                "고정 칸": ", ".join(f"{a}={b}" for a, b in sorted(rooms.items())),
                "걸었을 때 자동값": ", ".join(f"{a}={b}" for a, b in sorted(rec2.items())) or "—",
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
                   'day_lab', 'tadj', 'ladder_up', 'lab', 'load', 'member', 'rack',
                   'floor_flex', 'floor_nrf', 'state', 'approval', 'why']]
            t.columns = ['일자', '요일', 'D-', '객실', '객실명', '전체', '잔여', '잔여율',
                         '날짜 칸', '타입 조정', '계단', '확정 칸', '로드(BAR)',
                         '회원 노출가', '해외 랙', 'Flex 하한', 'NRF 하한',
                         '상태', '승인', '근거']
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

    ov_raw = new_load_overrides(db)
    ov = new_override_map(ov_raw)
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

    # ── 예외 재검토 — 예외를 걸지 않았을 때의 자동 계산과 대조 ──────
    auto_now, review_df = {}, pd.DataFrame()
    try:
        if ov:
            # 예외를 뺀 계산을 한 번 더 돌려 '자동값'을 구합니다.
            day_raw = new_compute_days(curr_df, prev_df, today=today, overrides=None)
            type_raw = new_compute_types(curr_df, day_raw, today=today, overrides=None)
            auto_now = new_auto_labels(day_raw, type_raw)
            review_df = new_review_overrides(ov_raw, auto_now)
        else:
            # 예외가 없으면 지금 계산이 곧 자동값입니다 (추가 계산 불필요).
            auto_now = new_auto_labels(day_df, type_df)
    except Exception as e:
        st.warning(f"예외 재검토 판정 실패 — 나머지는 정상입니다. ({e})")

    n_ov = len(ov)
    if n_ov:
        msg = f"✋ 예외 {n_ov}일이 적용된 상태입니다. (9번 탭에서 관리)"
        if not review_df.empty:
            st.warning(f"{msg}  ·  ⚠️ 그중 **재검토 필요 {len(review_df)}건** — "
                       f"예외를 걸었을 때의 자동 계산값이 바뀌었습니다. (9번 탭)")
        else:
            st.info(msg)

    chg_label = "📈 이전 대비 변화"
    if chg and chg.get('moved_days'):
        chg_label = f"📈 이전 대비 변화 ({chg['moved_days']})"
    tabs = st.tabs([
        "📐 규칙 & 요약", chg_label, "📅 일자별 칸", "🛏️ 타입별 칸 · 요금",
        "📒 최종 요금", "📋 요금표", "🛡️ Floor & 재심사", "🏷️ 할인 레이어 · 채널가",
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
        _safe(_new_tab_final, day_df, type_df, ov_raw)
    with tabs[5]:
        _safe(_new_tab_ratecard)
    with tabs[6]:
        _safe(_new_tab_floor, day_df)
    with tabs[7]:
        _safe(_new_tab_promo, type_df, promotions, channel_list)
    with tabs[8]:
        _safe(_new_tab_override, day_df, type_df, db, today, auto_now, review_df)
    with tabs[9]:
        _safe(_new_tab_download, day_df, type_df, day_cmp, type_cmp)
