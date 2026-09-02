import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import math
import re
import io
import hashlib
import json

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
BAR_GRADIENT_COLORS = {
    "BAR0P": "#7B0000",  # BAR0보다 진한 최고가
    "BAR0": "#B71C1C",
    "BAR1": "#D32F2F", "BAR2": "#EF5350", "BAR3": "#FF8A65", "BAR4": "#FFB199",
    "BAR5": "#81C784", "BAR6": "#A5D6A7", "BAR7": "#C8E6C9", "BAR8": "#E8F5E9",
}
BAR_LIGHT_COLORS = {
    "BAR0P": "#EF9A9A",
    "BAR0": "#FFCDD2",
    "BAR1": "#FFEBEE", "BAR2": "#FFEBEE", "BAR3": "#FFF3E0", "BAR4": "#FFF3E0",
    "BAR5": "#E8F5E9", "BAR6": "#E8F5E9", "BAR7": "#F1F8E9", "BAR8": "#F1F8E9",
}
# BAR 고가→저가 순서 (인덱스 낮을수록 비쌈)
BAR_ORDER = ["BAR0P", "BAR0", "BAR1", "BAR2", "BAR3", "BAR4", "BAR5", "BAR6", "BAR7", "BAR8"]
WEEKDAYS_KR = ['월', '화', '수', '목', '금', '토', '일']
DYNAMIC_ROOMS = ["FDB", "FDE", "HDP", "HDT", "HDF"]
FIXED_ROOMS = ["GDB", "GDF", "FFD", "FPT", "PPV"]
ALL_ROOMS = DYNAMIC_ROOMS + FIXED_ROOMS

PRICE_TABLE = {
    "FDB": {"BAR0P": 894000, "BAR0": 805000, "BAR1": 721000, "BAR2": 642000, "BAR3": 567000, "BAR4": 502000, "BAR5": 445000, "BAR6": 396000, "BAR7": 353000, "BAR8": 315000},
    "FDE": {"BAR0P": 931000, "BAR0": 842000, "BAR1": 758000, "BAR2": 679000, "BAR3": 604000, "BAR4": 539000, "BAR5": 482000, "BAR6": 433000, "BAR7": 390000, "BAR8": 352000},
    "HDP": {"BAR0P": 859000, "BAR0": 770000, "BAR1": 686000, "BAR2": 607000, "BAR3": 532000, "BAR4": 467000, "BAR5": 410000, "BAR6": 361000, "BAR7": 318000, "BAR8": 280000},
    "HDT": {"BAR0P": 829000, "BAR0": 740000, "BAR1": 656000, "BAR2": 577000, "BAR3": 502000, "BAR4": 437000, "BAR5": 380000, "BAR6": 331000, "BAR7": 288000, "BAR8": 250000},
    "HDF": {"BAR0P": 999000, "BAR0": 910000, "BAR1": 826000, "BAR2": 747000, "BAR3": 672000, "BAR4": 607000, "BAR5": 550000, "BAR6": 501000, "BAR7": 458000, "BAR8": 420000},
}
# FPT 펫룸 독립 BAR 요금표 (호텔 전체 OCC 기준, 500,000~900,000)
FPT_TABLE = {
    "BAR0P": 950000, "BAR0": 900000, "BAR1": 850000, "BAR2": 800000, "BAR3": 750000,
    "BAR4": 700000, "BAR5": 650000, "BAR6": 600000, "BAR7": 550000, "BAR8": 500000,
}
# PPV 풀빌라 럭셔리 독립 BAR 요금표 (FDB 연동, 1,290,000~2,790,000)
PPV_TABLE = {
    "BAR0P": 2790000, "BAR0": 2490000, "BAR1": 2340000, "BAR2": 2190000, "BAR3": 2040000,
    "BAR4": 1890000, "BAR5": 1740000, "BAR6": 1590000, "BAR7": 1440000, "BAR8": 1290000,
}
# GDB 그린밸리 더블 독립 BAR 요금표 (자체 OCC 기준, 298,000~718,000)
GDB_TABLE = {
    "BAR0P": 718000, "BAR0": 658000, "BAR1": 598000, "BAR2": 538000, "BAR3": 478000,
    "BAR4": 418000, "BAR5": 358000, "BAR6": 298000, "BAR7": 298000, "BAR8": 298000,
}
# GDF 그린밸리 패밀리 독립 BAR 요금표 (자체 OCC 기준, 390,000~969,000)
GDF_TABLE = {
    "BAR0P": 969000, "BAR0": 880000, "BAR1": 796000, "BAR2": 717000, "BAR3": 642000,
    "BAR4": 577000, "BAR5": 520000, "BAR6": 471000, "BAR7": 428000, "BAR8": 390000,
}
# FFD 포레스트 패밀리 더블 BAR 요금표 (FDE+20k 플로어 스냅업, 372,000~951,000)
FFD_TABLE = {
    "BAR0P": 951000, "BAR0": 862000, "BAR1": 778000, "BAR2": 699000, "BAR3": 624000,
    "BAR4": 559000, "BAR5": 502000, "BAR6": 453000, "BAR7": 410000, "BAR8": 372000,
}
# 하위 호환용 (구 스냅샷 읽기 등에 사용될 수 있음, 신규 산출에는 미사용)
FIXED_PRICE_TABLE = {
    "GDB": {"UND1": 298000, "UND2": 298000, "MID1": 298000, "MID2": 298000, "UPP1": 298000, "UPP2": 298000},
    "GDF": {"UND1": 375000, "UND2": 410000, "MID1": 410000, "MID2": 488000, "UPP1": 488000, "UPP2": 578000},
    "FFD": {"UND1": 353000, "UND2": 393000, "MID1": 433000, "MID2": 482000, "UPP1": 539000, "UPP2": 604000},
    "FPT": {"UND1": 500000, "UND2": 550000, "MID1": 600000, "MID2": 650000, "UPP1": 700000, "UPP2": 750000},
    "PPV": {"UND1": 1104000, "UND2": 1154000, "MID1": 1154000, "MID2": 1304000, "UPP1": 1304000, "UPP2": 1554000},
}

TODAY = date.today()

# 객실별 요금 상한 (희소성 프리미엄 가산 후 클램프) — 한 곳에서만 관리
# ⚠️ 상한이 요금표 BAR0P보다 낮으면 그 BAR는 도달 불가 구간이 됩니다.
#    validate_price_tables()가 시작 시 자동 점검합니다.
ROOM_PRICE_CAPS = {
    "GDB": 678000,    # 요금표 BAR0P = 718,000
    "GDF": 878000,    # 요금표 BAR0P = 969,000
    "FPT": 900000,    # 요금표 BAR0P = 950,000
    "PPV": 2490000,   # 요금표 BAR0P = 2,790,000
}

# 객실ID → 요금표 매핑 (여러 함수에 흩어져 있던 if/elif 체인 통합)
def get_room_table(room_id):
    if room_id in DYNAMIC_ROOMS:
        return PRICE_TABLE.get(room_id, {})
    return {"FPT": FPT_TABLE, "PPV": PPV_TABLE, "GDB": GDB_TABLE,
            "GDF": GDF_TABLE, "FFD": FFD_TABLE}.get(room_id, {})


def _bar_move_mark(from_bar, to_bar):
    """BAR 이동 방향 → (화살표, 색). 인덱스가 작을수록 고가."""
    a, b = bar_rank(from_bar), bar_rank(to_bar)
    if a is None or b is None or a == b:
        return "→", "#888"
    return ("▲", "#c62828") if b < a else ("▼", "#1565C0")


def bar_rank(bar):
    """BAR 코드 → BAR_ORDER 인덱스 (0=최고가). 알 수 없으면 None."""
    try:
        return BAR_ORDER.index(str(bar).strip().upper())
    except (ValueError, AttributeError):
        return None


def is_valid_bar(bar):
    return bar_rank(bar) is not None


# --- 데이터 품질 이슈 수집 (리런 단위, 화면 경고용) ---
_data_issues = {}   # {(date_str, rid): "사유"}
_logic_errors = []  # 예외를 삼키지 않고 여기에 기록


def _record_issue(date_str, rid, reason):
    _data_issues[(date_str, rid)] = reason


def normalize_inventory(av_raw, tot_raw, date_str, rid, fallback_occ=None):
    """잔여/전체 객실을 검증·정규화하고 OCC를 반환.

    반환: (occ, avail_effective, total_effective, ok)
    - Total 결측/0, Available 결측 → OCC 계산 불가 → fallback_occ(호텔 OCC) 사용, 이슈 기록
    - Available > Total → Total로 클램프, 이슈 기록
    ※ 기존 코드는 결측을 조용히 0으로 바꿔 '매진(최고가)' 또는 '공실(최저가)'로
      단정해 오요금을 만들었습니다. 여기서는 단정하지 않고 호텔 OCC로 대체 + 경고합니다.
    """
    try:
        tot = float(tot_raw) if pd.notna(tot_raw) else float('nan')
    except (TypeError, ValueError):
        tot = float('nan')
    try:
        av = float(av_raw) if pd.notna(av_raw) else float('nan')
    except (TypeError, ValueError):
        av = float('nan')

    if not (tot == tot) or tot <= 0:          # NaN 또는 0 이하
        _record_issue(date_str, rid, f"전체객실 값 이상({tot_raw!r}) → 호텔 OCC로 대체")
        return (fallback_occ if fallback_occ is not None else 0.0), av, tot, False
    if not (av == av):                        # Available NaN
        _record_issue(date_str, rid, "잔여객실 결측 → 호텔 OCC로 대체")
        return (fallback_occ if fallback_occ is not None else 0.0), av, tot, False
    if av < 0:
        _record_issue(date_str, rid, f"잔여객실 음수({av:g}) → 0으로 처리")
        av = 0.0
    if av > tot:
        _record_issue(date_str, rid, f"잔여({av:g}) > 전체({tot:g}) → 전체로 클램프")
        av = tot
    return ((tot - av) / tot * 100), av, tot, True


def validate_inventory_df(df):
    """업로드 직후 재고 데이터 무결성 점검. 반환: list of (date, rid, 사유)"""
    if df is None or df.empty:
        return []
    bad = []
    for _, r in df.iterrows():
        rid, d = r.get('RoomID'), r.get('Date')
        tot, av = r.get('Total'), r.get('Available')
        try:
            tot_f = float(tot) if pd.notna(tot) else float('nan')
        except (TypeError, ValueError):
            tot_f = float('nan')
        try:
            av_f = float(av) if pd.notna(av) else float('nan')
        except (TypeError, ValueError):
            av_f = float('nan')
        if not (tot_f == tot_f) or tot_f <= 0:
            bad.append((d, rid, f"전체객실 결측/0 ({tot!r})"))
        elif not (av_f == av_f):
            bad.append((d, rid, "잔여객실 결측"))
        elif av_f > tot_f:
            bad.append((d, rid, f"잔여({av_f:g}) > 전체({tot_f:g})"))
        elif av_f < 0:
            bad.append((d, rid, f"잔여객실 음수 ({av_f:g})"))
    return bad


# Firebase 컬렉션 이름 (스네이크케이스)
COL_SNAPSHOTS = "daily_snapshots"
COL_APPLIED = "applied_rates"
COL_SETTINGS = "settings"
COL_AUDIT = "audit_log"
COL_RESTORE = "restore_points"


# =============================================================================
# 3. 로직 함수
# =============================================================================
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


def get_start_bar(date_obj):
    """날짜 기반 시작 BAR 반환 (해당 날 OCC 최저일 때의 BAR).
    BAR_ORDER에서 인덱스 높을수록 저렴. 시작 BAR = OCC 0% 때의 BAR."""
    m, d = date_obj.month, date_obj.day
    md = f"{m:02d}.{d:02d}"
    actual_is_weekend = date_obj.weekday() in [4, 5]

    # ── 9~10월 연휴: BAR1 시작 ──
    # ※ 9/28은 공휴일이 아닌 일반 월요일이라 연휴에서 제외 (9~10월 기본 적용).
    if (("09.24" <= md <= "09.26") or
        ("10.01" <= md <= "10.10")):
        return "BAR1"

    # ── 추석 연휴 마지막날 9/27(일): 한 단계 하향 ──
    # 연휴 끝자락이라 수요가 약해지는 구간. BAR1 → BAR2.
    # 되돌리려면 이 블록을 지우고 위 범위를 "09.27"까지로 넓히면 됩니다.
    if md == "09.27":
        return "BAR2"

    # ── 최성수기: BAR2 시작 (주중/주말 동일) ──
    if (("07.25" <= md <= "08.08") or
        ("08.14" <= md <= "08.16") or
        ("12.24" <= md <= "12.26") or
        md == "12.31"):
        return "BAR2"

    # ── 준성수기: BAR3 시작 ──
    if "08.09" <= md <= "08.13":
        return "BAR3"

    # ── 여름 성수기 (7/17~8/29) 나머지: 주중 BAR5, 주말 BAR4 ──
    if "07.17" <= md <= "08.29":
        return "BAR4" if actual_is_weekend else "BAR5"

    # ── 12월 연말 (21~30 중 24~26·31 제외): BAR5 시작 (주중/주말 동일) ──
    # ※ 기존 BAR4 고정 → BAR5 고정으로 한 단계 하향.
    if "12.21" <= md <= "12.30":
        return "BAR5"

    # ── 9~10월 (연휴 제외): 주중 BAR5, 주말 BAR4 ──
    if "09.01" <= md <= "10.31":
        return "BAR4" if actual_is_weekend else "BAR5"

    # ── 11월~12월20일: 주중 BAR7, 주말 BAR6 ──
    if "11.01" <= md <= "12.20":
        return "BAR6" if actual_is_weekend else "BAR7"

    # ── 나머지 날짜 (1~6월, 7월 1~16일): 기존 시즌 로직으로 매핑 ──
    _, season, is_weekend_ovr = get_season_details(date_obj)
    # is_weekend_ovr 포함 (설날·추석 등 휴일 평일→주말 오버라이드 반영)
    return {
        ("UPP", True):  "BAR4", ("UPP", False):  "BAR5",
        ("MID", True):  "BAR6", ("MID", False):  "BAR7",
        ("UND", True):  "BAR7", ("UND", False):  "BAR8",
    }.get((season, is_weekend_ovr), "BAR8")


# =============================================================================
# 3-V2. 요금 곡선 설정 (2단계) — 이 블록의 숫자만 만지면 곡선이 바뀝니다
# =============================================================================
# 요금 로직 버전. False로 두면 기존(1단계) 곡선으로 그대로 돌아갑니다.
# 하단 "구/신 요금 비교" 패널이 이 값을 일시적으로 바꿔가며 두 결과를 대조합니다.
_PRICING_V2 = True

# ── OCC 구간별 인상 단계 ─────────────────────────────────────────────
# (기존) 31%/51%/81% → 1/2/3단계, 최대 3단계에서 캡
#   → 비수기 시작BAR8에서 100% 매진해도 BAR5(최고가의 50%)에서 멈췄습니다.
# (신규) 임계값을 30/50/70/85/90/95로 정정·확장하고 최대 6단계까지 허용.
#   임계값을 31→30으로 내린 이유: 20실 객실은 OCC가 5% 단위로만 움직여
#   '31% 이상'의 실효 임계값이 35%였습니다(80%→85%, 50%→55%도 동일).
OCC_OFFSET_LADDER = [
    (95, 6),
    (90, 5),
    (85, 4),
    (70, 3),
    (50, 2),
    (30, 1),
]
# ※ 시즌 상한(get_bar_ceiling) 도입 후 이 값의 역할이 바뀌었습니다.
#   "얼마나 높이 올라가는가"는 이제 시즌 상한이 정합니다.
#   이 값은 "얼마나 빨리 상한에 도달하는가"(곡선의 기울기)를 조절합니다.
#   값이 작을수록 낮은 OCC에서 빨리 상한에 붙습니다.
# (오늘~180일 × OCC 0~100% 전수 시뮬레이션 / 기존 대비 전체 평균)
#   3 → +3.4%  (가파름 — OCC 50%면 상한 근처)
#   4 → +2.3%
#   5 → +0.7%  ← 기본값
#   6 → -0.6%  (완만 — 거의 매진돼야 상한)
# 하단 "🔬 구/신 요금 곡선 비교" 패널에서 실제 데이터로 확인한 뒤 조정하세요.
OCC_OFFSET_MAX = 5

# ── 잔여 객실 수 기준 희소성 (재고 규모 차이 보정) ──────────────────
# %만 쓰면 재고가 작은 객실이 불리합니다.
#   20실 객실: 잔여 1실 = 95% → 6단계 인상
#    6실 객실: 잔여 1실 = 83% → 4단계에서 멈춤
# 잔여 실수 기준 하한을 같이 적용해 재고 규모와 무관하게 맞춥니다.
# ※ OCC가 SCARCITY_MIN_OCC 미만이면 적용하지 않습니다
#   (4실 중 3실 공실=OCC 25%를 '희소'로 오판하지 않도록)
SCARCITY_BY_AVAIL = {1: 6, 2: 5, 3: 4}
SCARCITY_MIN_OCC = 50

# ── 시즌별 BAR 상한 (도달 가능한 최고 요금) ─────────────────────────
# ※ 이게 없어서 시작BAR가 높은 날짜(9/25, 10/5 = 시작 BAR1)가
#   OCC 50%만 되어도 BAR0P까지 올라갔습니다. 32실 중 16실이 남았는데
#   최고가를 부르는 상태였습니다. 시작점만 있고 천장이 없었던 게 원인입니다.
#
# BAR0P는 "재고가 실제로 부족하다는 증거가 있는 날"에만 쓰는 요금이므로
# 연휴·최성수기로 한정합니다. 그 외 날짜는 아무리 팔려도 아래 상한까지만.
# 상한을 넘겨야 하는 예외 상황은 「예외 설정」이나 「오버라이드」로 수동 지정하세요.

# BAR0P 도달을 허용하는 연휴·최성수기 구간
HOLIDAY_RANGES = [
    ("09.24", "09.27"),   # 추석 연휴
    ("10.01", "10.10"),   # 개천절·한글날 연휴
    ("12.24", "12.26"),   # 크리스마스
    ("12.31", "12.31"),   # 연말
    ("07.25", "08.08"),   # 여름 최성수기   ※ 기본값 — 확인 필요
    ("08.14", "08.16"),   # 광복절 연휴     ※ 기본값 — 확인 필요
]

# 그 외 구간의 상한 (시작MM.DD, 끝MM.DD, 주중상한, 주말상한)
# ※ 주말 = 금·토 (체크인 기준, 기존 로직과 동일)
BAR_CEILING_RULES = [
    ("07.17", "08.29", "BAR1", "BAR0"),   # 여름 성수기 나머지  ※ 기본값
    ("08.09", "08.13", "BAR1", "BAR0"),   # 여름 준성수기       ※ 기본값
    # 12월 연말(21~30, 24~26·31 제외). 시작BAR도 BAR4 → BAR5로 한 단계 내렸습니다.
    # 연말 수요가 실제로 강하면 아래를 ("BAR2","BAR1") 정도로 올리세요.
    ("12.21", "12.30", "BAR3", "BAR2"),
]
# 위 어디에도 안 걸리는 전 기간 (9~10월 평일/주말 포함)
DEFAULT_BAR_CEILING = ("BAR3", "BAR2")

# ── 최상단 BAR 잠금 해제 조건 ────────────────────────────────────────
# 연휴 구간이라도 "달력"만으로 최고가가 나오면 안 됩니다.
# 예: 9/25(추석)는 시작이 BAR1이라 OCC 50%(32실 중 16실 잔여)에도 BAR0P가
#     나왔습니다. 절반이 비었는데 최고가를 부르는 상태입니다.
# BAR0P/BAR0는 "재고가 실제로 부족하다는 근거"가 있을 때만 열립니다.
# (BAR 코드: (필요 OCC%, 또는 이 잔여 실수 이하))
TOP_BAR_GATES = {
    "BAR0P": (85, 3),
    "BAR0":  (70, 5),
}


def apply_top_bar_gate(bar, occ, avail):
    """BAR0P/BAR0는 OCC 또는 잔여 실수 조건을 만족할 때만 허용."""
    if not _PRICING_V2:
        return bar
    idx = BAR_ORDER.index(bar)
    try:
        av = float(avail)
        if av != av:
            av = None
    except (TypeError, ValueError):
        av = None
    while idx < len(BAR_ORDER) - 1:
        gate = TOP_BAR_GATES.get(BAR_ORDER[idx])
        if not gate:
            break
        min_occ, max_av = gate
        if occ >= min_occ or (av is not None and av <= max_av):
            break
        idx += 1                                   # 조건 미달 → 한 단계 아래로
    return BAR_ORDER[idx]


def _in_ranges(md, ranges):
    return any(a <= md <= b for a, b in ranges)


def get_bar_ceiling(date_obj):
    """해당 날짜에 도달 가능한 최고 BAR (인상 상한)."""
    if not _PRICING_V2:
        return BAR_ORDER[0]
    md = f"{date_obj.month:02d}.{date_obj.day:02d}"
    if _in_ranges(md, HOLIDAY_RANGES):
        return BAR_ORDER[0]                       # BAR0P 허용
    is_weekend = date_obj.weekday() in [4, 5]
    for a, b, wd_cap, we_cap in BAR_CEILING_RULES:
        if a <= md <= b:
            return we_cap if is_weekend else wd_cap
    wd_cap, we_cap = DEFAULT_BAR_CEILING
    return we_cap if is_weekend else wd_cap


# ── 픽업(판매 속도) 기반 조정 ────────────────────────────────────────
# OCC는 "지금까지 얼마나 팔렸나"(과거)일 뿐, "남은 재고가 남은 시간 안에
# 팔릴까"(미래)를 말해주지 않습니다. 같은 '잔여 8실'이라도
#   D-60 잔여 8실 → 60일 남았으니 팔린다 → 올려야 함
#   D-1  잔여 8실 → 내일 8실을 팔아야 함 → 올리면 못 팜 → 내려야 함
# 이 둘을 OCC만으로는 구분할 수 없습니다.
#
# 직전 스냅샷(prev_df) 대비 판매 속도로 소진 예상일을 구해,
# 남은 일수와 비교합니다.  ratio = 소진예상일 / 남은일수
SNAPSHOT_INTERVAL_DAYS = 1     # 리포트 업로드 주기(일). 매일 저장하면 1
PICKUP_FLOOR = 0.1             # 픽업 0일 때 쓰는 하한 (10일에 1실)
PICKUP_RULES = [               # (ratio 상한, 조정 단계)
    (0.25, +2),                # 남은 시간의 1/4 만에 소진될 속도 → 수요 초과
    (0.50, +1),
    (2.00,  0),                # 정상 — 조정 없음
    (4.00, -1),                # 남은 시간의 2~4배 필요 → 못 판다
    (10**9, -2),
]
PICKUP_MIN_AVAIL = 1           # 잔여가 이보다 적으면 조정 안 함(매진 등)
DOWN_MAX_STEPS = 2             # 인하(부진+픽업 합산) 상한

