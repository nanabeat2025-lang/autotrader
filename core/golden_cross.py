"""
골든크로스 / 데드크로스 스캐너 모듈

골든크로스: 단기 이동평균선이 장기 이동평균선을 아래→위로 돌파 (매수 신호)
데드크로스: 단기 이동평균선이 장기 이동평균선을 위→아래로 돌파 (매도 신호)

지원 조합:
  - 단기: 5일 / 20일  (빠른 신호, 노이즈 많음)
  - 중기: 20일 / 60일  (중간 신뢰도)
  - 장기: 20일 / 120일 (느리지만 강한 신호)
"""
import time
from typing import Optional
from core.indicators import calc_ma


# ── 대표 스캔 종목 (KOSPI/KOSDAQ 주요 종목 + ETF) ────────
# 원하는 종목을 자유롭게 추가/수정 가능
SCAN_UNIVERSE = {
    # 대형주
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "035420": "NAVER",
    "035720": "카카오",
    "005380": "현대차",
    "000270": "기아",
    "006400": "삼성SDI",
    "051910": "LG화학",
    "003670": "포스코퓨처엠",
    "068270": "셀트리온",
    "105560": "KB금융",
    "055550": "신한지주",
    "012330": "현대모비스",
    "033780": "KT&G",
    "003550": "LG",
    "034730": "SK",
    "030200": "KT",
    "017670": "SK텔레콤",
    "066570": "LG전자",
    "032830": "삼성생명",
    "009150": "삼성전기",
    "028260": "삼성물산",
    "010130": "고려아연",
    "034020": "두산에너빌리티",
    "004020": "현대제철",
    # 중형주
    "247540": "에코프로비엠",
    "086520": "에코프로",
    "373220": "LG에너지솔루션",
    "352820": "하이브",
    "259960": "크래프톤",
    "263750": "펄어비스",
    "293490": "카카오게임즈",
    # ETF
    "069500": "KODEX 200",
    "114800": "KODEX 인버스",
    "229200": "KODEX 코스닥150",
    "305540": "TIGER 2차전지테마",
    "381180": "TIGER AI반도체핵심공정",
    "364690": "KODEX Fn반도체",
    "091160": "KODEX 반도체",
    "091170": "KODEX 은행",
    "139260": "TIGER 200 IT",
}


def _get_closes_from_ohlcv(ohlcv_list: list[dict]) -> list[float]:
    """KIS OHLCV → 시계열 순서 종가 리스트 (과거→현재)"""
    ordered = list(reversed(ohlcv_list))
    return [float(d.get("stck_clpr", 0)) for d in ordered]


def detect_cross(closes: list[float], short_period: int, long_period: int) -> Optional[str]:
    """
    골든/데드 크로스 감지
    Returns: "GOLDEN" | "DEAD" | None

    원리: 어제와 오늘의 단기MA - 장기MA 부호 변화 확인
      어제 단기 < 장기 → 오늘 단기 > 장기 = 골든크로스
      어제 단기 > 장기 → 오늘 단기 < 장기 = 데드크로스
    """
    if len(closes) < long_period + 1:
        return None

    # 오늘 (마지막 봉)
    today_short = calc_ma(closes, short_period)
    today_long  = calc_ma(closes, long_period)

    # 어제 (마지막에서 하나 뺀)
    yesterday_closes = closes[:-1]
    yesterday_short  = calc_ma(yesterday_closes, short_period)
    yesterday_long   = calc_ma(yesterday_closes, long_period)

    if None in (today_short, today_long, yesterday_short, yesterday_long):
        return None

    yesterday_diff = yesterday_short - yesterday_long
    today_diff     = today_short - today_long

    if yesterday_diff <= 0 and today_diff > 0:
        return "GOLDEN"
    elif yesterday_diff >= 0 and today_diff < 0:
        return "DEAD"
    return None


def detect_near_golden(closes: list[float], short_period: int, long_period: int,
                       threshold: float = 0.005) -> bool:
    """
    골든크로스 임박 여부 (단기MA가 장기MA 대비 threshold% 이내로 접근)
    아직 돌파하진 않았지만 곧 발생할 수 있는 종목 감지
    """
    if len(closes) < long_period:
        return False
    short_ma = calc_ma(closes, short_period)
    long_ma  = calc_ma(closes, long_period)
    if None in (short_ma, long_ma) or long_ma == 0:
        return False
    # 단기 < 장기 (아직 아래) + 갭이 threshold% 이내
    gap_rate = (long_ma - short_ma) / long_ma
    return short_ma < long_ma and 0 < gap_rate <= threshold