# ── 픽업 판단이 유효한 리드타임 ──────────────────────────────────────
# ※ 이 제한이 없으면 예약이 시작되지도 않은 먼 날짜에서 하루치 픽업이
#   요금을 크게 흔듭니다. 실제 사례(12/01, D+90, HDT 34실 중 33실 잔여):
#     어제 대비 0실 판매 → 소진예상 330일 > 90일 → 1단계 인하 → BAR8 250,000
#     어제 대비 1실 판매 → 소진예상  33일 <  90일 → 1단계 인상 → BAR6 331,000
#   1실 차이로 81,000원이 갈렸습니다. D+90에 3% 판매는 정상인데 '부진'으로
#   판정한 것이고, 하루 표본을 90일로 외삽한 것도 무리였습니다.
#
# 픽업은 'OCC 기반 요금에 대한 근거리 보정'으로만 씁니다.
# 먼 날짜의 수요는 OCC 래더가 이미 반영합니다.
PICKUP_LEAD_UP_MAX = 45        # 인상 신호는 D+45 이내에서만 (실제 판매된 증거)
PICKUP_LEAD_DOWN_MAX = 21      # 인하 신호는 D+21 이내에서만
#   ↑ 비대칭 이유: '팔렸다'는 신호는 멀어도 사실이지만,
#     '안 팔렸다'는 신호는 리드타임이 멀면 정상이라 근거가 되지 못합니다.

_pickup_cache = {}


def get_pickup_per_day(date_obj, rid):
    """직전 스냅샷 대비 하루당 판매 실수. 데이터 없으면 None."""
    key = (date_obj, rid)
    if key in _pickup_cache:
        return _pickup_cache[key]
    val = None
    try:
        prev = st.session_state.get('prev_df', pd.DataFrame())
        curr = st.session_state.get('today_df', pd.DataFrame())
        if prev is not None and curr is not None and not prev.empty and not curr.empty:
            p = prev[(prev['RoomID'] == rid) & (prev['Date'] == date_obj)]
            c = curr[(curr['RoomID'] == rid) & (curr['Date'] == date_obj)]
            if not p.empty and not c.empty:
                pa = float(p.iloc[0]['Available']) if pd.notna(p.iloc[0]['Available']) else float('nan')
                ca = float(c.iloc[0]['Available']) if pd.notna(c.iloc[0]['Available']) else float('nan')
                if pa == pa and ca == ca:
                    val = max(0.0, pa - ca) / max(1, SNAPSHOT_INTERVAL_DAYS)
    except Exception as e:
        msg = f"픽업 계산 실패 ({rid} {date_obj}): {type(e).__name__}: {e}"
        if msg not in _logic_errors:
            _logic_errors.append(msg)
        val = None
    _pickup_cache[key] = val
    return val


def pickup_steps(date_obj, avail, pickup_per_day):
    """소진 속도 기반 BAR 조정 단계 (-2 ~ +2).

    ※ 리드타임 제한 필수: 예약이 시작되지도 않은 먼 날짜에서는 하루치 픽업을
      외삽해도 의미가 없습니다 (PICKUP_LEAD_* 주석의 12/01 사례 참고).
    """
    if not _PRICING_V2 or pickup_per_day is None:
        return 0
    days_left = (date_obj - TODAY).days
    if days_left <= 0:
        return 0
    if days_left > max(PICKUP_LEAD_UP_MAX, PICKUP_LEAD_DOWN_MAX):
        return 0
    try:
        av = float(avail)
    except (TypeError, ValueError):
        return 0
    if av != av or av < PICKUP_MIN_AVAIL:
        return 0                                   # 매진 등 — 조정 불필요
    est_days = av / max(pickup_per_day, PICKUP_FLOOR)
    ratio = est_days / days_left
    step = PICKUP_RULES[-1][1]
    for thr, s in PICKUP_RULES:
        if ratio <= thr:
            step = s
            break
    # 리드타임별 유효성 (인상/인하 비대칭)
    if step > 0 and days_left > PICKUP_LEAD_UP_MAX:
        return 0
    if step < 0 and days_left > PICKUP_LEAD_DOWN_MAX:
        return 0
    return step


# ── 판매 부진 시 인하 경로 (신규) ────────────────────────────────────
# 기존에는 OCC가 요금을 올리기만 하고 절대 내리지 못해, 성수기 공실 100%에도
# 시작BAR(예: 9/25 BAR1 = FDB 721,000)이 그대로 유지됐습니다.
# (체크인까지 남은 일수, OCC 상한, 인하 단계)
DISCOUNT_RULES = [
    (14, 20, 2),   # 체크인 14일 이내 + OCC 20% 미만 → 2단계 인하
    (30, 30, 1),   # 체크인 30일 이내 + OCC 30% 미만 → 1단계 인하
]
DISCOUNT_MAX_STEPS = 2          # 시작BAR 대비 최대 인하 단계
# 인하는 요금표 최저 BAR(BAR8)를 하한으로 자동 클램프됩니다.

# ── 역전방지 계단 ────────────────────────────────────────────────────
# 【발동 원칙】 역전방지의 목적은 '카니발라이제이션 방지'입니다.
#   상급 객실이 하급보다 싸면 하급을 사려던 고객이 상급으로 올라갑니다.
#   → 하급 재고가 안 팔리고, 상급을 제값보다 싸게 팔게 됩니다(이중 손실).
#   따라서 발동 기준은 "하급 객실에 잠식당할 재고가 실제로 남아 있는가"입니다.
#   OCC 비교가 아닙니다.
#
#   ① 하급에 팔 재고가 충분     → 간격 전액 (상급을 싸게 두면 하급이 죽음)
#   ② 하급이 매진 임박          → 간격 × LADDER_GAP_SHRINK (지킬 재고가 거의 없음)
#   ③ 하급 매진 (잔여 0)        → 계단에서 제외 (잠식할 재고 없음, 예약 자체 불가)
#
#   실제 사례(2026-09-14): HDT 3/34실(91%) → ② 발동으로 HDT→HDP 간격만 축소.
#   HDP 13실·FDB 16실은 팔 재고가 있으므로 그 위 계단은 전액 유지.
#
#   ※ 계단은 '같은 상품군' 안에서만 적용합니다. 그린밸리(GDB/GDF)는 펜션형으로
#     메인 호텔동과 상품군이 달라 별도 계단을 씁니다.

# 메인 호텔동 계단 (하위객실, 상위객실, 최소 가격차)
LADDER_GAPS = [
    ("HDT", "HDP", 30000),
    ("HDP", "FDB", 35000),
    ("FDB", "FDE", 37000),
    ("FDE", "HDF", 70000),
]
# 그린밸리 계단 (신규). 기존에는 GDB↔GDF 사이에 계단이 아예 없어서
# GDF(패밀리)가 GDB(더블)보다 싸지는 날이 9월 20일 중 4일 발생했습니다.
# 최소 가격차 90,000원 = 두 요금표의 같은 BAR 최소 격차(BAR8 기준 92,000)에 맞춤.
GREENVALLEY_GAPS = [
    ("GDB", "GDF", 90000),
]
LADDER_GAP_SHRINK = 0.3        # 하급 매진 임박 시 간격 축소 비율 (1.0 = 축소 안 함)
LADDER_NEAR_SELLOUT_AVAIL = 2  # 하급 잔여가 이 이하면 '매진 임박'
LADDER_NEAR_SELLOUT_OCC = 90   # 또는 하급 OCC가 이 이상이면 '매진 임박'


def ladder_gap_factor(occ_low, avail_low):
    """하급 객실의 판매 가능 상태 → 계단 간격 배수. None이면 계단 제외(매진)."""
    if not _PRICING_V2:
        return 1.0
    try:
        av = float(avail_low)
    except (TypeError, ValueError):
        av = None
    if av is not None and av == av and av <= 0:
        return None                                   # 매진 → 계단에서 제외
    if (av is not None and av == av and av <= LADDER_NEAR_SELLOUT_AVAIL) \
            or occ_low >= LADDER_NEAR_SELLOUT_OCC:
        return LADDER_GAP_SHRINK                      # 매진 임박 → 축소
    return 1.0                                        # 팔 재고 충분 → 전액


def apply_ladder(fp, gaps, occs, avails):
    """가격 계단 적용.

    - 매진(잔여 0) 객실은 '기준'에서 제외합니다. 예약이 불가하므로 잠식할 재고가
      없고, 그 가격을 위 객실의 하한으로 쓰면 캐스케이드만 발생합니다.
    - 제외된 객실을 건너뛴 구간의 간격은 합산해서 적용합니다.
    반환: 간격이 축소된 객실 집합 (표시용)
    """
    order = [g[0] for g in gaps] + [gaps[-1][1]]
    gap_of = {up: g for _lo, up, g in gaps}
    shrunk = set()
    last = None                       # 기준이 되는 '판매 중' 객실
    for rid in order:
        if rid not in fp:
            continue
        if last is not None:
            f = ladder_gap_factor(occs.get(last, 0), avails.get(last))
            if f is not None:
                i_l, i_n = order.index(last), order.index(rid)
                gap = sum(gap_of.get(order[j], 0) for j in range(i_l + 1, i_n + 1))
                if f < 1.0:
                    shrunk.add(rid)
                fp[rid] = max(fp[rid], fp[last] + int(gap * f))
        # 판매 중인 객실만 다음 기준이 됩니다 (매진 객실은 기준에서 제외)
        av = avails.get(rid)
        try:
            is_open = av is None or (float(av) == float(av) and float(av) > 0)
        except (TypeError, ValueError):
            is_open = True
        if is_open:
            last = rid
    return shrunk

# ── 연동 객실이 자체 재고를 반영하는 폭 ──────────────────────────────
# FPT·PPV는 FDB BAR를, FFD는 FDE 가격을 그대로 따라갔습니다(자체 재고 무시).
# 연동 BAR 기준 ±LINK_FLEX_STEPS 단계까지 자체 재고 신호를 반영합니다.
LINK_FLEX_STEPS = 2

# ── 메인 5객실 OCC 혼합 비율 (기본 0 = 기존 동작 유지) ───────────────
# 0.0 → 객실별 OCC 그대로 (현행). 하위객실 1개가 매진되면 역전방지가
#        상위객실 전체를 끌어올리는 캐스케이드가 남습니다.
# 0.5 → 객실별 OCC와 호텔 전체 OCC를 반반 섞어 캐스케이드 폭을 절반으로.
# 1.0 → 호텔 전체 OCC만 사용 (캐스케이드 소멸, 객실별 신호도 소멸).
# ※ 이 값을 올리면 요금 성향이 크게 바뀝니다. 비교 패널로 먼저 확인하세요.
ROOM_OCC_BLEND = 0.0


def occ_to_offset(occ, avail=None):
    """OCC(+잔여 실수)를 BAR 인상 단계로 변환."""
    offset = 0
    for threshold, off in OCC_OFFSET_LADDER:
        if occ >= threshold:
            offset = off
            break
    if avail is not None and occ >= SCARCITY_MIN_OCC:
        try:
            a = int(float(avail))
        except (TypeError, ValueError):
            a = None
        if a is not None:
            for limit in sorted(SCARCITY_BY_AVAIL):
                if a <= limit:
                    offset = max(offset, SCARCITY_BY_AVAIL[limit])
                    break
    return min(offset, OCC_OFFSET_MAX)


def discount_steps(date_obj, occ):
    """판매 부진 인하 단계 (0 이상). 과거 날짜에는 적용하지 않습니다."""
    days = (date_obj - TODAY).days
    if days < 0:
        return 0
    for max_days, max_occ, steps in DISCOUNT_RULES:
        if days <= max_days and occ < max_occ:
            return min(steps, DISCOUNT_MAX_STEPS)
    return 0


def determine_bar(date_obj, occ, avail=None, pickup=None):
    """날짜 + OCC(+잔여 실수 +판매 속도) → BAR 코드.

    시작 BAR에서 출발해
      (+) OCC / 잔여 실수 / 소진 속도가 빠르면 고가 BAR로
      (-) 판매 부진 / 소진 속도가 느리면 저가 BAR로
    이동하되, 시즌별 상한(get_bar_ceiling)을 절대 넘지 않습니다.

    _PRICING_V2 = False 이면 기존 곡선(31/51/81 → 최대 3단계, 인하·상한 없음)으로 동작.
    """
    start_idx = BAR_ORDER.index(get_start_bar(date_obj))

    if not _PRICING_V2:
        if occ >= 81:   offset = 3
        elif occ >= 51: offset = 2
        elif occ >= 31: offset = 1
        else:           offset = 0
        return BAR_ORDER[max(0, start_idx - offset)]

    # 시즌 상한: 상한 BAR보다 비싸질 수 없음.
    # 단, 상한이 시작BAR보다 비싸면 시작BAR를 존중 (상한이 시즌 시작 요금을
    # 아래로 끌어내리는 일은 없습니다).
    ceil_idx = min(max(BAR_ORDER.index(get_bar_ceiling(date_obj)), 0), start_idx)
    band = start_idx - ceil_idx                    # 이 날짜가 올라갈 수 있는 총 단계

    # ※ 인상폭을 '절대 단계'가 아니라 '밴드 대비 비율'로 환산합니다.
    #   그러지 않으면 밴드가 좁은 날(9월 평일: 시작 BAR5 → 상한 BAR3 = 2단계)에서
    #   OCC 50%가 밴드를 다 써버려 50~100% 구간이 전부 같은 요금이 됩니다.
    up = occ_to_offset(occ, avail)
    up_eff = int(band * min(1.0, up / OCC_OFFSET_MAX) + 0.5) if band > 0 else 0

    down = discount_steps(date_obj, occ)
    pk = pickup_steps(date_obj, avail, pickup)
    offset = up_eff - down + pk
    offset = max(offset, -DOWN_MAX_STEPS)          # 인하 상한

    idx = start_idx - offset
    idx = max(ceil_idx, min(len(BAR_ORDER) - 1, idx))

    # 최상단 BAR는 재고 근거가 있을 때만 (달력만으로 최고가가 나오지 않게)
    gated_idx = BAR_ORDER.index(apply_top_bar_gate(BAR_ORDER[idx], occ, avail))
    # 게이트는 '올라간 만큼'만 되돌립니다 — 시즌 시작 요금 아래로는 내리지 않음
    return BAR_ORDER[min(gated_idx, max(start_idx, idx))]


def blend_occ(room_occ, hotel_occ):
    """메인 5객실용 혼합 OCC (ROOM_OCC_BLEND=0 이면 객실별 OCC 그대로)."""
    if not _PRICING_V2 or not ROOM_OCC_BLEND:
        return room_occ
    w = max(0.0, min(1.0, ROOM_OCC_BLEND))
    return room_occ * (1 - w) + hotel_occ * w


# =============================================================================
# 3-NEW. 희소성 프리미엄 + 전체 날짜 가격 통합 산출 (역전방지 + 연동 포함)
# =============================================================================
_price_cache = {}  # 리런 단위 캐시 (모듈 레벨, 리런마다 초기화됨)


def _rows_signature(df, date_obj):
    """캐시 키용 — 해당 날짜 행의 '내용' 지문. id(df) 대신 사용."""
    try:
        rows = df[df['Date'] == date_obj]
        if rows.empty:
            return "empty"
        return tuple(
            (str(r['RoomID']),
             None if pd.isna(r['Available']) else float(r['Available']),
             None if pd.isna(r['Total']) else float(r['Total']))
            for _, r in rows.sort_values('RoomID').iterrows()
        )
    except Exception as e:
        _logic_errors.append(f"_rows_signature 실패: {type(e).__name__}: {e}")
        return "unhashable"


def _clean_manual_bar(raw, date_str=None, rid=None):
    """수동 오버라이드 BAR 값 정규화. 유효하지 않으면 None + 경고 기록.
    ※ 기존에는 'BAR 3', '3' 같은 오타가 그대로 저장되어 가격 0원으로 판매됐습니다."""
    if raw is None:
        return None
    s = str(raw).strip().upper().replace(" ", "")
    if not s or s in ("NONE", "NAN"):
        return None
    if is_valid_bar(s):
        return s
    if date_str and rid:
        _record_issue(date_str, rid, f"수동 오버라이드 값 '{raw}' 이 유효한 BAR 코드가 아님 → 무시")
    return None


def compute_scarcity_premium(avail, date_obj):
    """희소성 프리미엄: 잔여2실 +20,000 / 잔여1실 +50,000 / 체크인7일이내 잔여1실 +70,000

    ※ 수정: 잔여 0(매진)에는 프리미엄을 붙이지 않습니다. 팔 수 없는 재고에
      프리미엄을 얹어 표시 요금만 부풀리던 동작을 제거했습니다.
    ※ 수정: 결측(NaN)은 '재고 999실'로 단정하지 않고 프리미엄 0으로 처리하며,
      결측 자체는 normalize_inventory()가 경고로 표면화합니다.
    """
    try:
        avail_int = int(float(avail)) if pd.notna(avail) else None
    except (TypeError, ValueError):
        avail_int = None
    if avail_int is None or avail_int <= 0:
        return 0
    days_to_checkin = (date_obj - TODAY).days
    if avail_int <= 1:
        return 70000 if days_to_checkin <= 7 else 50000
    elif avail_int <= 2:
        return 20000
    return 0


def snap_to_bar_ceil(table, floor_price):
    """floor_price 이상인 BAR 중 가장 저렴한 BAR 반환.
    예) FFD floor=609,000 → BAR5(502,000)는 미달, BAR4(559,000)도 미달,
        BAR3(624,000) ≥ 609,000 → 'BAR3'
    모든 BAR가 floor 미만이면 최고가 BAR 반환.
    ※ 수정: 기존 int(bar.replace('BAR','')) 방식은 'BAR0P'에서 예외가 나 최고가
      BAR가 후보에서 빠졌습니다. BAR_ORDER 기준으로 교체."""
    best_bar, best_rank = None, -1
    for bar, price in table.items():
        r = bar_rank(bar)
        if r is None:
            continue
        if price >= floor_price and r > best_rank:
            best_rank, best_bar = r, bar
    if best_bar is None:
        # 전 BAR가 floor 미만 → 표에 존재하는 최고가 BAR
        for b in BAR_ORDER:
            if b in table:
                return b
        return "BAR0"
    return best_bar


def compute_all_prices_for_date(date_obj, curr_df, manual_bars=None):
    """주어진 날짜의 전체 객실 가격 통합 산출.
    Step1: 전체 호텔OCC → hotel_bar
    Step2~3: 메인5객실 BAR+가격
    Step4: 역전방지 (HDT<HDP<FDB<FDE<HDF)
    Step5~6: 특수객실 연동+희소성 프리미엄
    Returns: {rid: {'occ', 'bar', 'price', 'is_manual'}}
    """
    if manual_bars is None:
        manual_bars = {}

    date_str = date_obj.strftime('%Y-%m-%d')
    # ※ 수정: 캐시 키에 id(curr_df)를 쓰면 (a) 내용 변경을 감지하지 못하고
    #   (b) DataFrame이 GC된 뒤 주소가 재사용되면 다른 데이터의 값을 반환합니다.
    #   해당 날짜 행의 내용 지문으로 교체.
    _prev_sig = _rows_signature(st.session_state.get('prev_df', pd.DataFrame()), date_obj) \
        if _PRICING_V2 else None
    cache_key = (date_str, _rows_signature(curr_df, date_obj), _prev_sig,
                 tuple(sorted(manual_bars.items())), _PRICING_V2, ROOM_OCC_BLEND)
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    date_rows = curr_df[curr_df['Date'] == date_obj]

    # Step 1. 전체 호텔 OCC (정상 데이터 행만으로 계산 — 결측 행이 지표를 오염시키지 않게)
    total_avail_sum, total_rooms_sum = 0.0, 0.0
    for _, row in date_rows.iterrows():
        try:
            tot_f = float(row['Total']) if pd.notna(row['Total']) else float('nan')
            av_f = float(row['Available']) if pd.notna(row['Available']) else float('nan')
        except (TypeError, ValueError):
            continue
        if not (tot_f == tot_f) or tot_f <= 0 or not (av_f == av_f):
            continue
        total_avail_sum += min(max(av_f, 0.0), tot_f)
        total_rooms_sum += tot_f
    hotel_occ = ((total_rooms_sum - total_avail_sum) / total_rooms_sum * 100) if total_rooms_sum > 0 else 0
    hotel_bar = determine_bar(date_obj, hotel_occ)

    result = {}

    # Step 2~3. 메인 5개 객실 BAR + 기본 가격
    main_rooms_order = ["HDT", "HDP", "FDB", "FDE", "HDF"]
    base_prices, bars, occs, avails, is_manuals = {}, {}, {}, {}, {}

    for rid in main_rooms_order:
        m = date_rows[date_rows['RoomID'] == rid]
        if m.empty:
            continue
        occ, av, tot, _ok = normalize_inventory(
            m.iloc[0]['Available'], m.iloc[0]['Total'], date_str, rid, fallback_occ=hotel_occ)
        occs[rid] = occ
        avails[rid] = av

        manual_bar = _clean_manual_bar(manual_bars.get(f"{date_str}_{rid}"), date_str, rid)
        if manual_bar:
            bar, is_manual = manual_bar, True
        else:
            # ROOM_OCC_BLEND=0(기본)이면 객실별 OCC 그대로 — 기존 동작과 동일
            bar = determine_bar(date_obj, blend_occ(occ, hotel_occ), av,
                                get_pickup_per_day(date_obj, rid))
            is_manual = False

        bars[rid] = bar
        is_manuals[rid] = is_manual
        base_prices[rid] = PRICE_TABLE.get(rid, {}).get(bar, 0)

    # Step 4. 가격 역전 방지 (계단) — 발동 기준은 ladder_gap_factor() 참고
    fp = dict(base_prices)
    ladder_shrunk = apply_ladder(fp, LADDER_GAPS, occs, avails)

    for rid in main_rooms_order:
        if rid not in fp:
            continue
        occ_bar = bars.get(rid, "BAR8")
        adj_price = fp[rid]
        # 역전방지로 가격 상향된 경우에만 유효 BAR 역산
        # (가격이 그대로면 계산 BAR를 유지 — 동가 BAR 오표시 방지)
        if adj_price != base_prices.get(rid, adj_price):
            eff_bar = price_to_effective_bar(rid, adj_price) or occ_bar
        else:
            eff_bar = occ_bar
        # 수동 오버라이드가 역전방지로 상향된 경우 → 관리자에게 알림
        # ("내가 넣은 BAR가 안 먹는다"의 실제 원인을 표면화)
        if is_manuals.get(rid) and adj_price != base_prices.get(rid):
            _record_issue(date_str, rid,
                          f"오버라이드 {occ_bar}({base_prices.get(rid, 0):,}원)이 "
                          f"역전방지로 {adj_price:,}원으로 상향됨")
        result[rid] = {
            'occ': occs.get(rid, 0),
            'bar': eff_bar,
            'original_bar': occ_bar,
            'price': adj_price,
            'is_manual': is_manuals.get(rid, False),
            'ladder_shrunk': rid in ladder_shrunk,   # 하급 매진임박으로 계단 축소됨
            'ladder_lifted': adj_price != base_prices.get(rid),
        }

    # Step 5. GDB/GDF: 자체 OCC 기반 독립 BAR (그린밸리 펜션형, 메인 계층 무관)
    fde_p = fp.get("FDE", 0)
    gv_occ, gv_avail = {}, {}

    for rid, table in [("GDB", GDB_TABLE), ("GDF", GDF_TABLE)]:
        m = date_rows[date_rows['RoomID'] == rid]
        if m.empty:
            continue
        cap = ROOM_PRICE_CAPS.get(rid)
        occ, av, tot, _ok = normalize_inventory(
            m.iloc[0]['Available'], m.iloc[0]['Total'], date_str, rid, fallback_occ=hotel_occ)

        # ※ 수정: 고정객실도 수동 오버라이드를 반영합니다.
        #   (기존에는 오버라이드 매트릭스에서 입력해도 조용히 무시됐습니다)
        man = _clean_manual_bar(manual_bars.get(f"{date_str}_{rid}"), date_str, rid)
        if man:
            result[rid] = {'occ': occ, 'bar': man,
                           'original_bar': determine_bar(date_obj, occ, av,
                                                         get_pickup_per_day(date_obj, rid)),
                           'price': table.get(man, 0), 'is_manual': True, 'capped': False}
            continue

        own_bar = determine_bar(date_obj, occ, av, get_pickup_per_day(date_obj, rid))
        base_p = table.get(own_bar, list(table.values())[-1])
        # V2: 희소성은 OCC 래더(SCARCITY_BY_AVAIL)에서 이미 반영 → 정액 가산 중복 제거
        scarcity = 0 if _PRICING_V2 else compute_scarcity_premium(av, date_obj)
        raw_p = base_p + scarcity
        final_p = min(raw_p, cap) if cap else raw_p
        # ※ 수정: 항상 재역산하면 동가 BAR에서 엉뚱한 BAR가 표시됩니다.
        #   GDB_TABLE은 BAR6=BAR7=BAR8=298,000이라 계산이 BAR6이어도
        #   역산이 가장 저렴한 BAR8을 골라 'BAR6 ▲ BAR8'로 찍혔습니다.
        #   → 가격이 계산 BAR의 표가와 같으면 계산 BAR를 그대로 씁니다.
        eff_bar = own_bar if table.get(own_bar) == final_p else (
            price_to_effective_bar(rid, final_p) or own_bar)
        result[rid] = {'occ': occ, 'bar': eff_bar, 'original_bar': own_bar, 'price': final_p,
                       'is_manual': False, 'capped': bool(cap and raw_p > cap)}
        gv_occ[rid], gv_avail[rid] = occ, av

    # Step 5-B. 그린밸리 계단 (GDB → GDF)
    # ※ 기존에는 GDB↔GDF 사이에 역전방지가 아예 없어 GDF(패밀리)가
    #   GDB(더블)보다 싸지는 날이 발생했습니다(9월 20일 중 4일).
    if _PRICING_V2:
        gv_fp = {r: result[r]['price'] for r in ("GDB", "GDF")
                 if r in result and not result[r].get('is_manual')}
        if len(gv_fp) == 2:
            apply_ladder(gv_fp, GREENVALLEY_GAPS, gv_occ, gv_avail)
            for r in ("GDB", "GDF"):
                if gv_fp[r] != result[r]['price']:
                    cap_r = ROOM_PRICE_CAPS.get(r)
                    newp = min(gv_fp[r], cap_r) if cap_r else gv_fp[r]
                    result[r]['price'] = newp
                    result[r]['bar'] = price_to_effective_bar(r, newp) or result[r]['bar']
                    result[r]['capped'] = bool(cap_r and gv_fp[r] > cap_r)

    # Step 6. FFD: FDE 연동 (FDE+20k 플로어) + 자체 재고 반영
    m_ffd = date_rows[date_rows['RoomID'] == "FFD"]
    if not m_ffd.empty:
        occ_ffd, av_ffd, tot_ffd, _ok = normalize_inventory(
            m_ffd.iloc[0]['Available'], m_ffd.iloc[0]['Total'], date_str, "FFD", fallback_occ=hotel_occ)
        man = _clean_manual_bar(manual_bars.get(f"{date_str}_FFD"), date_str, "FFD")
        if man:
            result["FFD"] = {'occ': occ_ffd, 'bar': man, 'original_bar': man,
                             'price': FFD_TABLE.get(man, 0), 'is_manual': True, 'capped': False}
        elif not _PRICING_V2:
            scarcity_ffd = compute_scarcity_premium(av_ffd, date_obj)
            ffd_bar = snap_to_bar_ceil(FFD_TABLE, fde_p + 20000 + scarcity_ffd)
            result["FFD"] = {'occ': occ_ffd, 'bar': ffd_bar, 'original_bar': ffd_bar,
                             'price': FFD_TABLE.get(ffd_bar, FFD_TABLE["BAR0"]),
                             'is_manual': False, 'capped': False}
        else:
            # 연동 기준 BAR = FDE+20,000 플로어
            link_bar = snap_to_bar_ceil(FFD_TABLE, fde_p + 20000)
            link_idx = bar_rank(link_bar) or 0
            # 자체 재고 신호를 ±LINK_FLEX_STEPS 범위에서 반영
            own_idx = bar_rank(determine_bar(date_obj, occ_ffd, av_ffd,
                                             get_pickup_per_day(date_obj, "FFD")))
            idx = link_idx
            if own_idx is not None:
                delta = max(-LINK_FLEX_STEPS, min(LINK_FLEX_STEPS, own_idx - link_idx))
                idx = max(0, min(len(BAR_ORDER) - 1, link_idx + delta))
            # FDE 역전 금지 — FFD 가격이 FDE 이하로 내려가면 한 단계씩 올림
            while idx > 0 and FFD_TABLE.get(BAR_ORDER[idx], 0) <= fde_p:
                idx -= 1
            ffd_bar = BAR_ORDER[idx]
            result["FFD"] = {'occ': occ_ffd, 'bar': ffd_bar, 'original_bar': link_bar,
                             'price': FFD_TABLE.get(ffd_bar, FFD_TABLE["BAR0"]),
                             'is_manual': False, 'capped': False}

    # Step 7. FPT/PPV: FDB BAR 연동 + 자체 재고 반영
    # (주석 정정: 기존 요금표 주석은 FPT를 '호텔 전체 OCC 기준'이라 적었지만
    #  구현은 FDB 연동입니다. 실제 동작에 맞춰 FDB 연동으로 문서화합니다.)
    fdb_bar = result.get("FDB", {}).get("bar", hotel_bar)
    fdb_idx = bar_rank(fdb_bar) or 0
    for rid, table in [("FPT", FPT_TABLE), ("PPV", PPV_TABLE)]:
        m = date_rows[date_rows['RoomID'] == rid]
        if m.empty:
            continue
        cap = ROOM_PRICE_CAPS.get(rid)
        occ, av, tot, _ok = normalize_inventory(
            m.iloc[0]['Available'], m.iloc[0]['Total'], date_str, rid, fallback_occ=hotel_occ)

        man = _clean_manual_bar(manual_bars.get(f"{date_str}_{rid}"), date_str, rid)
        if man:
            result[rid] = {'occ': occ, 'bar': man, 'original_bar': fdb_bar,
                           'price': table.get(man, 0), 'is_manual': True, 'capped': False}
            continue

        link_bar = fdb_bar
        if _PRICING_V2:
            # 자체 재고 신호를 ±LINK_FLEX_STEPS 범위에서 반영
            own_idx = bar_rank(determine_bar(date_obj, occ, av,
                                             get_pickup_per_day(date_obj, rid)))
            if own_idx is not None:
                delta = max(-LINK_FLEX_STEPS, min(LINK_FLEX_STEPS, own_idx - fdb_idx))
                link_bar = BAR_ORDER[max(0, min(len(BAR_ORDER) - 1, fdb_idx + delta))]

        base_p = table.get(link_bar, list(table.values())[-1])
        scarcity = 0 if _PRICING_V2 else compute_scarcity_premium(av, date_obj)
        raw_p = base_p + scarcity
        final_p = min(raw_p, cap) if cap else raw_p
        # cap에 걸려 요금표보다 낮아진 경우 표시 BAR를 실제 가격에 맞춰 역산
        # (기존에는 'BAR0P 표시 / 실가 900,000' 같은 불일치가 발생)
        eff_bar = link_bar
        if cap and raw_p > cap:
            eff_bar = price_to_effective_bar(rid, final_p) or link_bar
        result[rid] = {'occ': occ, 'bar': eff_bar, 'original_bar': fdb_bar, 'price': final_p,
                       'is_manual': False, 'capped': bool(cap and raw_p > cap)}

    _price_cache[cache_key] = result
    return result


def compute_final_prices_for_date(date_obj, curr_df, manual_bars=None, applied_rates=None):
    """예외(applied_rates)로 고정한 BAR까지 반영한 '최종' 가격.

    ※ 기존에는 예외 셀의 가격을 get_bar_price(rid, bar)로 요금표에서 직접 읽어
      역전방지·상한·연동을 모두 우회했습니다. 그래서 예외로 HDF에 BAR8을 지정하면
      HDF 420,000 < FDE 482,000 처럼 실제 요금 역전이 발생했습니다.
      → 예외 BAR를 수동 오버라이드와 같은 경로로 주입해 가드레일을 통과시킵니다.
    '직접가격'(숫자) 예외는 관리자가 지정한 절대값이므로 여기서 다루지 않습니다.
    """
    ov = dict(manual_bars or {})
    date_str = date_obj.strftime('%Y-%m-%d')
    rooms = (applied_rates or {}).get(date_str, {}).get('rooms', {}) or {}
    for rid, v in rooms.items():
        s = str(v).strip().upper().replace(" ", "")
        if is_valid_bar(s):
            ov[f"{date_str}_{rid}"] = s
    return compute_all_prices_for_date(date_obj, curr_df, ov)



def price_to_effective_bar(room_id, price):
    """조정된 가격에서 가장 가까운 실효 BAR 코드를 역산.
    price 이하인 BAR 중 가장 비싼 BAR 반환.

    ※ 수정 2건:
      1) 기존 range(1, 9)는 BAR0/BAR0P를 후보에서 제외했습니다. 그래서 역전방지로
         BAR0P 가격을 넘어선 HDF(1,001,000)가 'BAR1'로 표시되어 요금과 셀 색상이
         전부 어긋났습니다. → BAR_ORDER 전체를 후보로 사용.
      2) 동가 BAR(예: GDB BAR6=BAR7=BAR8=298,000)에서 기존 엄격 비교(p > best)는
         항상 가장 비싼 쪽(BAR6)을 반환했습니다. → 동가면 저가 BAR를 반환.
    price가 최고가 BAR보다 높으면 None (호출부에서 계산 BAR를 그대로 사용)."""
    table = get_room_table(room_id)
    if not table:
        return None
    best_bar, best_price = None, None
    for bar in BAR_ORDER:            # 고가 → 저가 순
        p = table.get(bar)
        if p is None or p > price:
            continue
        if best_price is None or p > best_price:
            best_price, best_bar = p, bar
        elif p == best_price:
            best_bar = bar           # 동가면 더 저렴한(뒤쪽) BAR 채택
    return best_bar


def get_final_values(room_id, date_obj, avail, total, manual_bar=None):
    """반환: (occ, bar, price, is_manual)

    ※ 수정: 기존 `except Exception: pass` 는 모든 오류를 조용히 삼키고
      역전방지·연동·희소성이 전부 빠진 폴백 경로로 넘어갔습니다. 같은 화면에서
      객실별로 요금 체계가 달라져도 아무 표시가 없었습니다.
      → 오류를 _logic_errors에 기록해 화면 상단에 노출합니다.
    """
    date_str = date_obj.strftime('%Y-%m-%d')

    # --- 통합 산출 경로 (session_state에 today_df 있을 때) ---
    try:
        curr_df = st.session_state.get('today_df', pd.DataFrame())
        if not curr_df.empty:
            manual_bars = dict(st.session_state.get('manual_bars', {}))
            if manual_bar:
                manual_bars[f"{date_str}_{room_id}"] = manual_bar
            all_prices = compute_all_prices_for_date(date_obj, curr_df, manual_bars)
            if room_id in all_prices:
                info = all_prices[room_id]
                return info['occ'], info['bar'], info['price'], info.get('is_manual', False)
    except Exception as e:
        msg = f"{date_str} {room_id}: 통합 산출 실패 → 폴백 경로 사용 ({type(e).__name__}: {e})"
        if msg not in _logic_errors:
            _logic_errors.append(msg)

    # --- Fallback (역전방지·연동 없음 — 통합 경로 실패 시에만 도달) ---
    occ, av_eff, tot_eff, _ok = normalize_inventory(avail, total, date_str, room_id)

    table = get_room_table(room_id)
    man = _clean_manual_bar(manual_bar, date_str, room_id)
    if man:
        return occ, man, table.get(man, 0), True

    if not table:
        type_code, _season, _is_weekend = get_season_details(date_obj)
        return occ, type_code, 0, False

    bar = determine_bar(date_obj, occ, av_eff, get_pickup_per_day(date_obj, room_id))
    price = table.get(bar, table.get(BAR_ORDER[-1], 0))
    cap = ROOM_PRICE_CAPS.get(room_id)
    if cap:
        price = min(price, cap)
    return occ, bar, price, False


def date_filter_toggle(key_prefix, total_dates, default_show_past=False):
    past_count = sum(1 for d in total_dates if d < TODAY)
    future_count = len(total_dates) - past_count

    if past_count == 0:
        return total_dates

    show_past = st.checkbox(
        f"📜 과거 {past_count}일 포함 (현재 미래 {future_count}일만 표시)",
        value=default_show_past,
        key=f"show_past_{key_prefix}"
    )
    return total_dates if show_past else [d for d in total_dates if d >= TODAY]


def filter_df_by_dates(df, visible_dates):
    if df.empty:
        return df
    return df[df['Date'].isin(visible_dates)].copy()


# =============================================================================
# 3-A. 재검토 캐싱 (B 개선: build_review_map)
# =============================================================================
def _df_signature(df, applied_rates):
    """DataFrame + applied_rates의 시그니처 - 캐시 키용"""
    if df.empty:
        d_sig = "empty"
    else:
        # 핵심 컬럼만 사용해서 해시
        try:
            d_sig = hashlib.md5(
                pd.util.hash_pandas_object(df[['Date', 'RoomID', 'Available', 'Total']]).values.tobytes()
            ).hexdigest()
        except Exception:
            d_sig = str(len(df)) + "_" + str(df['Date'].min()) + "_" + str(df['Date'].max())
    try:
        a_sig = hashlib.md5(json.dumps(applied_rates, sort_keys=True, default=str).encode()).hexdigest()
    except Exception:
        a_sig = str(len(applied_rates))
    return f"{d_sig}_{a_sig}"


def build_review_map(current_df, applied_rates):
    """모든 (rid, date) 조합에 대해 재검토 필요 여부를 한 번에 계산.
    리턴: dict {(rid, date_obj): {'needs': bool, 'applied': str, 'rec': str, 'rec_at_apply': str}}
    세션 캐시 사용 (시그니처 기반)"""
    if current_df.empty:
        return {}

    sig = _df_signature(current_df, applied_rates)
    cache_key = f"_review_map_cache_{sig}"

    if cache_key in st.session_state:
        return st.session_state[cache_key]

    result = {}
    for rid in DYNAMIC_ROOMS:
        room_df = current_df[current_df['RoomID'] == rid]
        for _, row in room_df.iterrows():
            d = row['Date']
            date_str = d.strftime('%Y-%m-%d')
            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)

            if not applied_bar:
                continue

            _, rec_bar, _, _ = get_final_values(rid, d, row['Available'], row['Total'])
            rec_at_apply = applied_rates.get(date_str, {}).get('rec_bar_at_apply', {}).get(rid)
            needs = bool(rec_at_apply and rec_at_apply != rec_bar)

            result[(rid, d)] = {
                'needs': needs,
                'applied': applied_bar,
                'rec': rec_bar,
                'rec_at_apply': rec_at_apply,
            }

    # 이전 캐시 정리 (메모리 절약)
    for k in list(st.session_state.keys()):
        if k.startswith("_review_map_cache_") and k != cache_key:
            del st.session_state[k]
    st.session_state[cache_key] = result
    return result


def is_review_needed(rid, date_obj, current_df, applied_rates):
    """캐시된 리뷰맵 사용 - 기존 호출부 호환용"""
    review_map = build_review_map(current_df, applied_rates)
    info = review_map.get((rid, date_obj))
    if not info:
        # 캐시에 없으면 적용 BAR이 없다는 뜻 - 기존 동작 유지
        date_str = date_obj.strftime('%Y-%m-%d')
        applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
        if not applied_bar:
            return False, None, None
        # 안전장치
        curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == date_obj)]
        if curr_match.empty:
            return False, applied_bar, None
        _, rec_bar, _, _ = get_final_values(rid, date_obj, curr_match.iloc[0]['Available'], curr_match.iloc[0]['Total'])
        return False, applied_bar, rec_bar
    return info['needs'], info['applied'], info['rec']


# =============================================================================
# 3-B. 가격 무결성 검증 (F 개선)
# =============================================================================
def validate_price_tables():
    """PRICE_TABLE의 BAR1~BAR8 가격이 단조 감소(BAR1>BAR2>...>BAR8)인지 검증.
    리턴: list of warnings"""
    warnings = []
    for room, bars in PRICE_TABLE.items():
        prev_price = None
        prev_bar = None
        for i in range(1, 9):
            bar = f"BAR{i}"
            p = bars.get(bar)
            if p is None:
                warnings.append(f"⚠️ {room}: {bar} 가격 누락")
                continue
            if prev_price is not None and p >= prev_price:
                warnings.append(f"🚨 {room}: {prev_bar}({prev_price:,}) ≤ {bar}({p:,}) — 가격 역전!")
            prev_price = p
            prev_bar = bar
        bar0 = bars.get("BAR0")
        bar1 = bars.get("BAR1")
        if bar0 is not None and bar1 is not None and bar0 <= bar1:
            warnings.append(f"🚨 {room}: BAR0({bar0:,}) ≤ BAR1({bar1:,}) — 수동인상가가 BAR1보다 작거나 같음!")

    # ※ 수정: 기존에는 FPT/PPV만 검사해 GDB/GDF/FFD의 동가·역전을 놓쳤습니다.
    for tname, tbl in [("FPT_TABLE", FPT_TABLE), ("PPV_TABLE", PPV_TABLE),
                       ("GDB_TABLE", GDB_TABLE), ("GDF_TABLE", GDF_TABLE),
                       ("FFD_TABLE", FFD_TABLE)]:
        prev_price, prev_bar = None, None
        for i in range(1, 9):
            bar = f"BAR{i}"
            p = tbl.get(bar)
            if p is None:
                warnings.append(f"⚠️ {tname}: {bar} 가격 누락")
                continue
            if prev_price is not None and p == prev_price:
                warnings.append(f"⚠️ {tname}: {prev_bar}와 {bar}가 동일 가격({p:,}) — OCC가 올라도 요금이 안 움직입니다")
            elif prev_price is not None and p > prev_price:
                warnings.append(f"🚨 {tname}: {prev_bar}({prev_price:,}) < {bar}({p:,}) — 가격 역전!")
            prev_price, prev_bar = p, bar

    # ※ 신규: 요금 상한(cap)과 요금표의 정합성 — cap보다 비싼 BAR는 도달 불가 구간
    for rid, cap in ROOM_PRICE_CAPS.items():
        tbl = get_room_table(rid)
        unreachable = [b for b in BAR_ORDER if b in tbl and tbl[b] > cap]
        if unreachable:
            warnings.append(
                f"⚠️ {rid}: 요금 상한 {cap:,}원 때문에 {', '.join(unreachable)} 구간에 "
                f"도달할 수 없습니다 (최고 {tbl[unreachable[0]]:,}원). "
                f"상한을 올릴지 / 요금표 상단을 정리할지 결정이 필요합니다."
            )
    return warnings