def scan_golden_cross(
    kis,
    tickers: dict = None,
    short_period: int = 5,
    long_period: int = 20,
    include_near: bool = True,
    ohlcv_days: int = 130,
) -> dict:
    """
    여러 종목을 스캔하여 골든크로스 / 데드크로스 / 임박 종목 반환

    Returns: {
        "golden": [{"ticker", "name", "short_ma", "long_ma", "current_price", "volume"}, ...],
        "dead":   [...],
        "near":   [...],
        "scanned": 총 스캔 종목 수,
        "short_period": 5,
        "long_period": 20,
    }
    """
    if tickers is None:
        tickers = SCAN_UNIVERSE

    golden_list = []
    dead_list   = []
    near_list   = []

    for ticker, name in tickers.items():
        try:
            ohlcv = kis.get_daily_ohlcv(ticker, period=ohlcv_days)
            if not ohlcv:
                continue

            closes = _get_closes_from_ohlcv(ohlcv)
            if len(closes) < long_period + 1:
                continue

            current_price = closes[-1]
            short_ma = calc_ma(closes, short_period) or 0
            long_ma  = calc_ma(closes, long_period)  or 0
            volume   = int(ohlcv[0].get("acml_vol", 0))  # 최신 거래량

            entry = {
                "ticker":        ticker,
                "name":          name,
                "current_price": current_price,
                "short_ma":      round(short_ma, 0),
                "long_ma":       round(long_ma, 0),
                "gap_rate":      round((short_ma - long_ma) / long_ma * 100, 2) if long_ma else 0,
                "volume":        volume,
            }

            cross = detect_cross(closes, short_period, long_period)
            if cross == "GOLDEN":
                golden_list.append(entry)
            elif cross == "DEAD":
                dead_list.append(entry)
            elif include_near and detect_near_golden(closes, short_period, long_period):
                entry["gap_rate"] = round((long_ma - short_ma) / long_ma * 100, 2) if long_ma else 0
                near_list.append(entry)

            time.sleep(0.15)  # API rate limit

        except Exception as e:
            print(f"  [{ticker}] 스캔 실패: {e}")
            continue

    return {
        "golden":       sorted(golden_list, key=lambda x: x["volume"], reverse=True),
        "dead":         sorted(dead_list,   key=lambda x: x["volume"], reverse=True),
        "near":         sorted(near_list,   key=lambda x: x["gap_rate"]),
        "scanned":      len(tickers),
        "short_period":  short_period,
        "long_period":   long_period,
    }


def format_scan_result(result: dict) -> str:
    """스캔 결과를 텔레그램 HTML 메시지로 포맷"""
    sp = result["short_period"]
    lp = result["long_period"]
    lines = [f"<b>📊 골든크로스 스캔 결과 ({sp}일/{lp}일)</b>"]
    lines.append(f"스캔 종목: {result['scanned']}개\n")

    # 골든크로스
    golden = result["golden"]
    if golden:
        lines.append(f"<b>🟢 골든크로스 발생 ({len(golden)}건)</b>")
        for s in golden:
            lines.append(
                f"  <code>{s['ticker']}</code> <b>{s['name']}</b>\n"
                f"    현재가 {s['current_price']:,.0f}원 | "
                f"{sp}일MA {s['short_ma']:,.0f} > {lp}일MA {s['long_ma']:,.0f}\n"
                f"    거래량 {s['volume']:,}"
            )
    else:
        lines.append("🟢 골든크로스: 없음")

    lines.append("")

    # 임박
    near = result["near"]
    if near:
        lines.append(f"<b>🟡 골든크로스 임박 ({len(near)}건)</b>")
        for s in near[:5]:  # 상위 5개
            lines.append(
                f"  <code>{s['ticker']}</code> <b>{s['name']}</b>\n"
                f"    현재가 {s['current_price']:,.0f}원 | "
                f"갭 {s['gap_rate']:.2f}%"
            )
    lines.append("")

    # 데드크로스
    dead = result["dead"]
    if dead:
        lines.append(f"<b>🔴 데드크로스 발생 ({len(dead)}건)</b>")
        for s in dead:
            lines.append(
                f"  <code>{s['ticker']}</code> <b>{s['name']}</b>\n"
                f"    현재가 {s['current_price']:,.0f}원"
            )
    else:
        lines.append("🔴 데드크로스: 없음")

    return "\n".join(lines)