# =============================================================================
# 4. 렌더러 (마스터 테이블)
# =============================================================================
def render_master_table(current_df, prev_df, ch_name=None, title="", mode="기준", applied_rates=None):
    if current_df.empty:
        return "<div style='padding:20px;'>데이터를 업로드하세요.</div>"
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
    for d in dates:
        html += f"<th style='border:1px solid #ddd; padding:{header_padding}; {col_width_style}'>{d.strftime('%m-%d')}</th>"
    html += "</tr><tr style='background:#f9f9f9;'>"
    for d in dates:
        wd = WEEKDAYS_KR[d.weekday()]
        color = "red" if wd == '일' else ("blue" if wd == '토' else "black")
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
                    try:
                        _prev_manual = dict(st.session_state.get('manual_bars', {}))
                        if p_m_bar:
                            _prev_manual[f"{date_str}_{rid}"] = p_m_bar
                        _prev_all = compute_all_prices_for_date(d, prev_df, _prev_manual)
                        prev_bar = _prev_all.get(rid, {}).get('bar')
                    except Exception:
                        prev_bar = None

            style = f"border:1px solid #ddd; padding:{row_padding}; text-align:center; background-color:white; {line_style}"

            if mode == "기준":
                bg = BAR_GRADIENT_COLORS.get(bar, "#FFFFFF")
                style += f"background-color: {bg};"
                try:
                    _ap = compute_all_prices_for_date(d, current_df, st.session_state.get('manual_bars', {}))
                    _orig = _ap.get(rid, {}).get('original_bar', bar)
                except Exception:
                    _orig = bar
                if _orig and _orig != bar:
                    # ※ 수정: 화살표가 ▲(빨강)로 하드코딩돼 있어 요금이 내려간
                    #   경우에도 ▲로 표시됐습니다. BAR 서열로 방향을 판정합니다.
                    _ar, _ac = _bar_move_mark(_orig, bar)
                    bar_disp = (f"<span style='color:#bbb;text-decoration:line-through;"
                                f"font-size:9px;'>{_orig}</span>"
                                f"<span style='color:{_ac};'>{_ar}</span><b>{bar}</b>")
                else:
                    bar_disp = f"<b>{bar}</b>"
                content = f"{bar_disp}<br>{base_price:,}<br>{occ:.0f}%"

            elif mode == "최종결과":
                applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid) if applied_rates else None
                is_applied = applied_bar is not None
                # 가격 직접 오버라이드(GDB/GDF/FFD 숫자 문자열) vs BAR 오버라이드 구분
                _is_price_ovr = is_applied and str(applied_bar).strip().isdigit()
                _guard_lifted = 0
                if _is_price_ovr:
                    final_bar = bar          # 색상은 계산 BAR 기준
                    final_price = int(str(applied_bar).strip())
                elif is_applied:
                    final_bar = applied_bar
                    # ※ 수정: 예외 BAR 가격을 요금표에서 직접 읽으면 역전방지·상한·연동을
                    #   모두 우회해 실제 요금 역전이 발생했습니다(예: 예외 HDF BAR8
                    #   420,000 < FDE 482,000). 가드레일을 통과한 값을 사용합니다.
                    _table_price = get_bar_price(rid, final_bar) or base_price
                    try:
                        _gp = compute_final_prices_for_date(
                            d, current_df, st.session_state.get('manual_bars', {}), applied_rates
                        ).get(rid, {}).get('price')
                    except Exception:
                        _gp = None
                    final_price = _gp if _gp else _table_price
                    if _gp and _gp > _table_price:
                        _guard_lifted = _gp - _table_price
                else:
                    final_bar = bar
                    final_price = base_price
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFFFFF")

                needs_review = False
                if is_applied and applied_rates and rid in DYNAMIC_ROOMS:
                    needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)

                try:
                    _ap2 = compute_all_prices_for_date(d, current_df, st.session_state.get('manual_bars', {}))
                    _orig2 = _ap2.get(rid, {}).get('original_bar', final_bar)
                except Exception:
                    _orig2 = final_bar
                if _is_price_ovr:
                    _bar_disp2 = f"<b>직접가격</b>"
                elif _orig2 and _orig2 != final_bar and not is_applied:
                    _ar2, _ac2 = _bar_move_mark(_orig2, final_bar)
                    _bar_disp2 = (f"<span style='color:#bbb;text-decoration:line-through;"
                                  f"font-size:9px;'>{_orig2}</span>"
                                  f"<span style='color:{_ac2};'>{_ar2}</span><b>{final_bar}</b>")
                else:
                    _bar_disp2 = f"<b>{final_bar}</b>"
                if _guard_lifted:
                    # 예외 BAR 표가보다 역전방지로 올라간 경우 표시
                    _bar_disp2 += (f"<span style='color:#c62828;font-size:8px;' "
                                   f"title='역전방지로 +{_guard_lifted:,}원 상향'>▲역전방지</span>")
                if is_applied:
                    if needs_review:
                        style += f"background-color: {bg}; border: 3px solid #FF6F00; font-weight: bold; box-shadow: inset 0 0 0 2px #FFD54F;"
                        content = f"⚠️ {_bar_disp2}<br>{final_price:,}<br>{occ:.0f}%"
                    else:
                        style += f"background-color: {bg}; border: 3px solid #2E7D32; font-weight: bold;"
                        content = f"⭐ {_bar_disp2}<br>{final_price:,}<br>{occ:.0f}%"
                else:
                    style += f"background-color: {bg}; opacity: 0.9;"
                    content = f"{_bar_disp2}<br>{final_price:,}<br>{occ:.0f}%"

            elif mode == "변화":
                curr_av_safe = float(avail) if pd.notna(avail) else 0.0
                prev_av_safe = float(prev_avail) if (prev_avail is not None and pd.notna(prev_avail)) else 0.0
                pickup = (prev_av_safe - curr_av_safe) if prev_avail is not None else 0
                bg = BAR_LIGHT_COLORS.get(bar, "#FFFFFF")
                style += f"background-color: {bg};"
                if pickup > 0:
                    style += "color:red; font-weight:bold; border: 1.5px solid red;"
                    content = f"+{pickup:.0f}"
                elif pickup < 0:
                    style += "color:blue; font-weight:bold;"
                    content = f"{pickup:.0f}"
                else:
                    content = "-"

            elif mode == "판도변화":
                curr_b_str = str(bar).strip() if bar else ""
                prev_b_str = str(prev_bar).strip() if prev_bar else ""
                if prev_bar is not None and prev_b_str != curr_b_str:
                    try:
                        prev_num = int(prev_b_str.replace('BAR', ''))
                        curr_num = int(curr_b_str.replace('BAR', ''))
                        is_price_up = curr_num < prev_num  # BAR 숫자 낮을수록 고가
                    except Exception:
                        is_price_up = True
                    arrow = "▲" if is_price_up else "▼"
                    border_color = "#B71C1C" if is_price_up else "#0D47A1"
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid {border_color};"
                    content = (f"{arrow} <b style='font-size:13px;'>{curr_b_str}</b><br>"
                               f"<span style='font-size:9px;opacity:0.7;'>{prev_b_str}</span>")
                else:
                    content = f"<span style='color:#aaa; font-size:10px;'>{curr_b_str}</span>"

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
                    try:
                        _pn = int(prev_b_str.replace('BAR', ''))
                        _cn = int(curr_b_str.replace('BAR', ''))
                        _is_up = _cn < _pn
                    except Exception:
                        _is_up = True
                    _bc = "#B71C1C" if _is_up else "#0D47A1"
                    bg = BAR_GRADIENT_COLORS.get(bar, "#7000FF")
                    style += f"background-color: {bg}; color: white; font-weight: bold; border: 2.5px solid {_bc};"
                if is_manual:
                    style += "border: 2px dashed #FF0000;"
                    content = f"⭐ {content}"

            html += f"<td style='{style}'>{content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html


# =============================================================================
# 4-A. 적용 요금 관리 (applied_rates)
# =============================================================================
@st.cache_data(ttl=60)
def load_applied_rates():
    try:
        docs = db.collection(COL_APPLIED).stream()
        result = {}
        for doc in docs:
            result[doc.id] = doc.to_dict()
        return result
    except Exception:
        return {}


def save_applied_rate(target_date_str, applied_data, memo="", rec_at_apply=None, prev_rooms=None, prev_rec_at_apply=None):
    """적용 저장 + 변경 이력(audit log) 자동 기록"""
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
        db.collection(COL_APPLIED).document(target_date_str).set(payload)

        # 변경 이력 기록 (C 개선)
        log_audit(
            action="apply_save",
            target_date=target_date_str,
            new_rooms=applied_data,
            old_rooms=prev_rooms or {},
            memo=memo,
            new_rec_at_apply=rec_at_apply,
            old_rec_at_apply=prev_rec_at_apply,
        )

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"적용 저장 실패: {e}")
        return False


def delete_applied_rate(target_date_str, prev_rooms=None, prev_memo="", prev_rec_at_apply=None):
    try:
        db.collection(COL_APPLIED).document(target_date_str).delete()
        log_audit(
            action="apply_delete",
            target_date=target_date_str,
            new_rooms={},
            old_rooms=prev_rooms or {},
            memo=prev_memo or "",
            old_rec_at_apply=prev_rec_at_apply,
        )
        st.cache_data.clear()
        return True
    except:
        return False


def get_applied_bar(target_date_str, room_id, applied_rates):
    return applied_rates.get(target_date_str, {}).get('rooms', {}).get(room_id)


def get_bar_price(room_id, bar):
    """BAR 코드로 가격 조회."""
    if room_id in DYNAMIC_ROOMS:
        return PRICE_TABLE.get(room_id, {}).get(bar, 0)
    if room_id == "FPT":
        return FPT_TABLE.get(bar, 0)
    if room_id == "PPV":
        return PPV_TABLE.get(bar, 0)
    if room_id == "GDB":
        return GDB_TABLE.get(bar, 0)
    if room_id == "GDF":
        return GDF_TABLE.get(bar, 0)
    if room_id == "FFD":
        return FFD_TABLE.get(bar, 0)
    return 0


def get_applied_price(room_id, applied_bar, date_obj, current_df, applied_rates, fallback=0):
    """예외(applied_rates)로 지정된 셀의 최종 요금.

    ※ 신설 이유: 화면 6곳에서 get_bar_price(rid, bar)로 요금표를 직접 읽어
      역전방지·상한·연동을 우회했습니다. 그 결과
        - 예외 HDF BAR8(420,000) < FDE 권장(482,000) → 실제 요금 역전
        - '직접가격'(숫자) 예외는 get_bar_price가 0을 반환 → 0원 표시
      두 문제가 있었습니다. 모든 화면이 이 함수를 쓰도록 통일합니다.
    """
    s = str(applied_bar).strip()
    if s.isdigit():                      # 직접가격 — 관리자가 지정한 절대값
        return int(s)
    bar = s.upper().replace(" ", "")
    table_p = get_bar_price(room_id, bar) or fallback
    try:
        p = compute_final_prices_for_date(
            date_obj, current_df, st.session_state.get('manual_bars', {}), applied_rates
        ).get(room_id, {}).get('price')
    except Exception:
        p = None
    return p if p else table_p


# =============================================================================
# 4-A-1-B. 예외 자동 갱신 (신규)
# =============================================================================
def auto_update_stale_exceptions(current_df):
    """새 파일 저장 시 기존 예외(applied_rates) 자동 갱신.

    규칙:
    - 권장 BAR 가격 > 예외 BAR 가격  →  권장 BAR로 자동 교체 (판도변화 인상 수용)
    - 예외 BAR 가격 >= 권장 BAR 가격  →  예외 유지 (더 비싼 예외 고수)

    반환: (갱신된 날짜 수, 상세 로그 리스트)
    """
    if current_df.empty:
        return 0, []

    st.cache_data.clear()
    applied = load_applied_rates()
    if not applied:
        return 0, []

    current_dates = set(current_df['Date'].unique())
    updated_count = 0
    log_items = []

    for date_str, rate_info in applied.items():
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            continue

        if d not in current_dates:
            continue

        existing_rooms = rate_info.get('rooms', {})
        if not existing_rooms:
            continue

        new_rooms = {}
        changed = False
        date_log = []

        for rid, exc_bar in existing_rooms.items():
            # ※ 수정: 기존에는 `if rid not in DYNAMIC_ROOMS: continue` 로
            #   GDB·GDF·FFD·FPT·PPV의 예외가 절대 자동 갱신되지 않았습니다.
            #   한 번 걸면 매진되든 말든 영구 고정 → "매진인데 요금이 낮다"의 원인.
            #   '직접가격'(숫자) 예외는 관리자 지정 절대값이므로 그대로 유지합니다.
            if rid not in ALL_ROOMS or str(exc_bar).strip().isdigit():
                new_rooms[rid] = exc_bar
                continue

            row = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if row.empty:
                new_rooms[rid] = exc_bar
                continue

            _, rec_bar, rec_price, _ = get_final_values(
                rid, d, row.iloc[0]['Available'], row.iloc[0]['Total']
            )
            # 예외가도 가드레일을 통과한 값으로 비교 (한쪽만 보정하면 비교가 왜곡됨)
            exc_price = get_applied_price(rid, exc_bar, d, current_df, applied)

            if rec_price > exc_price:
                new_rooms[rid] = rec_bar
                if rec_bar != exc_bar:
                    changed = True
                    date_log.append(f"{rid}: {exc_bar}→{rec_bar} (권장 {rec_price:,} > 예외 {exc_price:,})")
            else:
                new_rooms[rid] = exc_bar

        if changed:
            rec_at_apply = {}
            for rid in new_rooms:
                if rid in ALL_ROOMS:
                    row = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                    if not row.empty:
                        _, r, _, _ = get_final_values(
                            rid, d, row.iloc[0]['Available'], row.iloc[0]['Total']
                        )
                        rec_at_apply[rid] = r

            memo = rate_info.get('memo', '')
            auto_note = ("[자동갱신] " + memo).strip() if memo and not memo.startswith("[자동갱신]") else (memo or "[자동갱신]")

            save_applied_rate(
                date_str, new_rooms,
                memo=auto_note,
                rec_at_apply=rec_at_apply,
                prev_rooms=existing_rooms,
                prev_rec_at_apply=rate_info.get('rec_bar_at_apply', {}),
            )
            updated_count += 1
            log_items.append({'date': date_str, 'changes': date_log})

    return updated_count, log_items



# =============================================================================
# 4-A-2. 변경 이력 (Audit Log) - C 개선
# =============================================================================
def log_audit(action, target_date, new_rooms, old_rooms=None, memo="", new_rec_at_apply=None, old_rec_at_apply=None, extra=None):
    """변경 이력을 audit_log 컬렉션에 기록 (무제한 보존, 수동 정리만)"""
    try:
        old_rooms = old_rooms or {}
        # 변경 사항 diff 계산
        all_keys = set(old_rooms.keys()) | set(new_rooms.keys())
        diffs = []
        for k in sorted(all_keys):
            o = old_rooms.get(k)
            n = new_rooms.get(k)
            if o != n:
                diffs.append({'room': k, 'from': o, 'to': n})

        # 변경 없으면 기록 안 함 (스팸 방지)
        if action in ("apply_save",) and not diffs:
            return

        ts = datetime.now()
        payload = {
            'action': action,  # apply_save, apply_delete, bulk_delete, restore, etc.
            'target_date': target_date,
            'logged_at': ts.isoformat(),
            'logged_at_display': ts.strftime("%Y-%m-%d %H:%M:%S"),
            'memo': memo,
            'new_rooms': new_rooms,
            'old_rooms': old_rooms,
            'diffs': diffs,
            'new_rec_at_apply': new_rec_at_apply,
            'old_rec_at_apply': old_rec_at_apply,
        }
        if extra:
            payload['extra'] = extra
        db.collection(COL_AUDIT).add(payload)
    except Exception as e:
        # 로그 실패가 본 기능을 막으면 안 됨
        pass


@st.cache_data(ttl=30)
def load_audit_log(limit=200, action_filter=None, date_from_str=None, date_to_str=None):
    """변경 이력 조회"""
    try:
        q = db.collection(COL_AUDIT).order_by("logged_at", direction=firestore.Query.DESCENDING).limit(limit)
        result = []
        for doc in q.stream():
            d = doc.to_dict()
            d['_id'] = doc.id
            if action_filter and d.get('action') != action_filter:
                continue
            if date_from_str and d.get('target_date', '') < date_from_str:
                continue
            if date_to_str and d.get('target_date', '') > date_to_str:
                continue
            result.append(d)
        return result
    except Exception:
        return []


def cleanup_audit_log(before_date_str=None):
    """변경 이력 수동 정리 (특정 날짜 이전 또는 전체)"""
    try:
        deleted = 0
        if before_date_str:
            docs = db.collection(COL_AUDIT).where("logged_at", "<", before_date_str + "T00:00:00").stream()
        else:
            docs = db.collection(COL_AUDIT).stream()

        batch = db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 400:  # Firestore batch 제한
                batch.commit()
                deleted += count
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()
            deleted += count
        st.cache_data.clear()
        return deleted
    except Exception as e:
        st.error(f"정리 실패: {e}")
        return 0


# =============================================================================
# 4-A-3. 복원 지점 (Restore Points) - I 개선
# =============================================================================
def create_restore_point(label="자동 백업", trigger="manual"):
    """현재 applied_rates 전체를 스냅샷으로 백업"""
    try:
        current_applied = {}
        for doc in db.collection(COL_APPLIED).stream():
            current_applied[doc.id] = doc.to_dict()

        ts = datetime.now()
        payload = {
            'label': label,
            'trigger': trigger,  # manual, before_bulk_delete, before_shift, etc.
            'created_at': ts.isoformat(),
            'created_at_display': ts.strftime("%Y-%m-%d %H:%M:%S"),
            'applied_count': len(current_applied),
            'applied_snapshot': current_applied,
        }
        doc_ref = db.collection(COL_RESTORE).add(payload)
        st.cache_data.clear()
        return True, ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        st.error(f"복원 지점 생성 실패: {e}")
        return False, None


@st.cache_data(ttl=30)
def load_restore_points(limit=50):
    try:
        q = db.collection(COL_RESTORE).order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        result = []
        for doc in q.stream():
            d = doc.to_dict()
            d['_id'] = doc.id
            result.append(d)
        return result
    except Exception:
        return []


def restore_from_point(point_id):
    """복원 지점으로 되돌리기. 현재 적용 요금을 모두 지우고 스냅샷으로 덮어씀.
    되돌리기 직전에도 자동 백업을 생성해서 다중 안전망."""
    try:
        doc = db.collection(COL_RESTORE).document(point_id).get()
        if not doc.exists:
            return False, "복원 지점을 찾을 수 없습니다."
        snap = doc.to_dict()
        applied_snapshot = snap.get('applied_snapshot', {})

        # 0. 되돌리기 직전 현재 상태 백업
        create_restore_point(
            label=f"되돌리기 전 자동백업 ({snap.get('label','')[:20]})",
            trigger="before_restore",
        )

        # 1. 현재 applied_rates 전체 삭제 (배치)
        batch = db.batch()
        count = 0
        for d in db.collection(COL_APPLIED).stream():
            batch.delete(d.reference)
            count += 1
            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()

        # 2. 스냅샷으로 덮어쓰기 (배치)
        batch = db.batch()
        count = 0
        for date_id, payload in applied_snapshot.items():
            ref = db.collection(COL_APPLIED).document(date_id)
            batch.set(ref, payload)
            count += 1
            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()

        # 3. audit log 기록
        log_audit(
            action="restore",
            target_date="*",
            new_rooms={},
            old_rooms={},
            memo=f"복원 지점 사용: {snap.get('label','')}",
            extra={'restored_count': len(applied_snapshot)},
        )

        st.cache_data.clear()
        return True, f"{len(applied_snapshot)}개 날짜 복원 완료"
    except Exception as e:
        return False, f"복원 실패: {e}"


def delete_restore_point(point_id):
    try:
        db.collection(COL_RESTORE).document(point_id).delete()
        st.cache_data.clear()
        return True
    except:
        return False


def cleanup_restore_points(before_date_str=None):
    """복원 지점 수동 정리"""
    try:
        deleted = 0
        if before_date_str:
            docs = db.collection(COL_RESTORE).where("created_at", "<", before_date_str + "T00:00:00").stream()
        else:
            docs = db.collection(COL_RESTORE).stream()
        batch = db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 400:
                batch.commit()
                deleted += count
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()
            deleted += count
        st.cache_data.clear()
        return deleted
    except Exception as e:
        return 0


# =============================================================================
# 4-B. 권장 vs 적용 비교 표 (A 개선: 객실 필터 파라미터 추가)
# =============================================================================
def render_applied_vs_recommend_table(current_df, applied_rates, prev_df=None, prev_applied_rates=None,
                                      highlight_only_changes=True, focus_dates=None, room_filter=None):
    """room_filter: 표시할 객실 리스트 (None이면 DYNAMIC_ROOMS 전체)"""
    if current_df.empty:
        return "<div style='padding:20px;'>데이터를 업로드하세요.</div>"

    if prev_applied_rates is None:
        prev_applied_rates = applied_rates

    use_focus = bool(focus_dates)
    if use_focus:
        normalized_focus = set()
        for fd in focus_dates:
            if hasattr(fd, 'date') and callable(getattr(fd, 'date', None)):
                normalized_focus.add(fd.date())
            else:
                normalized_focus.add(fd)
        focus_dates = normalized_focus

    dates = sorted(current_df['Date'].unique())
    rooms_to_show = room_filter if room_filter else ALL_ROOMS

    # 재검토 필요 카운트 (DYNAMIC_ROOMS만 오버라이드 대상)
    review_map = build_review_map(current_df, applied_rates)
    review_count = sum(1 for (rid, _), info in review_map.items()
                       if info['needs'] and rid in rooms_to_show and rid in DYNAMIC_ROOMS)

    review_banner = ""
    if review_count > 0:
        review_banner = f"""
        <div style='background:#FFF3E0; border:2px solid #FF6F00; padding:8px 12px;
                    margin-top:5px; border-radius:6px; font-size:13px; color:#E65100;'>
            ⚠️ <b>재검토 필요 {review_count}건</b> — 적용 시점 이후 시스템 권장이 변경된 셀이 있습니다
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

    for rid in rooms_to_show:
        is_fixed = rid in FIXED_ROOMS
        row_label = f"<b>{rid}</b>" + (" <span style='font-size:9px;color:#999;'>연동</span>" if is_fixed else "")
        html += f"<tr><td style='border:1px solid #ddd; padding:8px; background:#fff; border-right:4px solid #000; position:sticky; left:0; z-index:1;'>{row_label}</td>"

        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            curr_match = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if curr_match.empty:
                html += "<td style='border:1px solid #ddd; padding:8px; text-align:center;'>-</td>"
                continue

            avail = curr_match.iloc[0]['Available']
            total = curr_match.iloc[0]['Total']
            _, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total)

            d_key = d.date() if (hasattr(d, 'date') and callable(getattr(d, 'date', None))) else d
            if use_focus and d_key not in focus_dates:
                applied_bar_o = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
                bar_show = applied_bar_o if applied_bar_o else rec_bar
                style = "border:1px solid #eee; padding:8px; text-align:center; background-color: #FAFAFA; color: #BBB;"
                cell_content = f"<span style='font-size:9px;'>포커스외</span><br><span style='font-size:10px;'>{bar_show}</span>"
                html += f"<td style='{style}' title='5번 선택 외 날짜'>{cell_content}</td>"
                continue

            # ── 연동 객실 (GDB/GDF/FFD/FPT/PPV) ──
            if is_fixed:
                # 오버라이드 확인
                fixed_override = applied_rates.get(date_str, {}).get('rooms', {}).get(rid) if applied_rates else None
                _fovr_is_price = fixed_override and str(fixed_override).strip().isdigit()
                _fovr_is_bar = fixed_override and str(fixed_override).strip().upper().startswith('BAR')

                prev_rec_bar_f = None
                if prev_df is not None and not prev_df.empty:
                    prev_m_f = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                    if not prev_m_f.empty:
                        try:
                            _pf_all = compute_all_prices_for_date(d, prev_df, dict(st.session_state.get('manual_bars', {})))
                            prev_rec_bar_f = _pf_all.get(rid, {}).get('bar')
                        except Exception:
                            prev_rec_bar_f = None
                is_trend_f = (prev_rec_bar_f is not None and
                              str(prev_rec_bar_f).strip() != str(rec_bar).strip())

                if fixed_override:
                    # 오버라이드 있음 — 초록 테두리로 표시
                    bg_f = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    style = (f"border:2px solid #2E7D32; padding:8px; text-align:center;"
                             f"background-color:{bg_f}; font-weight:bold;")
                    if _fovr_is_price:
                        ovr_price = int(str(fixed_override).strip())
                        cell_content = (f"⭐ <b>직접가격</b><br>"
                                        f"<span style='font-size:9px;color:#1B5E20;'>{ovr_price:,}</span><br>"
                                        f"<span style='font-size:8px;color:#555;'>권장:{rec_price:,}</span>")
                    else:
                        ovr_bar = str(fixed_override).strip().upper()
                        ovr_price_f = get_applied_price(rid, ovr_bar, d, current_df,
                                                        applied_rates, fallback=rec_price)
                        cell_content = (f"⭐ <b>{ovr_bar}</b><br>"
                                        f"<span style='font-size:9px;color:#1B5E20;'>{ovr_price_f:,}</span><br>"
                                        f"<span style='font-size:8px;color:#555;'>권장:{rec_bar}</span>")
                    tooltip_f = f"title='연동객실 수동오버라이드'"
                elif is_trend_f:
                    try:
                        _pnum = int(str(prev_rec_bar_f).replace('BAR',''))
                        _cnum = int(str(rec_bar).replace('BAR',''))
                        _farrow = "▲" if _cnum < _pnum else "▼"
                        _fborder = "#B71C1C" if _cnum < _pnum else "#0D47A1"
                    except Exception:
                        _farrow, _fborder = "▲", "#B71C1C"
                    bg_f = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    style = (f"border:1.5px solid {_fborder}; padding:8px; text-align:center;"
                             f"background-color: {bg_f}; font-weight:bold;")
                    cell_content = (f"{_farrow} <b style='font-size:13px;'>{rec_bar}</b><br>"
                                    f"<span style='font-size:9px;opacity:0.7;'>{prev_rec_bar_f}</span><br>"
                                    f"<span style='font-size:9px;'>{rec_price:,}</span>")
                    tooltip_f = f"title='이전 {prev_rec_bar_f} → 현재 {rec_bar}'"
                elif highlight_only_changes:
                    style = "border:1px solid #eee; padding:8px; text-align:center; background-color:#FAFAFA; color:#BBB;"
                    cell_content = f"<span style='font-size:10px;'>{rec_bar}</span>"
                    tooltip_f = ""
                else:
                    bg_f = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    style = f"border:1px solid #ddd; padding:8px; text-align:center; background-color:{bg_f};"
                    cell_content = f"<b>{rec_bar}</b><br><span style='font-size:9px;'>{rec_price:,}</span>"
                    tooltip_f = ""
                html += f"<td style='{style}' {tooltip_f}>{cell_content}</td>"
                continue

            # ── 기존 DYNAMIC 객실: 오버라이드 비교 로직 ──
            applied_info = applied_rates.get(date_str, {})
            applied_bar = applied_info.get('rooms', {}).get(rid)
            memo = applied_info.get('memo', '')
            applied_at = applied_info.get('applied_at_display', '')
            rec_at_apply = applied_info.get('rec_bar_at_apply', {}).get(rid)

            needs_review = bool(applied_bar and rec_at_apply and rec_at_apply != rec_bar)

            prev_rec_bar = None
            if prev_df is not None and not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    try:
                        _pd_all = compute_all_prices_for_date(d, prev_df, dict(st.session_state.get('manual_bars', {})))
                        prev_rec_bar = _pd_all.get(rid, {}).get('bar')
                    except Exception:
                        prev_rec_bar = None

            is_trend_changed = (prev_rec_bar is not None and
                                str(prev_rec_bar).strip() != str(rec_bar).strip())

            is_calm = (applied_bar and applied_bar == rec_bar and
                       not needs_review and not is_trend_changed)

            tip_parts = []
            if memo: tip_parts.append(f"📝 {memo}")
            if applied_at: tip_parts.append(f"⏰ {applied_at}")
            if needs_review: tip_parts.append(f"⚠️ 적용시점 권장: {rec_at_apply} → 현재 권장: {rec_bar}")
            if is_trend_changed: tip_parts.append(f"▲ 이전 권장: {prev_rec_bar} → 현재 권장: {rec_bar}")
            memo_text = " | ".join(tip_parts)
            tooltip = f"title='{memo_text}'" if memo_text else ""

            if not applied_bar:
                # ※ 수정: 기존에는 적용 BAR가 없으면 무조건 회색 '대기중'으로만 찍혀,
                #   권장 BAR가 직전 대비 바뀌어도 화면에 전혀 드러나지 않았습니다
                #   (is_trend_changed를 계산해 툴팁에만 넣고 시각 표시는 누락).
                #   연동 객실(GDB/GDF/FFD/FPT/PPV)은 오버라이드가 없어도 트렌드를
                #   색으로 보여줘서, 같은 표 안에서 두 그룹의 규칙이 달랐습니다.
                #   → 메인 5객실도 동일하게 트렌드를 표시합니다.
                if is_trend_changed:
                    _wp, _wc = bar_rank(prev_rec_bar), bar_rank(rec_bar)
                    _w_up = (_wp is not None and _wc is not None and _wc < _wp)
                    _w_arrow = "▲" if _w_up else "▼"
                    _w_border = "#B71C1C" if _w_up else "#0D47A1"
                    _w_bg = BAR_GRADIENT_COLORS.get(rec_bar, "#FFFFFF")
                    _w_fg = "#fff" if rec_bar in ("BAR0P", "BAR0", "BAR1", "BAR2", "BAR3") else "#222"
                    style = (f"border:1.5px solid {_w_border}; padding:8px; text-align:center; "
                             f"background-color:{_w_bg}; color:{_w_fg}; font-weight:bold;")
                    cell_content = (f"{_w_arrow} <b style='font-size:13px;'>{rec_bar}</b><br>"
                                    f"<span style='font-size:9px;opacity:0.75;'>{prev_rec_bar}</span><br>"
                                    f"<span style='font-size:8px;opacity:0.7;'>대기중</span>")
                else:
                    style = ("border:1px solid #ddd; padding:8px; text-align:center; "
                             "background-color: #FAFAFA; color: #999;")
                    cell_content = f"<span style='font-size:9px;'>대기중</span><br>{rec_bar}"
            elif needs_review:
                style = "border:2px solid #FF6F00; padding:8px; text-align:center; background-color: #FFF3E0; color: #E65100; font-weight:bold;"
                cell_content = f"⚠️ <b>{applied_bar}</b><br><span style='font-size:9px; color:#FF6F00;'>권장→{rec_bar}</span>"
            elif applied_bar == rec_bar:
                if highlight_only_changes and is_calm:
                    style = "border:1px solid #eee; padding:8px; text-align:center; background-color: #FAFAFA; color: #BBB;"
                    cell_content = f"<span style='font-size:10px;'>✓ {applied_bar}</span>"
                elif is_trend_changed:
                    style = "border:1.5px solid #2E7D32; padding:8px; text-align:center; background-color: #C8E6C9; color: #1B5E20; font-weight:bold;"
                    try:
                        _tn_p = int(str(prev_rec_bar).replace('BAR',''))
                        _tn_c = int(str(applied_bar).replace('BAR',''))
                        _t_arrow = "▲" if _tn_c < _tn_p else "▼"
                    except Exception:
                        _t_arrow = "▲"
                    cell_content = (f"{_t_arrow} <b style='font-size:13px;'>{applied_bar}</b><br>"
                                    f"<span style='font-size:9px;opacity:0.7;'>{prev_rec_bar}</span>")
                else:
                    style = "border:1px solid #ddd; padding:8px; text-align:center; background-color: #E8F5E9; color: #2E7D32;"
                    cell_content = f"✅ <b>{applied_bar}</b>"
            else:
                # 오버라이드 방향 구분: 고가유지(파랑) vs 저가오버라이드(주황)
                try:
                    _app_n = int(applied_bar.replace('BAR', ''))
                    _rec_n = int(rec_bar.replace('BAR', ''))
                    _keeping_high = _app_n < _rec_n  # 낮은 BAR 번호 = 높은 가격
                except Exception:
                    _keeping_high = False
                if _keeping_high:
                    style = ("border:1.5px solid #1565C0; padding:8px; text-align:center; "
                             "background-color:#E3F2FD; color:#0D47A1; font-weight:bold;")
                    cell_content = (f"<span style='font-size:9px;color:#90CAF9;"
                                    f"text-decoration:line-through;'>{rec_bar}</span><br>"
                                    f"🏷️ <b>{applied_bar}</b><br>"
                                    f"<span style='font-size:8px;color:#1565C0;'>고가유지</span>")
                else:
                    style = ("border:1.5px dashed #FF8F00; padding:8px; text-align:center; "
                             "background-color:#FFF3E0; color:#C62828;")
                    cell_content = (f"<span style='font-size:10px;text-decoration:line-through;"
                                    f"color:#999;'>{rec_bar}</span><br>⭐ <b>{applied_bar}</b>")

            html += f"<td style='{style}' {tooltip}>{cell_content}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html


# =============================================================================
# 4-C. 요금 적용 UI
# =============================================================================
def render_apply_rate_ui(current_df, applied_rates):
    if current_df.empty: return
    st.markdown("""<div style='margin-top:40px; margin-bottom:15px; font-weight:bold; font-size:18px; padding:10px; background:#FFF3E0; border-left:10px solid #FF6F00;'>⏰ 5. 예외 설정 — 특정 날짜 BAR 고정 (파일 재업로드 후에도 유지)</div>""", unsafe_allow_html=True)
    st.caption("🔧 특정 일자의 요금을 시스템 권장과 다르게 강제로 묶거나 인상할 때 사용합니다. "
               "여기서 설정한 예외는 이후 파일 재업로드·저장 시에도 유지되며, "
               "판도변화로 권장가가 예외가보다 높아질 경우 자동으로 권장가로 갱신됩니다.")

    all_dates_full = sorted(current_df['Date'].unique())
    today = date.today()

    # 필터 옵션
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

    dates = all_dates_full if include_past else [d for d in all_dates_full if d >= today]

    if only_overridden:
        overridden_dates = set()
        for d in dates:
            date_str = d.strftime('%Y-%m-%d')
            if applied_rates.get(date_str, {}).get('rooms'):
                overridden_dates.add(d)
        dates = sorted(overridden_dates)

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

    # 누적 날짜 선택
    st.markdown("##### 📅 적용할 날짜 누적 선택")
    st.caption("💡 아래 도구로 기간/일자를 **추가**하면 누적됩니다. 기간+기간, 기간+일자, 일자+일자 자유 조합 가능!")

    if '_picked_dates' not in st.session_state:
        st.session_state['_picked_dates'] = set()

    # 빠른 프리셋
    with st.container(border=True):
        st.markdown("**🎯 빠른 프리셋 (클릭 시 누적 추가)**")
        pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)

        def add_to_picked(new_dates):
            valid = []
            for d in new_dates:
                if d in dates:
                    if hasattr(d, 'date') and callable(getattr(d, 'date', None)):
                        valid.append(d.date())
                    else:
                        valid.append(d)
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
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_"):
                        del st.session_state[k]
                st.rerun()

    # 기간 추가
    with st.container(border=True):
        st.markdown("**📆 기간 추가 (시작일 ~ 종료일)** — 여러 번 누르면 여러 기간 누적!")
        rc1, rc2, rc3 = st.columns([2, 2, 1])
        with rc1:
            range_start = st.date_input("시작일", value=dates[0], min_value=dates[0], max_value=dates[-1], key="apply_range_start")
        with rc2:
            range_end = st.date_input("종료일", value=dates[-1], min_value=dates[0], max_value=dates[-1], key="apply_range_end")
        with rc3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 이 기간 추가", use_container_width=True, key="apply_range_btn", type="primary"):
                if range_start > range_end:
                    st.error("시작일이 종료일보다 늦습니다.")
                else:
                    new_dates = [d for d in dates if range_start <= d <= range_end]
                    add_to_picked(new_dates)
                    st.rerun()

    # 개별 일자 추가
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
                    if "apply_single_pick" in st.session_state:
                        del st.session_state["apply_single_pick"]
                    st.rerun()
                else:
                    st.warning("일자를 먼저 선택하세요.")

    selected_dates = sorted(st.session_state['_picked_dates'])

    if not selected_dates:
        return st.info("👆 위 도구로 날짜를 먼저 추가하세요. (기간/일자/프리셋 자유 조합)")

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

    # 빠른 채우기
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

    # 일괄 시프트
    st.markdown("**📈 일괄 시프트 (오버라이드 한번에 조정)**")
    sft_col1, sft_col2, sft_col3, sft_col4 = st.columns(4)

    def shift_bar(bar_str, step):
        if not bar_str or bar_str == "BAR0":
            return bar_str
        try:
            n = int(bar_str.replace("BAR", ""))
            new_n = max(1, min(8, n + step))
            return f"BAR{new_n}"
        except:
            return bar_str

    with sft_col1:
        if st.button("⬆️ 한 단계 인상 (BAR↓)", use_container_width=True, key="shift_up_1"):
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
        if st.button("⬇️ 한 단계 인하 (BAR↑)", use_container_width=True, key="shift_down_1"):
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

    # ── 연동 객실 수동 오버라이드 ──────────────────────────────────────────
    st.markdown("---")
    with st.expander("🔗 연동 객실 수동 오버라이드 (선택적)", expanded=False):
        st.caption(
            "GDB/GDF/FFD: 직접 가격(원) 입력. FPT/PPV: BAR 선택. "
            "비워두면 연동 산식 그대로. 저장 버튼은 아래 공통 버튼 사용."
        )

        price_rooms_fixed = ["GDB", "GDF", "FFD"]
        bar_rooms_fixed   = ["FPT", "PPV"]
        bar_options_with_empty = [""] + bar_options
        fixed_price_key = f"fxprice_{len(selected_dates)}_{safe_date_str}"
        fixed_bar_key   = f"fxbar_{len(selected_dates)}_{safe_date_str}"

        def _build_price_matrix():
            rows = []
            for rid in price_rooms_fixed:
                row = {"객실": rid}
                for d in selected_dates:
                    lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    existing = applied_rates.get(d.strftime('%Y-%m-%d'), {}).get('rooms', {}).get(rid)
                    row[lbl] = int(existing) if existing and str(existing).isdigit() else None
                rows.append(row)
            return rows

        def _build_bar_matrix():
            rows = []
            for rid in bar_rooms_fixed:
                row = {"객실": rid}
                for d in selected_dates:
                    lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                    existing = applied_rates.get(d.strftime('%Y-%m-%d'), {}).get('rooms', {}).get(rid)
                    row[lbl] = existing if existing in bar_options else ""
                rows.append(row)
            return rows

        if fixed_price_key not in st.session_state:
            st.session_state[fixed_price_key] = _build_price_matrix()
        if fixed_bar_key not in st.session_state:
            st.session_state[fixed_bar_key] = _build_bar_matrix()

        st.markdown("**GDB / GDF / FFD — 직접 가격 (원)**")
        pcfg = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
        for d in selected_dates:
            lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            pcfg[lbl] = st.column_config.NumberColumn(min_value=0, max_value=3000000, step=1000, width="small", format="%d원")
        edited_price_fx = st.data_editor(
            pd.DataFrame(st.session_state[fixed_price_key]),
            column_config=pcfg, use_container_width=True, hide_index=True,
            key="fx_price_editor"
        )

        st.markdown("**FPT / PPV — BAR 선택**")
        bcfg = {"객실": st.column_config.TextColumn(disabled=True, width="small")}
        for d in selected_dates:
            lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
            bcfg[lbl] = st.column_config.SelectboxColumn(options=bar_options_with_empty, required=False, width="small")
        edited_bar_fx = st.data_editor(
            pd.DataFrame(st.session_state[fixed_bar_key]),
            column_config=bcfg, use_container_width=True, hide_index=True,
            key="fx_bar_editor"
        )

        # 파싱 → applied_input에 병합
        _bad_price_inputs = []
        for _, row in edited_price_fx.iterrows():
            rid = row["객실"]
            for d in selected_dates:
                lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                val = row.get(lbl)
                if val is not None and pd.notna(val):
                    # ※ 수정: 기존에는 파싱 실패를 조용히 버려서 입력한 가격이
                    #   사라진 이유를 알 수 없었습니다.
                    try:
                        pval = int(float(val))
                    except (TypeError, ValueError):
                        _bad_price_inputs.append(f"{rid} {lbl}: '{val}'")
                        continue
                    if pval > 0:
                        if d not in applied_input: applied_input[d] = {}
                        applied_input[d][rid] = str(pval)
                    else:
                        _bad_price_inputs.append(f"{rid} {lbl}: '{val}' (0 이하)")
        if _bad_price_inputs:
            st.warning("⚠️ 숫자로 읽을 수 없어 무시된 직접가격 입력: " + ", ".join(_bad_price_inputs[:15]))

        for _, row in edited_bar_fx.iterrows():
            rid = row["객실"]
            for d in selected_dates:
                lbl = f"{d.strftime('%m-%d')}({WEEKDAYS_KR[d.weekday()]})"
                val = row.get(lbl)
                bval = str(val).strip().upper() if val and pd.notna(val) else ""
                if bval in bar_options:
                    if d not in applied_input: applied_input[d] = {}
                    applied_input[d][rid] = bval
    # ────────────────────────────────────────────────────────────────────────

    memo = st.text_area("📝 메모 (툴팁 표시용)", placeholder="예: 총지배인 지시로 유지 / 단체예약 있어서 조정 안함", key="apply_memo", height=70)

    # 저장 후 선택 초기화 옵션 (기본 ON → 순차 저장 편의)
    clear_after_save = st.checkbox(
        "💡 저장 후 날짜 선택 초기화 (다른 기간 이어서 저장할 때 편리)",
        value=True,
        key="apply_clear_after_save",
        help="ON: 저장 완료 후 선택 목록을 비워서 다음 기간을 새로 선택할 수 있습니다. "
             "OFF: 선택을 유지합니다."
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("💾 선택한 날짜 모두 적용 저장", type="primary", use_container_width=True, key="apply_save_btn"):
            # 저장 직전 복원 지점 자동 생성 (I 개선)
            try:
                if len(selected_dates) >= 3:  # 3일 이상 일괄 저장 시에만
                    create_restore_point(
                        label=f"적용 저장 직전 ({len(selected_dates)}일)",
                        trigger="before_apply_save",
                    )
            except: pass

            success_count, fail_count = 0, 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                if applied_input.get(d, {}):
                    rec_at_apply = {}
                    for rid in applied_input[d].keys():
                        rec_at_apply[rid] = rec_bar_map.get((rid, date_str), "BAR5")

                    prev_payload = applied_rates.get(date_str, {})
                    prev_rooms = prev_payload.get('rooms', {})
                    prev_rec_at_apply = prev_payload.get('rec_bar_at_apply', {})

                    if save_applied_rate(date_str, applied_input[d], memo, rec_at_apply,
                                         prev_rooms=prev_rooms, prev_rec_at_apply=prev_rec_at_apply):
                        success_count += 1
                    else:
                        fail_count += 1
            if success_count:
                _clear = st.session_state.get("apply_clear_after_save", True)
                if _clear:
                    st.success(f"✅ {success_count}일 저장 완료! 날짜 선택이 초기화됐습니다 — 다음 기간을 선택하세요.")
                    st.session_state['_picked_dates'] = set()
                else:
                    st.success(f"✅ {success_count}일 적용 완료! (선택 유지)")
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_") or k.startswith("_review_map_cache_"):
                        del st.session_state[k]
                st.rerun()
    with col2:
        if st.button("🗑️ 선택일 적용 기록 해제", use_container_width=True, key="apply_delete_btn"):
            try:
                if len(selected_dates) >= 3:
                    create_restore_point(
                        label=f"적용 해제 직전 ({len(selected_dates)}일)",
                        trigger="before_apply_delete",
                    )
            except: pass

            del_count = 0
            for d in selected_dates:
                date_str = d.strftime('%Y-%m-%d')
                prev_payload = applied_rates.get(date_str, {})
                if delete_applied_rate(date_str,
                                        prev_rooms=prev_payload.get('rooms', {}),
                                        prev_memo=prev_payload.get('memo', ''),
                                        prev_rec_at_apply=prev_payload.get('rec_bar_at_apply', {})):
                    del_count += 1
            if del_count:
                st.success(f"🗑️ {del_count}일 수동 적용 해제됨 (시스템 권장가로 원복) · 선택은 유지")
                for k in list(st.session_state.keys()):
                    if k.startswith("apply_matrix_data_") or k.startswith("_review_map_cache_"):
                        del st.session_state[k]
                st.rerun()


# =============================================================================
# 4-D. 채널 판매가 (요청 1 적용: items_override 파라미터)
# =============================================================================
def render_channel_sale_table(current_df, prev_df, ch_name, applied_rates, prev_applied_rates=None,
                              highlight_only_changes=True, focus_dates=None, items_override=None):
    """items_override: 외부에서 필터된 items 리스트를 직접 주입 (None이면 promotions에서 로드)"""
    if current_df.empty:
        return ""

    if items_override is not None:
        items_to_show = items_override
    else:
        items_to_show = st.session_state.promotions.get(ch_name, {}).get("items", [])

    if not items_to_show:
        return f"<div style='padding:10px; color:gray;'>👉 사이드바에서 {ch_name} 상품을 추가해주세요.</div>"

    if prev_applied_rates is None:
        prev_applied_rates = applied_rates

    use_focus = bool(focus_dates)
    if use_focus:
        normalized_focus = set()
        for fd in focus_dates:
            if hasattr(fd, 'date') and callable(getattr(fd, 'date', None)):
                normalized_focus.add(fd.date())
            else:
                normalized_focus.add(fd)
        focus_dates = normalized_focus

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

            _, rec_bar, _, _ = get_final_values(rid, d, avail, total)

            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
            is_applied = applied_bar is not None
            final_bar = applied_bar if is_applied else rec_bar
            base_price = (get_applied_price(rid, final_bar, d, current_df, applied_rates)
                          if is_applied else get_bar_price(rid, final_bar))

            prev_rec_bar = None
            if prev_df is not None and not prev_df.empty:
                prev_m = prev_df[(prev_df['RoomID'] == rid) & (prev_df['Date'] == d)]
                if not prev_m.empty:
                    try:
                        _pch_all = compute_all_prices_for_date(d, prev_df, dict(st.session_state.get('manual_bars', {})))
                        prev_rec_bar = _pch_all.get(rid, {}).get('bar')
                    except Exception:
                        prev_rec_bar = None

            is_trend_changed = (prev_rec_bar is not None and
                                str(prev_rec_bar).strip() != str(rec_bar).strip())

            needs_review = False
            if is_applied and rid in DYNAMIC_ROOMS:
                needs_review, _, _ = is_review_needed(rid, d, current_df, applied_rates)

            try:
                b_price = float(base_price) if base_price else 0
                after_disc = b_price * (1 - (discount / 100))
                final_p = int((math.floor(after_disc / 1000) * 1000) + add_price)

                is_strategic_override = is_applied and (applied_bar != rec_bar)
                is_calm = (not is_trend_changed and not needs_review and not is_strategic_override)

                d_key = d.date() if (hasattr(d, 'date') and callable(getattr(d, 'date', None))) else d
                is_out_of_focus = use_focus and (d_key not in focus_dates)

                if is_out_of_focus or (highlight_only_changes and is_calm):
                    tooltip = "title='수정 대상 외'" if is_out_of_focus else "title='수정 필요 없음'"
                    style = "background-color: #FAFAFA; color: #BBB; font-weight: normal; border: 1px solid #EEE; padding:4px; text-align:center;"
                    content = f"<span style='font-size:10px;'>{final_p:,}</span><br><span style='font-size:8px; color:#CCC;'>✓{final_bar}</span>"
                    html += f"<td style='{style}' {tooltip}>{content}</td>"
                    continue

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

                if is_applied and needs_review:
                    border_style = "border: 2px solid #FF6F00; box-shadow: inset 0 0 0 1px #FFD54F;"
                    icon = "⚠️"
                    label_color = "#FFF" if is_trend_changed else "#E65100"
                    bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>재검토:{final_bar}</span>"
                elif is_applied:
                    _memo_check = applied_rates.get(date_str, {}).get('memo', '')
                    _is_auto = isinstance(_memo_check, str) and _memo_check.startswith("[자동갱신]")
                    if _is_auto:
                        border_style = "border: 2px dashed #1565C0;"
                        icon = "🔄"
                        label_color = "#FFF" if is_trend_changed else "#1565C0"
                        bar_label = f"<span style='font-size:9px; color:{label_color}; font-weight:bold;'>자동:{final_bar}</span>"
                    else:
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


# =============================================================================
# 4-E. 내일 적용될 요금 미리보기 (D 개선)
# =============================================================================
def render_tomorrow_preview(current_df, applied_rates):
    """내일/모레/글피 3일치 요금을 한눈에 카드 형태로"""
    if current_df.empty:
        return

    st.markdown("""
    <div style='margin-top:30px; margin-bottom:15px; font-weight:bold; font-size:18px;
                padding:10px; background:#E1F5FE; border-left:10px solid #0288D1;'>
        🌅 D-Day 요금 미리보기 (오늘·내일·모레 CMS 반영가)
    </div>
    """, unsafe_allow_html=True)
    st.caption("매일 아침 첫 확인용. 어떤 셀이 강조 표시되었는지 빠르게 체크하세요.")

    targets = []
    for offset, label in [(0, "오늘"), (1, "내일"), (2, "모레")]:
        d = TODAY + timedelta(days=offset)
        if d in set(current_df['Date'].unique()):
            targets.append((d, label, offset))

    if not targets:
        st.info("📭 오늘~모레 데이터가 없습니다. 리포트를 업로드하세요.")
        return

    cols = st.columns(len(targets))
    for (d, label, offset), col in zip(targets, cols):
        with col:
            date_str = d.strftime('%Y-%m-%d')
            wd = WEEKDAYS_KR[d.weekday()]
            wd_color = "#D32F2F" if wd == "일" else ("#1976D2" if wd == "토" else "#333")

            applied_info = applied_rates.get(date_str, {})
            has_applied = bool(applied_info.get('rooms'))
            memo = applied_info.get('memo', '')

            card_html = f"""
            <div style='border:2px solid {"#0288D1" if offset==0 else "#90CAF9"}; border-radius:10px;
                        padding:10px; background:{"#E1F5FE" if offset==0 else "#F5F9FF"};
                        margin-bottom:10px;'>
                <div style='font-size:13px; color:#666;'>{label}</div>
                <div style='font-size:20px; font-weight:bold;'>{d.strftime('%m월 %d일')}
                    <span style='color:{wd_color}; font-size:14px;'>({wd})</span></div>
            """
            if has_applied:
                card_html += f"<div style='margin-top:5px; padding:3px 6px; background:#FFF3E0; border-radius:4px; font-size:11px; color:#E65100;'>⭐ 오버라이드 적용됨</div>"
            else:
                card_html += f"<div style='margin-top:5px; padding:3px 6px; background:#F1F8E9; border-radius:4px; font-size:11px; color:#558B2F;'>📊 시스템 권장가</div>"
            if memo:
                card_html += f"<div style='margin-top:5px; font-size:11px; color:#666;'>📝 {memo[:40]}</div>"
            card_html += "</div>"
            st.markdown(card_html, unsafe_allow_html=True)

            # 객실별 가격 미니 테이블
            rows_html = "<table style='width:100%; font-size:11px; border-collapse:collapse;'>"
            for rid in ALL_ROOMS:
                cm = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
                if cm.empty:
                    continue
                avail = cm.iloc[0]['Available']
                total = cm.iloc[0]['Total']
                _, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total)
                applied_bar = applied_info.get('rooms', {}).get(rid)
                if applied_bar:
                    final_bar = applied_bar
                    final_price = get_applied_price(rid, applied_bar, d, current_df,
                                                    applied_rates, fallback=rec_price)
                    star = "⭐"
                    color = "#D32F2F"
                else:
                    final_bar = rec_bar
                    final_price = rec_price
                    star = ""
                    color = "#333"
                bg = BAR_GRADIENT_COLORS.get(final_bar, "#FFF")
                rows_html += f"<tr><td style='padding:3px; border-bottom:1px solid #EEE;'><b>{rid}</b></td>"
                rows_html += f"<td style='padding:3px; border-bottom:1px solid #EEE; text-align:center; background:{bg};'>{final_bar}</td>"
                rows_html += f"<td style='padding:3px; border-bottom:1px solid #EEE; text-align:right; color:{color};'>{star}{final_price:,}</td></tr>"
            rows_html += "</table>"
            st.markdown(rows_html, unsafe_allow_html=True)


# =============================================================================
# 4-F. 객실별 7일 픽업 스파크라인 (E 개선)
# =============================================================================
def render_pickup_sparklines(current_df):
    """최근 N일 픽업 추세를 작은 차트로 보여줌 (data_editor의 LineChartColumn 활용)"""
    if current_df.empty:
        return
    st.markdown("""
    <div style='margin-top:30px; margin-bottom:15px; font-weight:bold; font-size:18px;
                padding:10px; background:#F3E5F5; border-left:10px solid #7B1FA2;'>
        📈 객실별 점유 추세 (스파크라인)
    </div>
    """, unsafe_allow_html=True)
    st.caption("앞으로 14일 점유율 추이 — 픽업이 가속되는 객실/날짜 패턴을 한눈에 파악")

    # 향후 14일 데이터 추출
    future_dates = sorted([d for d in current_df['Date'].unique() if d >= TODAY])[:14]
    if not future_dates:
        st.info("미래 데이터가 없습니다.")
        return

    rows = []
    for rid in ALL_ROOMS:
        occ_series = []
        avail_series = []
        for d in future_dates:
            m = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if m.empty:
                occ_series.append(0)
                avail_series.append(0)
                continue
            avail = m.iloc[0]['Available']
            total = m.iloc[0]['Total']
            try:
                a = float(avail) if pd.notna(avail) else 0.0
                occ = ((total - a) / total * 100) if total > 0 else 0
            except:
                occ = 0
                a = 0
            occ_series.append(round(occ, 1))
            avail_series.append(int(a))
        rows.append({
            "객실": rid,
            "점유율 추이(%)": occ_series,
            "잔여실 추이": avail_series,
            "현재 점유율": occ_series[0] if occ_series else 0,
            "평균 점유율": round(sum(occ_series) / len(occ_series), 1) if occ_series else 0,
        })

    df_spark = pd.DataFrame(rows)
    st.data_editor(
        df_spark,
        use_container_width=True,
        hide_index=True,
        disabled=True,
        column_config={
            "객실": st.column_config.TextColumn(width="small"),
            "점유율 추이(%)": st.column_config.LineChartColumn(
                "점유율 추이(%)",
                width="medium",
                y_min=0,
                y_max=100,
            ),
            "잔여실 추이": st.column_config.LineChartColumn(
                "잔여실 추이",
                width="medium",
            ),
            "현재 점유율": st.column_config.NumberColumn(format="%.1f%%"),
            "평균 점유율": st.column_config.NumberColumn(format="%.1f%%"),
        },
        key="sparkline_editor",
    )


# =============================================================================
# 4-G. 모바일 카드 뷰 (G 개선)
# =============================================================================
def render_mobile_card_view(current_df, applied_rates):
    """모바일 친화적 3일 카드 뷰 (가로 스크롤 매트릭스 대안)"""
    if current_df.empty:
        return
    st.markdown("""
    <div style='margin-top:20px; margin-bottom:10px; font-weight:bold; font-size:16px;
                padding:8px; background:#FFF8E1; border-left:6px solid #FFA000;'>
        📱 모바일 뷰 (오늘부터 N일 카드 형태)
    </div>
    """, unsafe_allow_html=True)
    st.caption("출장지/회의 중 빠른 확인용. 표 대신 카드로 봅니다.")

    n_days = st.slider("표시 일수", 1, 7, 3, key="mobile_days_slider")

    target_dates = sorted([d for d in current_df['Date'].unique() if d >= TODAY])[:n_days]
    if not target_dates:
        st.info("표시할 미래 데이터가 없습니다.")
        return

    for d in target_dates:
        date_str = d.strftime('%Y-%m-%d')
        wd = WEEKDAYS_KR[d.weekday()]
        wd_color = "#D32F2F" if wd == "일" else ("#1976D2" if wd == "토" else "#333")
        is_today = (d == TODAY)
        applied_info = applied_rates.get(date_str, {})
        memo = applied_info.get('memo', '')

        st.markdown(f"""
        <div style='border:2px solid {"#0288D1" if is_today else "#CFD8DC"}; border-radius:10px;
                    padding:10px; margin:10px 0; background:{"#E1F5FE" if is_today else "#FAFAFA"};'>
            <div style='display:flex; justify-content:space-between; align-items:center;'>
                <span style='font-size:18px; font-weight:bold;'>
                    {d.strftime('%m월 %d일')} <span style='color:{wd_color};'>({wd})</span>
                    {"🌟 오늘" if is_today else ""}
                </span>
                <span style='font-size:11px; color:#666;'>{memo[:30] if memo else ""}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        for rid in ALL_ROOMS:
            cm = current_df[(current_df['RoomID'] == rid) & (current_df['Date'] == d)]
            if cm.empty: continue
            avail = cm.iloc[0]['Available']
            total = cm.iloc[0]['Total']
            occ, rec_bar, rec_price, _ = get_final_values(rid, d, avail, total)
            applied_bar = applied_info.get('rooms', {}).get(rid)
            if applied_bar:
                final_bar = applied_bar
                final_price = get_applied_price(rid, applied_bar, d, current_df,
                                                applied_rates, fallback=rec_price)
                mark = "⭐"
                badge_bg = "#FFEBEE"
                badge_color = "#C62828"
            else:
                final_bar = rec_bar
                final_price = rec_price
                mark = ""
                badge_bg = "#E8F5E9"
                badge_color = "#2E7D32"

            bg_bar = BAR_GRADIENT_COLORS.get(final_bar, "#F5F5F5")

            try:
                avail_int = int(float(avail)) if pd.notna(avail) else 0
            except:
                avail_int = 0

            st.markdown(f"""
            <div style='display:flex; justify-content:space-between; align-items:center;
                        padding:6px 12px; border-bottom:1px solid #EEE; background:white;'>
                <div style='font-weight:bold; min-width:50px;'>{rid}</div>
                <div style='background:{bg_bar}; padding:2px 8px; border-radius:4px; font-size:12px; min-width:50px; text-align:center;'>{final_bar}</div>
                <div style='font-size:13px;'>{mark}<b>{final_price:,}</b></div>
                <div style='background:{badge_bg}; color:{badge_color}; padding:2px 6px; border-radius:4px; font-size:11px;'>잔{avail_int}/점{occ:.0f}%</div>
            </div>
            """, unsafe_allow_html=True)


# =============================================================================
# 4-H. 변경 이력 조회 UI (C 개선)
# =============================================================================

# =============================================================================
# 오버라이드 → 권장값 초기화 UI
# =============================================================================
def render_reset_override_ui(current_df, applied_rates):
    """저장된 오버라이드를 시스템 권장값으로 초기화하는 UI."""
    st.subheader("🔄 오버라이드 → 권장값으로 초기화")

    all_ovr = sorted([d for d, v in applied_rates.items() if v.get('rooms')])
    if not all_ovr:
        st.info("현재 저장된 오버라이드가 없습니다.")
        return

    st.caption(f"현재 오버라이드 적용 날짜: **{len(all_ovr)}일**")

    mode = st.radio(
        "초기화 대상 설정",
        ["전체", "특정일 지정", "특정기간 지정"],
        horizontal=True,
        key="rov_mode"
    )

    if 'rov_incl' not in st.session_state:
        st.session_state['rov_incl'] = []
    if 'rov_excl' not in st.session_state:
        st.session_state['rov_excl'] = []

    target = set()

    if mode == "전체":
        target = set(all_ovr)
        with st.expander("➖ 특정일/기간 제외 설정"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**날짜 단위 제외**")
                ed = st.date_input("제외 날짜", key="rov_excl_d",
                                   min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))
                if st.button("➕ 날짜 제외 추가", key="rov_add_ed"):
                    ds = ed.strftime('%Y-%m-%d')
                    if ds not in st.session_state['rov_excl']:
                        st.session_state['rov_excl'].append(ds)
                        st.rerun()
            with c2:
                st.markdown("**기간 단위 제외**")
                er_s = st.date_input("제외 시작", key="rov_excl_rs",
                                     min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))
                er_e = st.date_input("제외 종료", key="rov_excl_re",
                                     min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))
                if st.button("➕ 기간 제외 추가", key="rov_add_er"):
                    if er_s <= er_e:
                        cur = er_s
                        while cur <= er_e:
                            ds2 = cur.strftime('%Y-%m-%d')
                            if ds2 not in st.session_state['rov_excl']:
                                st.session_state['rov_excl'].append(ds2)
                            cur += timedelta(days=1)
                        st.rerun()
                    else:
                        st.error("시작일이 종료일보다 늦습니다.")
            if st.session_state['rov_excl']:
                excl_sorted = sorted(st.session_state['rov_excl'])
                st.markdown(f"**제외 목록 ({len(excl_sorted)}일):**")
                st.caption(", ".join(excl_sorted[:20]) + ("..." if len(excl_sorted) > 20 else ""))
                if st.button("🗑 제외 목록 전체 삭제", key="rov_clear_excl"):
                    st.session_state['rov_excl'] = []
                    st.rerun()
        target -= set(st.session_state['rov_excl'])

    elif mode == "특정일 지정":
        c1, c2 = st.columns([3, 1])
        with c1:
            sd = st.date_input("날짜 선택", key="rov_incl_d",
                               min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))
        with c2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 추가", key="rov_add_incl"):
                ds = sd.strftime('%Y-%m-%d')
                if ds not in st.session_state['rov_incl']:
                    st.session_state['rov_incl'].append(ds)
                    st.rerun()
        if st.session_state['rov_incl']:
            incl_sorted = sorted(st.session_state['rov_incl'])
            st.markdown(f"**추가된 날짜 ({len(incl_sorted)}일):**")
            st.caption(", ".join(incl_sorted))
            if st.button("🗑 목록 초기화", key="rov_clear_incl"):
                st.session_state['rov_incl'] = []
                st.rerun()
        target = set(st.session_state['rov_incl']) & set(all_ovr)

    elif mode == "특정기간 지정":
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            rs = st.date_input("시작일", key="rov_range_s",
                               min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))
        with c2:
            re_ = st.date_input("종료일", key="rov_range_e",
                                min_value=date(2025, 1, 1), max_value=date(2027, 12, 31))
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 기간 추가", key="rov_add_range"):
                if rs <= re_:
                    cur = rs
                    while cur <= re_:
                        ds = cur.strftime('%Y-%m-%d')
                        if ds not in st.session_state['rov_incl']:
                            st.session_state['rov_incl'].append(ds)
                        cur += timedelta(days=1)
                    st.rerun()
                else:
                    st.error("시작일이 종료일보다 늦습니다.")
        if st.session_state['rov_incl']:
            incl_sorted = sorted(st.session_state['rov_incl'])
            st.markdown(f"**선택된 날짜 ({len(incl_sorted)}일):**")
            st.caption(", ".join(incl_sorted[:30]) + ("..." if len(incl_sorted) > 30 else ""))
            if st.button("🗑 목록 초기화", key="rov_clear_range"):
                st.session_state['rov_incl'] = []
                st.rerun()
        target = set(st.session_state['rov_incl']) & set(all_ovr)

    final = sorted(target)
    if final:
        st.info(f"초기화 대상: **{len(final)}일** — 오버라이드 삭제 → 시스템 권장값 자동 적용")
        with st.expander("📋 대상 날짜 전체 확인"):
            st.write(", ".join(final))
        if st.button("🔄 권장값으로 변경 저장", type="primary", key="rov_save"):
            prog = st.progress(0)
            ok_count = 0
            for i, date_str in enumerate(final):
                prev_info = applied_rates.get(date_str, {})
                if delete_applied_rate(
                    date_str,
                    prev_rooms=prev_info.get('rooms', {}),
                    prev_memo=prev_info.get('memo', ''),
                    prev_rec_at_apply=prev_info.get('rec_bar_at_apply'),
                ):
                    ok_count += 1
                prog.progress((i + 1) / len(final))
            st.success(f"✅ {ok_count}일 초기화 완료")
            st.session_state['rov_incl'] = []
            st.session_state['rov_excl'] = []
            st.cache_data.clear()
            st.rerun()
    else:
        st.caption("날짜를 추가하면 초기화 버튼이 활성화됩니다.")


# =============================================================================
# 전체 BAR 캘린더 (6/21 ~ 12/31)
# =============================================================================
def render_bar_calendar_table(current_df, applied_rates):
    """6/21~12/31 최종 확정 요금 BAR 캘린더. 같은 BAR는 같은 색상."""
    st.subheader("📅 전체 요금 BAR 캘린더 (6/21 ~ 12/31)")
    st.caption("오버라이드 저장 완료 후 새로고침 시 최종 확정 요금 반영. 주황 테두리 = 오버라이드 적용 셀.")

    if current_df is None or current_df.empty:
        st.warning("데이터가 없습니다. 파일을 먼저 업로드해 주세요.")
        return

    cal_start = date(TODAY.year, 6, 21)
    cal_end   = date(TODAY.year, 12, 31)
    all_dates = []
    d = cal_start
    while d <= cal_end:
        all_dates.append(d)
        d += timedelta(days=1)

    rooms = ALL_ROOMS
    parts = [
        '<div style="overflow-x:auto;font-size:11px;margin-top:8px;">',
        '<table style="border-collapse:collapse;white-space:nowrap;min-width:max-content;">',
        '<thead><tr style="background:#1A237E;color:white;">',
        '<th style="padding:5px 8px;border:1px solid #3949AB;min-width:72px;">날짜</th>',
        '<th style="padding:5px 5px;border:1px solid #3949AB;min-width:28px;">요일</th>',
    ]
    for rid in rooms:
        parts.append(f'<th style="padding:5px 8px;border:1px solid #3949AB;min-width:70px;">{rid}</th>')
    parts.append('</tr></thead><tbody>')

    for d in all_dates:
        date_str = d.strftime('%Y-%m-%d')
        wd = WEEKDAYS_KR[d.weekday()]
        is_we = d.weekday() in [4, 5]
        is_today = (d == TODAY)
        row_bg = "#FFF8E1" if is_we else ("#E3F2FD" if is_today else "white")
        wd_color = "#E53935" if is_we else ("#1565C0" if is_today else "#555")

        parts.append(f'<tr style="background:{row_bg};">')
        parts.append(
            f'<td style="padding:3px 7px;border:1px solid #ddd;font-weight:{"bold" if is_we or is_today else "normal"};">'
            f'{"⭐ " if is_today else ""}{date_str[5:]}</td>'
        )
        parts.append(
            f'<td style="padding:3px 4px;border:1px solid #ddd;text-align:center;color:{wd_color};'
            f'font-weight:{"bold" if is_we else "normal"};">{wd}</td>'
        )

        rec_all = compute_all_prices_for_date(d, current_df)
        for rid in rooms:
            applied_bar = applied_rates.get(date_str, {}).get('rooms', {}).get(rid)
            bar = applied_bar if applied_bar else (rec_all.get(rid) or {}).get('bar', '-')
            is_ovr = bool(applied_bar)
            price = (get_applied_price(rid, bar, d, current_df, applied_rates)
                     if is_ovr else ((rec_all.get(rid) or {}).get('price', 0) or 0))
            price_str = f"{price // 1000}k" if price else "-"
            bg = BAR_GRADIENT_COLORS.get(bar, "#EEE")
            tc = "white" if bar in ("BAR0P", "BAR0", "BAR1", "BAR2", "BAR3") else "#333"
            border = "border:2.5px solid #FF8F00;" if is_ovr else "border:1px solid #ddd;"
            parts.append(
                f'<td style="padding:3px 5px;{border}background:{bg};color:{tc};text-align:center;">'
                f'<span style="font-size:10px;font-weight:bold;">{bar}</span><br>'
                f'<span style="font-size:9px;opacity:0.88;">{price_str}</span></td>'
            )
        parts.append('</tr>')

    parts.append('</tbody></table></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)

    leg = ['<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;">']
    for bar in BAR_ORDER:
        bg = BAR_GRADIENT_COLORS.get(bar, "#eee")
        tc = "white" if bar in ("BAR0P", "BAR0", "BAR1", "BAR2", "BAR3") else "#333"
        leg.append(f'<span style="background:{bg};color:{tc};padding:3px 10px;border-radius:4px;font-size:11px;font-weight:bold;">{bar}</span>')
    leg.append('<span style="border:2.5px solid #FF8F00;padding:3px 8px;border-radius:4px;font-size:11px;">주황 테두리 = 오버라이드</span>')
    leg.append('</div>')
    st.markdown("".join(leg), unsafe_allow_html=True)


# =============================================================================
# 4-Z. 구/신 요금 곡선 비교 (2단계 안전장치)
# =============================================================================
def compute_prices_both_versions(current_df, manual_bars):
    """전 날짜·전 객실에 대해 구 곡선(V1)과 신 곡선(V2) 요금을 동시 산출.
    반환: (DataFrame, 요약dict)"""
    global _PRICING_V2
    dates = sorted(current_df['Date'].unique())
    saved = _PRICING_V2
    out = {}
    try:
        for ver, flag in (("v1", False), ("v2", True)):
            _PRICING_V2 = flag
            _price_cache.clear()
            for d in dates:
                try:
                    res = compute_all_prices_for_date(d, current_df, manual_bars)
                except Exception:
                    continue
                for rid, info in res.items():
                    out.setdefault((d, rid), {})[ver] = info
    finally:
        _PRICING_V2 = saved
        _price_cache.clear()

    rows = []
    for (d, rid), v in sorted(out.items(), key=lambda x: (x[0][0], ALL_ROOMS.index(x[0][1]) if x[0][1] in ALL_ROOMS else 99)):
        a, b = v.get("v1"), v.get("v2")
        if not a or not b:
            continue
        rows.append({
            "날짜": d.strftime('%Y-%m-%d'),
            "요일": WEEKDAYS_KR[d.weekday()],
            "객실": rid,
            "OCC(%)": round(b.get('occ', 0), 0),
            "구BAR": a.get('bar'),
            "구요금": int(a.get('price') or 0),
            "신BAR": b.get('bar'),
            "신요금": int(b.get('price') or 0),
            "차액": int((b.get('price') or 0) - (a.get('price') or 0)),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df, {}
    df["변동률(%)"] = (df["차액"] / df["구요금"].replace(0, pd.NA) * 100).round(1)
    summary = {
        "총 셀": len(df),
        "변경 셀": int((df["차액"] != 0).sum()),
        "인상 셀": int((df["차액"] > 0).sum()),
        "인하 셀": int((df["차액"] < 0).sum()),
        "구 평균요금": int(df["구요금"].mean()),
        "신 평균요금": int(df["신요금"].mean()),
    }
    summary["평균 변동"] = summary["신 평균요금"] - summary["구 평균요금"]
    summary["평균 변동률(%)"] = round(
        summary["평균 변동"] / summary["구 평균요금"] * 100, 1) if summary["구 평균요금"] else 0
    return df, summary


def render_pricing_compare_ui(current_df):
    """구/신 요금 곡선 비교 패널 — 곡선을 바꾸기 전 실제 데이터로 영향 확인."""
    with st.expander("🔬 구/신 요금 곡선 비교 (실제 업로드 데이터 기준)", expanded=False):
        st.caption(
            f"현재 요금 로직: **{'신(V2)' if _PRICING_V2 else '구(V1)'}** — "
            f"코드 상단 `_PRICING_V2` 값으로 전환합니다. "
            f"아래 표는 같은 재고 데이터에 두 곡선을 각각 적용한 결과입니다."
        )
        if current_df.empty:
            st.info("데이터를 업로드하면 비교표가 나타납니다.")
            return
        if not st.button("🔍 비교 실행", use_container_width=True, key="run_pricing_compare"):
            st.caption("※ 전 날짜 × 전 객실을 두 번 계산하므로 버튼을 눌러야 실행됩니다.")
            return

        df, summ = compute_prices_both_versions(current_df, dict(st.session_state.get('manual_bars', {})))
        if df.empty:
            st.warning("비교할 데이터가 없습니다.")
            return

        c = st.columns(4)
        c[0].metric("평균 요금", f"{summ['신 평균요금']:,}원",
                    f"{summ['평균 변동']:+,}원 ({summ['평균 변동률(%)']:+}%)")
        c[1].metric("변경 셀", f"{summ['변경 셀']:,} / {summ['총 셀']:,}")
        c[2].metric("인상", f"{summ['인상 셀']:,}건")
        c[3].metric("인하", f"{summ['인하 셀']:,}건")

        # 객실별 요약
        by_room = df.groupby("객실", as_index=False).agg(
            구평균=("구요금", "mean"), 신평균=("신요금", "mean"), 평균차액=("차액", "mean"))
        for col in ("구평균", "신평균", "평균차액"):
            by_room[col] = by_room[col].round(0).astype(int)
        by_room["변동률(%)"] = (by_room["평균차액"] / by_room["구평균"].replace(0, pd.NA) * 100).round(1)
        by_room["객실"] = pd.Categorical(by_room["객실"], categories=ALL_ROOMS, ordered=True)
        st.markdown("**객실별 평균 영향**")
        st.dataframe(by_room.sort_values("객실"), use_container_width=True, hide_index=True)

        # 날짜별 요약
        by_date = df.groupby(["날짜", "요일"], as_index=False).agg(
            구평균=("구요금", "mean"), 신평균=("신요금", "mean"))
        by_date["평균차액"] = (by_date["신평균"] - by_date["구평균"]).round(0).astype(int)
        by_date["변동률(%)"] = (by_date["평균차액"] / by_date["구평균"].replace(0, pd.NA) * 100).round(1)
        for col in ("구평균", "신평균"):
            by_date[col] = by_date[col].round(0).astype(int)
        st.markdown("**날짜별 평균 영향**")
        st.dataframe(by_date, use_container_width=True, hide_index=True)

        only_changed = st.checkbox("변경된 셀만 보기", value=True, key="cmp_only_changed")
        detail = df[df["차액"] != 0] if only_changed else df
        st.markdown(f"**셀 단위 상세 ({len(detail):,}건)**")
        st.dataframe(detail, use_container_width=True, hide_index=True, height=420)

        buf = io.BytesIO()
        with pd.ExcelWriter(buf) as w:
            df.to_excel(w, index=False, sheet_name="셀상세")
            by_room.sort_values("객실").to_excel(w, index=False, sheet_name="객실별")
            by_date.to_excel(w, index=False, sheet_name="날짜별")
        st.download_button("📥 비교 결과 엑셀 다운로드", data=buf.getvalue(),
                           file_name=f"요금곡선비교_{date.today().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_pricing_compare")


def render_audit_log_ui():
    """변경 이력 조회 화면"""
    with st.expander("📋 변경 이력 (Audit Log)", expanded=False):
        st.caption("모든 적용/해제/일괄삭제/복원 기록이 무제한 보존됩니다.")

        col1, col2, col3 = st.columns(3)
        with col1:
            action_filter = st.selectbox(
                "액션 필터",
                ["전체", "apply_save", "apply_delete", "bulk_delete", "restore", "restore_create"],
                key="audit_action_filter"
            )
        with col2:
            date_from = st.date_input("대상 날짜 From", value=date.today() - timedelta(days=30),
                                       key="audit_date_from")
        with col3:
            date_to = st.date_input("대상 날짜 To", value=date.today() + timedelta(days=90),
                                     key="audit_date_to")

        limit = st.slider("최대 표시 건수", 50, 1000, 200, step=50, key="audit_limit")

        if st.button("🔍 이력 조회", use_container_width=True, key="audit_search_btn"):
            st.session_state['_audit_loaded'] = True

        if st.session_state.get('_audit_loaded'):
            logs = load_audit_log(
                limit=limit,
                action_filter=None if action_filter == "전체" else action_filter,
                date_from_str=date_from.strftime("%Y-%m-%d") if date_from else None,
                date_to_str=date_to.strftime("%Y-%m-%d") if date_to else None,
            )

            if not logs:
                st.info("조회된 이력이 없습니다.")
            else:
                st.success(f"📜 총 {len(logs)}건")

                # 표 형태로 변환
                table_rows = []
                for log in logs:
                    diffs_str = ""
                    for diff in log.get('diffs', [])[:5]:
                        diffs_str += f"{diff.get('room','')}:{diff.get('from','-')}→{diff.get('to','-')} | "
                    if len(log.get('diffs', [])) > 5:
                        diffs_str += f"...외 {len(log['diffs'])-5}건"
                    table_rows.append({
                        "시각": log.get('logged_at_display', ''),
                        "액션": log.get('action', ''),
                        "대상 날짜": log.get('target_date', ''),
                        "변경 내역": diffs_str[:200],
                        "메모": (log.get('memo') or '')[:60],
                    })
                df_log = pd.DataFrame(table_rows)
                st.dataframe(df_log, use_container_width=True, hide_index=True, height=400)

        st.divider()
        st.markdown("**🧹 이력 정리 (무제한 보존 → 수동 정리)**")
        cc1, cc2 = st.columns(2)
        with cc1:
            cleanup_before = st.date_input("이 날짜 이전 이력 삭제",
                                            value=date.today() - timedelta(days=180),
                                            key="audit_cleanup_before")
        with cc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ 정리 실행", key="audit_cleanup_btn"):
                cnt = cleanup_audit_log(before_date_str=cleanup_before.strftime("%Y-%m-%d"))
                st.success(f"✅ {cnt}건 정리 완료")
                st.rerun()


# =============================================================================
# 4-I. 복원 지점 UI (I 개선)
# =============================================================================
def render_restore_point_ui():
    """복원 지점 관리 화면"""
    with st.expander("🛟 복원 지점 (Restore Points)", expanded=False):
        st.caption("일괄 삭제·시프트·저장 직전에 자동 백업되며, 수동으로도 만들 수 있습니다.")

        # 수동 백업 생성
        col1, col2 = st.columns([3, 1])
        with col1:
            manual_label = st.text_input("백업 라벨 (수동 생성)",
                                          placeholder="예: 단체예약 반영 전 / 분기 시작 / ...",
                                          key="restore_manual_label")
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📸 지금 백업", use_container_width=True, key="restore_create_btn"):
                ok, ts = create_restore_point(label=manual_label or "수동 백업", trigger="manual")
                if ok:
                    log_audit(action="restore_create", target_date="*",
                              new_rooms={}, memo=manual_label or "수동 백업")
                    st.success(f"✅ 백업 완료 ({ts})")
                    st.rerun()

        st.divider()

        # 백업 목록
        points = load_restore_points(limit=50)
        if not points:
            st.info("아직 저장된 복원 지점이 없습니다.")
        else:
            st.markdown(f"**💾 저장된 복원 지점 ({len(points)}개)**")
            for p in points[:20]:  # 최근 20개만 화면에
                with st.container(border=True):
                    pc1, pc2, pc3, pc4 = st.columns([3, 2, 1, 1])
                    with pc1:
                        st.markdown(f"**{p.get('label','(라벨 없음)')}**")
                        st.caption(f"트리거: {p.get('trigger','?')} · 적용 날짜 {p.get('applied_count',0)}개")
                    with pc2:
                        st.markdown(f"🕒 {p.get('created_at_display','')}")
                    with pc3:
                        if st.button("↩️ 복원", key=f"restore_btn_{p['_id']}", use_container_width=True):
                            st.session_state['_pending_restore'] = p['_id']
                            st.session_state['_pending_restore_label'] = p.get('label', '')
                            st.rerun()
                    with pc4:
                        if st.button("🗑️", key=f"restore_del_{p['_id']}", use_container_width=True,
                                      help="이 복원 지점 삭제"):
                            delete_restore_point(p['_id'])
                            st.rerun()

        # 복원 확인 다이얼로그
        if st.session_state.get('_pending_restore'):
            st.warning(f"⚠️ 정말 복원하시겠습니까? '{st.session_state.get('_pending_restore_label','')}'\n\n현재 적용 요금이 모두 백업 시점으로 덮어쓰여집니다. (직전 상태도 자동 백업됨)")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("✅ 예, 복원 실행", type="primary", use_container_width=True, key="restore_confirm"):
                    ok, msg = restore_from_point(st.session_state['_pending_restore'])
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(msg)
                    del st.session_state['_pending_restore']
                    if '_pending_restore_label' in st.session_state:
                        del st.session_state['_pending_restore_label']
                    st.rerun()
            with cc2:
                if st.button("❌ 취소", use_container_width=True, key="restore_cancel"):
                    del st.session_state['_pending_restore']
                    if '_pending_restore_label' in st.session_state:
                        del st.session_state['_pending_restore_label']
                    st.rerun()

        st.divider()
        st.markdown("**🧹 복원 지점 정리**")
        rc1, rc2 = st.columns(2)
        with rc1:
            rp_cleanup_before = st.date_input("이 날짜 이전 복원 지점 삭제",
                                               value=date.today() - timedelta(days=90),
                                               key="rp_cleanup_before")
        with rc2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️ 복원 지점 정리", key="rp_cleanup_btn"):
                cnt = cleanup_restore_points(before_date_str=rp_cleanup_before.strftime("%Y-%m-%d"))
                st.success(f"✅ {cnt}개 정리 완료")
                st.rerun()


# =============================================================================
# 5. 파서 및 DB 로직
# =============================================================================
def robust_date_parser(d_val):
    """엑셀 헤더의 날짜 값을 date로 변환.

    ※ 수정 3건 (기존 버그):
      1) 연도가 date(2026, ...)로 하드코딩되어 2027년 예약은 전부 오답이었습니다.
         → 오늘 기준 -180일 ~ +400일 창에 들어가는 연도를 추론합니다.
         (12월 업로드분의 1월 날짜가 작년으로 잡히는 문제도 함께 해결)
      2) 엑셀 셀이 '진짜 날짜 서식'이면 Timestamp가 되고, str()이
         '2026-08-18 00:00:00' → 정규식이 '26-08'을 잡아 date(2026, 26, 8) →
         ValueError → None. 해당 날짜 열이 통째로 누락됐습니다.
         → datetime/date/Timestamp를 먼저 그대로 받습니다.
      3) 'YYYY-MM-DD' 문자열도 같은 이유로 None이었습니다. → 전체 파싱 우선 시도.
    """
    if d_val is None:
        return None
    try:
        if pd.isna(d_val):
            return None
    except (TypeError, ValueError):
        pass

    # 1) 날짜/시각 객체는 그대로
    if isinstance(d_val, pd.Timestamp):
        return d_val.date()
    if isinstance(d_val, datetime):
        return d_val.date()
    if isinstance(d_val, date):
        return d_val

    # 2) 엑셀 시리얼 번호
    if isinstance(d_val, (int, float)) and not isinstance(d_val, bool):
        try:
            return (pd.to_datetime('1899-12-30') + pd.to_timedelta(float(d_val), 'D')).date()
        except (ValueError, OverflowError):
            return None

    s = str(d_val).strip()
    if not s:
        return None

    # 3) 완전한 날짜 문자열 우선 (YYYY-MM-DD, YYYY.MM.DD, 2026년 8월 18일 등)
    ym = re.search(r'(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})', s)
    if ym:
        try:
            return date(int(ym.group(1)), int(ym.group(2)), int(ym.group(3)))
        except ValueError:
            return None

    # 4) MM-DD 형식 → 연도 추론
    s2 = s.replace('.', '-').replace('/', '-').replace(' ', '')
    m = re.search(r'(\d{1,2})-(\d{1,2})', s2)
    if not m:
        return None
    mo, dy = int(m.group(1)), int(m.group(2))
    for cand_year in (TODAY.year, TODAY.year + 1, TODAY.year - 1):
        try:
            c = date(cand_year, mo, dy)
        except ValueError:
            continue
        if -180 <= (c - TODAY).days <= 400:
            return c
    return None


def save_channel_configs():
    db.collection(COL_SETTINGS).document("channels").set({"channel_list": st.session_state.channel_list, "promotions": st.session_state.promotions})


def load_channel_configs():
    doc = db.collection(COL_SETTINGS).document("channels").get()
    if doc.exists:
        d = doc.to_dict()
        st.session_state.channel_list = d.get("channel_list", [])
        st.session_state.promotions = d.get("promotions", {})
    else:
        st.session_state.channel_list = []
        st.session_state.promotions = {}


def get_latest_snapshot():
    docs = db.collection(COL_SNAPSHOTS).order_by("save_time", direction=firestore.Query.DESCENDING).limit(1).stream()
    for doc in docs:
        d_dict = doc.to_dict()
        df = pd.DataFrame(d_dict['data'])
        if not df.empty and 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.date
        return df, d_dict.get('work_date', '알수없음')
    return pd.DataFrame(), None


# =============================================================================
# 6. 메인 UI
# =============================================================================
st.set_page_config(layout="wide")
st.title("🏨 엠버퓨어힐 전략 통합 수익관리 시스템")

# 가격 무결성 검증 (F 개선) - 앱 시작 시 1회
price_warnings = validate_price_tables()
if price_warnings:
    with st.expander(f"🚨 가격표 무결성 경고 {len(price_warnings)}건", expanded=False):
        for w in price_warnings:
            st.markdown(w)
        st.caption("⚠️ PRICE_TABLE 또는 FIXED_PRICE_TABLE을 점검하세요.")

if 'channel_list' not in st.session_state: load_channel_configs()
if 'today_df' not in st.session_state: st.session_state.today_df = pd.DataFrame()
if 'prev_df' not in st.session_state: st.session_state.prev_df = pd.DataFrame()
if 'compare_label' not in st.session_state: st.session_state.compare_label = ""
if 'manual_bars' not in st.session_state: st.session_state.manual_bars = {}
# 신규 5객실 추가 후 세션 캐시 리셋: room_filter_4가 FIXED_ROOMS를 포함하지 않으면 ALL_ROOMS로 재초기화
if 'room_filter_4' in st.session_state:
    cached = st.session_state.get('room_filter_4', [])
    if not any(r in cached for r in FIXED_ROOMS):
        del st.session_state['room_filter_4']

# =============================================================================
# 사이드바
# =============================================================================
with st.sidebar:
    # 모바일 뷰 토글 (G 개선)
    with st.container(border=True):
        st.markdown("### 📱 디스플레이 모드")
        view_mode = st.radio(
            "뷰 선택",
            ["💻 데스크탑 (전체 매트릭스)", "📱 모바일 (카드 뷰)"],
            key="view_mode",
            help="모바일에서는 카드 뷰가 보기 편해요"
        )

    # 포커스 모드
    picked_count = len(st.session_state.get('_picked_dates', set()))
    with st.container(border=True):
        st.markdown("### 🎯 포커스 모드")
        if picked_count > 0:
            st.markdown(f"<span style='color:#2E7D32; font-weight:bold;'>✅ 5번에서 {picked_count}일 선택됨</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='color:#999; font-size:12px;'>⚪ 5번에서 날짜 선택 시 활성화</span>", unsafe_allow_html=True)

        focus_for_4 = st.checkbox(
            "4번 권장vs적용표에 적용",
            value=st.session_state.get('focus_for_4', True),
            key='focus_for_4',
            disabled=(picked_count == 0)
        )
        focus_for_easy = st.checkbox(
            "이지에디터(채널)에 적용",
            value=st.session_state.get('focus_for_easy', True),
            key='focus_for_easy',
            disabled=(picked_count == 0)
        )

        if picked_count > 0:
            if st.button("🗑️ 포커스 선택 비우기", use_container_width=True):
                st.session_state['_picked_dates'] = set()
                st.rerun()

    st.divider()

    st.header("📅 수정 내역 조회 (History)")

    try:
        all_docs = db.collection(COL_SNAPSHOTS).select(["work_date"]).stream()
        saved_dates = sorted(list(set([d.to_dict().get('work_date', '') for d in all_docs if d.to_dict().get('work_date')])))
        if saved_dates:
            st.markdown("**📌 데이터가 저장된 날짜 (최근 14일)**")
            tags = "".join([f"<span style='background:#E8F5E9; border:1px solid #4CAF50; color:#2E7D32; padding:3px 8px; border-radius:12px; margin:2px; font-size:12px; display:inline-block; font-weight:bold;'>{d[5:]} ✅</span>" for d in saved_dates[-14:]])
            st.markdown(f"<div style='margin-bottom: 10px;'>{tags}</div>", unsafe_allow_html=True)
    except Exception:
        pass

    work_day = st.date_input("조회 날짜", value=date.today())
    if st.button("📂 과거 기록 불러오기"):
        docs = db.collection(COL_SNAPSHOTS).where("work_date", "==", work_day.strftime("%Y-%m-%d")).limit(1).stream()
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

    # 특정일 데이터 삭제
    with st.expander("🗑️ 특정일 데이터 삭제 (위험)", expanded=False):
        st.warning("⚠️ 이 작업은 되돌릴 수 없습니다. 신중히 사용하세요.")

        del_day = st.date_input("삭제할 날짜", value=date.today(), key="del_target_date")
        del_day_str = del_day.strftime("%Y-%m-%d")

        try:
            snap_count = sum(1 for _ in db.collection(COL_SNAPSHOTS).where("work_date", "==", del_day_str).stream())
        except Exception:
            snap_count = 0

        applied_doc = db.collection(COL_APPLIED).document(del_day_str).get()
        has_applied = applied_doc.exists

        st.markdown(f"""
        <div style='background:#FAFAFA; padding:8px 12px; border-radius:6px;
                    border:1px solid #E0E0E0; font-size:12px; margin:8px 0;'>
            <b>📋 {del_day_str}에 저장된 데이터:</b><br>
            • 일일 스냅샷 (리포트): <b style='color:#1976D2;'>{snap_count}건</b><br>
            • 적용 요금 (오버라이드): <b style='color:#D32F2F;'>{'있음' if has_applied else '없음'}</b>
        </div>
        """, unsafe_allow_html=True)

        target_options = []
        if snap_count > 0:
            target_options.append(f"📂 일일 스냅샷 ({snap_count}건)")
        if has_applied:
            target_options.append("⭐ 적용 요금 오버라이드")
        if snap_count > 0 and has_applied:
            target_options.append("💥 둘 다 (전부 삭제)")

        if not target_options:
            st.info(f"✨ {del_day_str}에 저장된 데이터가 없습니다.")
        else:
            del_target = st.radio("삭제 대상", target_options, key="del_target_radio")

            confirm = st.checkbox(
                f"☑️ 정말로 **{del_day_str}**의 데이터를 삭제하겠습니다",
                key="del_confirm_check"
            )

            if st.button("🗑️ 영구 삭제 실행",
                         type="primary",
                         disabled=not confirm,
                         use_container_width=True,
                         key="del_execute_btn"):
                deleted_snap = 0
                deleted_applied = False

                try:
                    # 적용 요금 삭제 전 자동 백업 (I 개선)
                    if has_applied and ("적용 요금" in del_target or "둘 다" in del_target):
                        create_restore_point(label=f"{del_day_str} 단일 삭제 직전", trigger="before_single_delete")

                    if "스냅샷" in del_target or "둘 다" in del_target:
                        snap_docs = db.collection(COL_SNAPSHOTS).where("work_date", "==", del_day_str).stream()
                        batch = db.batch()
                        bc = 0
                        for doc in snap_docs:
                            batch.delete(doc.reference)
                            deleted_snap += 1
                            bc += 1
                            if bc >= 400:
                                batch.commit(); batch = db.batch(); bc = 0
                        if bc > 0: batch.commit()

                    if "적용 요금" in del_target or "둘 다" in del_target:
                        if has_applied:
                            prev_payload = applied_doc.to_dict()
                            db.collection(COL_APPLIED).document(del_day_str).delete()
                            deleted_applied = True
                            log_audit(action="apply_delete", target_date=del_day_str,
                                      new_rooms={}, old_rooms=prev_payload.get('rooms', {}),
                                      memo="단일일 직접 삭제 (사이드바)")

                    st.cache_data.clear()
                    msg_parts = []
                    if deleted_snap > 0:
                        msg_parts.append(f"📂 스냅샷 {deleted_snap}건")
                    if deleted_applied:
                        msg_parts.append("⭐ 적용 요금")

                    if msg_parts:
                        st.success(f"🗑️ 삭제 완료: {', '.join(msg_parts)}")
                        if del_day == date.today():
                            st.session_state.today_df = pd.DataFrame()
                            st.session_state.prev_df = pd.DataFrame()
                            st.session_state.compare_label = ""
                            st.info("화면을 초기화합니다. 새 리포트를 업로드하세요.")
                        st.rerun()
                    else:
                        st.warning("삭제할 데이터를 찾지 못했습니다.")
                except Exception as e:
                    st.error(f"삭제 실패: {e}")

    # 일괄 삭제
    with st.expander("💥 일괄 삭제 (기간/전체) - 매우 위험", expanded=False):
        st.error("🚨 이 기능은 여러 날짜의 데이터를 한꺼번에 삭제합니다. 매우 신중히 사용하세요.")
        st.info("💡 일괄 삭제 실행 직전에 자동으로 복원 지점이 만들어집니다. (적용 요금 한정)")

        bulk_mode = st.radio(
            "삭제 방식",
            ["📆 기간 (시작일 ~ 종료일)", "🌍 전체 데이터 (모든 날짜)"],
            key="bulk_del_mode"
        )

        bulk_target_type = st.radio(
            "삭제 대상",
            ["⭐ 적용 요금만 (오버라이드)", "📂 일일 스냅샷만 (리포트)", "💥 둘 다 (전부)"],
            key="bulk_del_type",
        )

        if bulk_mode == "📆 기간 (시작일 ~ 종료일)":
            bcol1, bcol2 = st.columns(2)
            with bcol1:
                bulk_start = st.date_input("시작일", value=date.today(), key="bulk_del_start")
            with bcol2:
                bulk_end = st.date_input("종료일", value=date.today() + timedelta(days=60), key="bulk_del_end")

        if st.button("🔍 삭제 대상 미리 보기", use_container_width=True, key="bulk_preview_btn"):
            try:
                count_snap = 0
                count_applied = 0

                if bulk_mode == "🌍 전체 데이터 (모든 날짜)":
                    if "스냅샷" in bulk_target_type or "둘 다" in bulk_target_type:
                        count_snap = sum(1 for _ in db.collection(COL_SNAPSHOTS).stream())
                    if "적용 요금" in bulk_target_type or "둘 다" in bulk_target_type:
                        count_applied = sum(1 for _ in db.collection(COL_APPLIED).stream())
                else:
                    s_str = bulk_start.strftime("%Y-%m-%d")
                    e_str = bulk_end.strftime("%Y-%m-%d")
                    if "스냅샷" in bulk_target_type or "둘 다" in bulk_target_type:
                        snap_docs = db.collection(COL_SNAPSHOTS).where("work_date", ">=", s_str).where("work_date", "<=", e_str).stream()
                        count_snap = sum(1 for _ in snap_docs)
                    if "적용 요금" in bulk_target_type or "둘 다" in bulk_target_type:
                        applied_docs = db.collection(COL_APPLIED).stream()
                        for doc in applied_docs:
                            if s_str <= doc.id <= e_str:
                                count_applied += 1

                st.session_state['_bulk_preview'] = {
                    'snap': count_snap,
                    'applied': count_applied,
                    'mode': bulk_mode,
                    'target_type': bulk_target_type,
                    'range': (bulk_start, bulk_end) if bulk_mode == "📆 기간 (시작일 ~ 종료일)" else None
                }
                st.rerun()
            except Exception as e:
                st.error(f"미리보기 실패: {e}")

        preview = st.session_state.get('_bulk_preview')
        if preview:
            range_info = ""
            if preview.get('range'):
                s, e = preview['range']
                range_info = f"({s.strftime('%Y-%m-%d')} ~ {e.strftime('%Y-%m-%d')})"
            else:
                range_info = "(전체 데이터)"

            st.markdown(f"""
            <div style='background:#FFEBEE; padding:10px; border-radius:6px;
                        border:2px solid #D32F2F; margin:8px 0;'>
                <b style='color:#B71C1C;'>🎯 삭제 예정 데이터 {range_info}:</b><br>
                • 📂 일일 스냅샷: <b>{preview['snap']}건</b><br>
                • ⭐ 적용 요금: <b>{preview['applied']}건</b><br>
                <span style='font-size:11px; color:#666;'>{preview['target_type']} / {preview['mode']}</span>
            </div>
            """, unsafe_allow_html=True)

            total = preview['snap'] + preview['applied']
            if total > 0:
                confirm_text = st.text_input(
                    f"⚠️ 정말 삭제하려면 아래에 **삭제확인**이라고 입력하세요",
                    key="bulk_del_confirm_text",
                    placeholder="삭제확인"
                )

                if st.button("💀 일괄 영구 삭제 실행",
                             type="primary",
                             disabled=(confirm_text != "삭제확인"),
                             use_container_width=True,
                             key="bulk_del_execute"):
                    try:
                        # 일괄 삭제 직전 자동 백업 (I 개선)
                        if ("적용 요금" in preview['target_type'] or "둘 다" in preview['target_type']) and preview['applied'] > 0:
                            create_restore_point(
                                label=f"일괄삭제 직전 ({preview['applied']}건)",
                                trigger="before_bulk_delete",
                            )

                        deleted_snap = 0
                        deleted_applied = 0

                        # H 개선: 배치 삭제로 최적화
                        if preview['mode'] == "🌍 전체 데이터 (모든 날짜)":
                            if "스냅샷" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                for doc in db.collection(COL_SNAPSHOTS).stream():
                                    batch.delete(doc.reference); deleted_snap += 1; bc += 1
                                    if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()
                            if "적용 요금" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                for doc in db.collection(COL_APPLIED).stream():
                                    batch.delete(doc.reference); deleted_applied += 1; bc += 1
                                    if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()
                        else:
                            s, e = preview['range']
                            s_str = s.strftime("%Y-%m-%d")
                            e_str = e.strftime("%Y-%m-%d")

                            if "스냅샷" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                snap_docs = db.collection(COL_SNAPSHOTS).where("work_date", ">=", s_str).where("work_date", "<=", e_str).stream()
                                for doc in snap_docs:
                                    batch.delete(doc.reference); deleted_snap += 1; bc += 1
                                    if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()

                            if "적용 요금" in preview['target_type'] or "둘 다" in preview['target_type']:
                                batch = db.batch(); bc = 0
                                applied_docs = db.collection(COL_APPLIED).stream()
                                for doc in applied_docs:
                                    if s_str <= doc.id <= e_str:
                                        batch.delete(doc.reference); deleted_applied += 1; bc += 1
                                        if bc >= 400: batch.commit(); batch = db.batch(); bc = 0
                                if bc > 0: batch.commit()

                        log_audit(action="bulk_delete", target_date="*", new_rooms={},
                                  memo=f"{preview['target_type']} / {preview['mode']}",
                                  extra={'deleted_snap': deleted_snap, 'deleted_applied': deleted_applied, 'range': str(preview.get('range'))})

                        st.cache_data.clear()
                        del st.session_state['_bulk_preview']

                        st.session_state.today_df = pd.DataFrame()
                        st.session_state.prev_df = pd.DataFrame()
                        st.session_state.compare_label = ""
                        st.session_state.manual_bars = {}
                        if '_picked_dates' in st.session_state:
                            st.session_state['_picked_dates'] = set()
                        # 캐시 정리
                        for k in list(st.session_state.keys()):
                            if k.startswith("_review_map_cache_"):
                                del st.session_state[k]

                        st.success(f"🗑️ 일괄 삭제 완료! 스냅샷 {deleted_snap}건, 적용 요금 {deleted_applied}건")
                        st.info("화면을 초기화했습니다. 새 리포트를 업로드하세요.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"일괄 삭제 실패: {e}")
            else:
                st.success("✨ 삭제할 데이터가 없습니다.")

        if preview:
            if st.button("🔄 미리보기 리셋", use_container_width=True, key="bulk_preview_reset"):
                del st.session_state['_bulk_preview']
                st.rerun()

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
            db.collection(COL_SNAPSHOTS).add({
                "work_date": date.today().strftime("%Y-%m-%d"),
                "save_time": datetime.now().isoformat(),
                "data": t_df.to_dict(orient='records'),
                "prev_data": p_df_dict,
                "saved_promotions": st.session_state.promotions,
                "saved_channel_list": st.session_state.channel_list,
                "saved_manual_bars": st.session_state.manual_bars
            })
            st.cache_data.clear()
            # ── 신규: 예외 자동 갱신 (권장가 > 예외가인 경우 자동 인상) ──
            auto_cnt, auto_log = auto_update_stale_exceptions(st.session_state.today_df)
            if auto_cnt > 0:
                changes_html = "".join(
                    f"<li><b>{item['date']}</b>: {', '.join(item['changes'])}</li>"
                    for item in auto_log
                )
                st.info(f"🔄 예외 {auto_cnt}건 자동 갱신 완료 (권장가 인상 적용)\n\n"
                        f"아래 이지에디터에 반영되었습니다.")
                with st.expander(f"📋 자동 갱신 상세 ({auto_cnt}건)", expanded=False):
                    st.markdown(f"<ul>{changes_html}</ul>", unsafe_allow_html=True)
            st.success("저장 완료!")

# =============================================================================
# 7. 파일 로직 (스마트 병합)
# =============================================================================
if files:
    new_extracted = []
    _parse_failed_dates = []   # 날짜로 못 읽은 헤더 값 (조용한 열 누락 방지)
    ROW_MAP = {4: "GDB", 5: "GDF", 6: "FDB", 7: "FDE", 8: "FPT", 9: "FFD", 10: "HDP", 11: "HDT", 12: "HDF", 13: "PPV"}

    for f in files:
        date_tag = re.search(r'\d{8}', f.name).group() if re.search(r'\d{8}', f.name) else f.name
        df_raw = pd.read_excel(f, header=None)
        dates_raw = df_raw.iloc[2, 2:].values

        # 헤더 날짜를 한 번만 파싱해두고 실패분을 기록
        parsed_dates = []
        for d_val in dates_raw:
            d_obj = robust_date_parser(d_val)
            parsed_dates.append(d_obj)
            if d_obj is None and pd.notna(d_val) and str(d_val).strip():
                if str(d_val) not in _parse_failed_dates:
                    _parse_failed_dates.append(str(d_val))

        for r_idx, rid in ROW_MAP.items():
            if r_idx < len(df_raw):
                tot = pd.to_numeric(df_raw.iloc[r_idx, 1], errors='coerce')
                for d_obj, av in zip(parsed_dates, df_raw.iloc[r_idx, 2:].values):
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

    # 새 파일 업로드 시 리뷰 캐시 정리
    for k in list(st.session_state.keys()):
        if k.startswith("_review_map_cache_"):
            del st.session_state[k]

    # ── 신규: 업로드 데이터 무결성 점검 ──────────────────────────────
    # 기존에는 전체객실 결측 → OCC 0%(최저가), 잔여객실 결측 → OCC 100%(최고가)로
    # 조용히 단정해 오요금이 나갔습니다. 이제 여기서 먼저 표면화합니다.
    _bad_rows = validate_inventory_df(st.session_state.today_df)
    if _bad_rows:
        st.error(f"🚨 재고 데이터 이상 {len(_bad_rows)}건 — 해당 셀은 호텔 전체 OCC로 대체 계산됩니다. "
                 f"원본 리포트를 확인하세요.")
        with st.expander(f"📋 이상 데이터 상세 ({len(_bad_rows)}건)", expanded=True):
            _bad_df = pd.DataFrame(
                [{"날짜": d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d),
                  "객실": rid, "사유": why} for d, rid, why in _bad_rows]
            )
            st.dataframe(_bad_df, use_container_width=True, hide_index=True)
    else:
        st.success(f"✅ 재고 데이터 무결성 검사 통과 ({len(st.session_state.today_df)}행)")

    # 업로드 파일에서 날짜를 못 읽은 경우 경고 (날짜 열 누락 조용한 실패 방지)
    if _parse_failed_dates:
        st.warning(
            f"⚠️ 날짜로 인식하지 못한 헤더 값 {len(_parse_failed_dates)}건이 있어 해당 열은 "
            f"제외됐습니다: {', '.join(str(x) for x in _parse_failed_dates[:12])}"
            + (" …" if len(_parse_failed_dates) > 12 else "")
        )

# =============================================================================
# 8. 메인 출력
# =============================================================================
if not st.session_state.today_df.empty:
    curr, prev = st.session_state.today_df, st.session_state.prev_df

    if st.session_state.compare_label:
        st.info(f"ℹ️ {st.session_state.compare_label}")

    # ── 신규: 전 날짜 요금 선산출 (캐시 워밍 + 데이터/로직 이슈 수집) ──
    # 이슈를 화면 하단이 아니라 상단에서 먼저 보여주기 위해 미리 한 번 돌립니다.
    _mb = dict(st.session_state.get('manual_bars', {}))
    for _d in sorted(curr['Date'].unique()):
        try:
            compute_all_prices_for_date(_d, curr, _mb)
        except Exception as _e:
            _msg = f"{_d}: 요금 산출 실패 ({type(_e).__name__}: {_e})"
            if _msg not in _logic_errors:
                _logic_errors.append(_msg)

    if _logic_errors:
        st.error(f"🚨 요금 산출 중 오류 {len(_logic_errors)}건 — 해당 셀은 폴백(역전방지·연동 미적용) "
                 f"경로로 계산됐습니다. 요금을 신뢰하지 말고 아래 내용을 확인하세요.")
        with st.expander(f"📋 오류 상세 ({len(_logic_errors)}건)", expanded=True):
            for _m in _logic_errors[:50]:
                st.markdown(f"- {_m}")

    if _data_issues:
        st.warning(f"⚠️ 요금 산출에 영향을 준 데이터 이슈 {len(_data_issues)}건 "
                   f"(결측/범위초과/무효 오버라이드) — 대체값으로 계산됐습니다.")
        with st.expander(f"📋 데이터 이슈 상세 ({len(_data_issues)}건)", expanded=False):
            st.dataframe(
                pd.DataFrame([{"날짜": k[0], "객실": k[1], "사유": v}
                              for k, v in sorted(_data_issues.items())]),
                use_container_width=True, hide_index=True,
            )

    # 모바일 뷰면 카드만 보여주고 끝 (G 개선)
    if st.session_state.get('view_mode', "").startswith("📱"):
        applied_rates_data = load_applied_rates()
        render_mobile_card_view(curr, applied_rates_data)
        st.divider()
        render_tomorrow_preview(curr, applied_rates_data)
        st.divider()
        st.caption("💡 데스크탑 뷰로 전환하면 전체 매트릭스, 5번 오버라이드, 채널 판매가 등을 모두 볼 수 있습니다.")
    else:
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

            # D 개선: 내일 미리보기 (최상단)
            render_tomorrow_preview(curr_filtered, applied_rates_data)
            st.divider()

            # E 개선: 스파크라인
            render_pickup_sparklines(curr_filtered)
            st.divider()

            # 재검토 알림 배너
            review_map = build_review_map(curr_filtered, applied_rates_data)
            review_alerts = []
            for (rid, d), info in review_map.items():
                if info['needs']:
                    review_alerts.append({
                        '날짜': d.strftime('%m-%d'),
                        '요일': WEEKDAYS_KR[d.weekday()],
                        '객실': rid,
                        '적용 BAR': info['applied'],
                        '신규 권장': info['rec'],
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

            # 1. 시장 분석
            st.markdown(render_master_table(curr_filtered, prev_filtered, title="📊 1. 시장 분석 (시스템 권장 기준)", mode="기준"), unsafe_allow_html=True)

            # 1-A. 최종 확정
            st.markdown(render_master_table(curr_filtered, prev_filtered, applied_rates=applied_rates_data, title="🎯 1-A. 최종 확정 요금 상태 (시스템 + 전략 적용)", mode="최종결과"), unsafe_allow_html=True)

            st.markdown(render_master_table(curr_filtered, prev_filtered, title="📈 2. 예약 변화량", mode="변화"), unsafe_allow_html=True)
            st.markdown(render_master_table(curr_filtered, prev_filtered, title="🔔 3. 판도 변화", mode="판도변화"), unsafe_allow_html=True)

            # 3-B. 예외 현황 요약 (신규: 현재 활성 예외 한눈에)
            with st.expander("📌 현재 활성 예외 현황 (파일 저장 시 자동 갱신됨)", expanded=False):
                st.caption(
                    "5번에서 설정한 예외들입니다. "
                    "파일을 저장하면 권장가 > 예외가인 경우 자동으로 권장가로 갱신됩니다."
                )
                _exc_applied = load_applied_rates()
                _exc_dates = sorted(
                    [ds for ds in _exc_applied if _exc_applied[ds].get('rooms')],
                    key=lambda x: x
                )
                if not _exc_dates:
                    st.info("현재 설정된 예외가 없습니다. 5번에서 추가하세요.")
                else:
                    _exc_rows = []
                    for _ds in _exc_dates:
                        try:
                            _d = datetime.strptime(_ds, '%Y-%m-%d').date()
                        except Exception:
                            continue
                        _info = _exc_applied[_ds]
                        _rooms_str = ", ".join(
                            f"{r}={b}" for r, b in sorted(_info.get('rooms', {}).items())
                        )
                        _memo = _info.get('memo', '')
                        _at = _info.get('applied_at_display', '')
                        _past = "📜" if _d < TODAY else "🔮"
                        _exc_rows.append({
                            "": _past,
                            "날짜": _ds,
                            "요일": WEEKDAYS_KR[_d.weekday()],
                            "적용 BAR": _rooms_str,
                            "메모": _memo[:40],
                            "갱신일시": _at,
                        })
                    _exc_df = pd.DataFrame(_exc_rows)
                    st.dataframe(_exc_df, use_container_width=True, hide_index=True, height=300)
                    st.caption(f"총 {len(_exc_rows)}건 활성 예외")

            # 4. 권장 vs 적용 비교 (A 개선: 행 필터)
            st.markdown("---")
            tcol1, tcol2, tcol3 = st.columns([2, 2, 3])
            with tcol1:
                highlight_changes = st.checkbox(
                    "🎯 변동된 셀만 강조 (4번 + 이지에디터)",
                    value=True,
                    key="highlight_only_changes",
                    help="ON: 권장과 같고 이전과도 동일한 '평온한' 셀은 회색 / OFF: 모든 적용 셀 진하게"
                )
            with tcol2:
                room_filter_4 = st.multiselect(
                    "🔍 4번 표 객실 필터",
                    options=ALL_ROOMS,
                    default=ALL_ROOMS,
                    key="room_filter_4",
                    help="비교표에 보고 싶은 객실만 선택 (연동객실은 읽기전용)"
                )
            with tcol3:
                picked_now = st.session_state.get('_picked_dates', set())
                f4_on = st.session_state.get('focus_for_4', True) and len(picked_now) > 0

                tip_parts = []
                if highlight_changes:
                    tip_parts.append("✅ 진짜 손댈 셀만 도드라짐")
                else:
                    tip_parts.append("📋 모든 적용 셀 진하게")
                if f4_on:
                    tip_parts.append(f"🎯 <b>포커스: {len(picked_now)}일만 활성</b>")
                elif len(picked_now) > 0:
                    tip_parts.append("⚪ 포커스 OFF")
                st.markdown(f"<div style='font-size:12px; color:#666;'>{' · '.join(tip_parts)}</div>", unsafe_allow_html=True)

            focus_for_4_table = picked_now if f4_on else None

            st.markdown(render_applied_vs_recommend_table(
                curr_filtered, applied_rates_data,
                prev_df=prev_filtered,
                prev_applied_rates=applied_rates_data,
                highlight_only_changes=highlight_changes,
                focus_dates=focus_for_4_table,
                room_filter=room_filter_4,
            ), unsafe_allow_html=True)

            # 5. 요금 적용 UI (접기/펼치기)
            with st.expander("⏰ 5. 예외 설정 — 특정 날짜 BAR 고정", expanded=False):
                render_apply_rate_ui(curr, applied_rates_data)

        # 전략적 판도 오버라이드
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
                rejected = []
                for idx, row in edited_matrix.iterrows():
                    rid = row["객실"]
                    for d in dates_list:
                        val = str(row[d.strftime('%m-%d')]).strip()
                        if not val or val.upper() in ["NONE", "NAN", ""]:
                            continue
                        key = f"{d.strftime('%Y-%m-%d')}_{rid}"
                        # ※ 수정: 기존에는 val.upper()를 그대로 저장했습니다.
                        #   'BAR 3', '3' 같은 오타가 요금표에서 조회되지 않아
                        #   판매가 0원으로 나가는 버그가 있었습니다.
                        cleaned = str(val).strip().upper().replace(" ", "")
                        if is_valid_bar(cleaned):
                            new_manual_bars[key] = cleaned
                        else:
                            rejected.append(f"{rid} {d.strftime('%m-%d')}: '{val}'")
                st.session_state.manual_bars = new_manual_bars
                if rejected:
                    st.error(
                        f"❌ 유효하지 않은 BAR 코드 {len(rejected)}건은 저장하지 않았습니다 "
                        f"(사용 가능: {', '.join(BAR_ORDER)})\n\n- " + "\n- ".join(rejected[:20])
                    )
                applied_n = len(new_manual_bars)
                st.success(f"수동 오버라이드 {applied_n}건이 하단 판매가 리포트에 적용되었습니다.")
                st.rerun()

        st.divider()

        # 채널 판매가 (요청 1 + A 개선)
        if st.session_state.channel_list:
            hlc = st.session_state.get("highlight_only_changes", True)
            picked = st.session_state.get('_picked_dates', set())
            easy_focus_on = st.session_state.get('focus_for_easy', True) and len(picked) > 0
            focus_dates = picked if easy_focus_on else None

            focus_info = ""
            if focus_dates:
                focus_info = f"🎯 <b>포커스 모드 ON</b>: 5번에서 선택한 <b>{len(focus_dates)}일</b>만 색칠"
            elif len(picked) > 0:
                focus_info = "⚪ <b>포커스 모드 OFF</b>: 사이드바 토글로 켤 수 있음"
            else:
                focus_info = "🌐 <b>전체 모드</b>: 5번에서 날짜 선택 시 그 기간만 집중 표시 가능"

            st.markdown(f"""
            <div style='background:#FFF3E0; padding:10px 15px; border-radius:8px; margin:15px 0;'>
                💡 <b>채널 판매가 표기 규칙</b> {'(🎯 변동만 강조 ON)' if hlc else '(📋 전체 보기)'}<br>
                <span style='color:#1976D2;'>{focus_info}</span>
            </div>
            """, unsafe_allow_html=True)

            # ===== 요청 1: 채널별 객실/상품 행 필터 =====
            for ch in st.session_state.channel_list:
                items_all = st.session_state.promotions.get(ch, {}).get("items", [])
                if not items_all:
                    st.markdown(render_channel_sale_table(
                        curr_filtered, prev_filtered, ch, applied_rates_data, applied_rates_data,
                        highlight_only_changes=hlc, focus_dates=focus_dates,
                    ), unsafe_allow_html=True)
                    continue

                with st.container(border=True):
                    fc1, fc2, fc3 = st.columns([2, 2, 1])
                    with fc1:
                        rooms_in_ch = sorted({it.get('객실타입') for it in items_all if it.get('객실타입')})
                        picked_rooms = st.multiselect(
                            f"🔍 [{ch}] 객실타입 필터",
                            options=rooms_in_ch,
                            default=rooms_in_ch,
                            key=f"filter_rooms_{ch}",
                            help="보고 싶은 객실타입만 선택"
                        )
                    with fc2:
                        items_by_room = [it for it in items_all if it.get('객실타입') in picked_rooms]
                        product_labels = [f"{it.get('객실타입')} · {it.get('상품명')}" for it in items_by_room]
                        picked_products = st.multiselect(
                            f"🎁 [{ch}] 개별 상품 필터",
                            options=product_labels,
                            default=product_labels,
                            key=f"filter_products_{ch}",
                            help="특정 상품만 보고 싶을 때"
                        )
                    with fc3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("전체 보기", key=f"reset_filter_{ch}", use_container_width=True):
                            for k in [f"filter_rooms_{ch}", f"filter_products_{ch}"]:
                                if k in st.session_state:
                                    del st.session_state[k]
                            st.rerun()

                filtered_items = [it for it in items_by_room
                                  if f"{it.get('객실타입')} · {it.get('상품명')}" in picked_products]

                if not filtered_items:
                    st.info(f"🔍 [{ch}] 필터 조건에 맞는 상품이 없습니다.")
                    continue

                # items_override 파라미터로 안전하게 주입 (원본 보호)
                st.markdown(render_channel_sale_table(
                    curr_filtered, prev_filtered, ch, applied_rates_data, applied_rates_data,
                    highlight_only_changes=hlc, focus_dates=focus_dates,
                    items_override=filtered_items,
                ), unsafe_allow_html=True)

        st.divider()

        # 변경 이력 & 복원 지점 UI
        render_audit_log_ui()
        render_restore_point_ui()

        st.divider()

        # 오버라이드 초기화 & BAR 캘린더
        render_reset_override_ui(st.session_state.today_df, applied_rates_data)

        st.divider()

        render_bar_calendar_table(st.session_state.today_df, applied_rates_data)

        st.divider()

        # 구/신 요금 곡선 비교 (2단계 안전장치)
        render_pricing_compare_ui(st.session_state.today_df)

        st.divider()

        # 엑셀 다운로드
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
                    applied_price = get_applied_price(rid, applied_bar, d,
                                                      st.session_state.today_df,
                                                      applied_rates_export, fallback=rec_price)
                    status = "✅ 적용됨"
                    is_diff = "⚠️ 다름" if applied_bar != rec_bar else "일치"
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
