"""
종목 스크리너
전체 주요 종목을 스캔해서 매매 조건에 맞는 종목만 필터링
→ 조건 충족 종목만 GPT 분석으로 넘김 (API 비용 절감 + 기회 포착)

매수 후보 조건 (하나 이상 충족):
  - RSI < 40 (과매도)
  - MACD 골든크로스 발생
  - 볼린저밴드 하단 근처 (position < 0.2)
  - 거래량 급증 (1.5배 이상) + 가격 상승

매도 후보 조건 (보유 종목):
  - RSI > 70 (과매수)
  - MACD 데드크로스 발생
  - 볼린저밴드 상단 근처 (position > 0.8)
"""
import time
from core.indicators import build_indicators, calc_rsi, calc_macd, calc_bollinger, detect_volume_spike, _safe_float, _safe_int


def build_universe(kis) -> dict:
    """
    동적 스캔 유니버스 구성
    - KOSPI 시가총액 상위 100
    - KOSDAQ 시가총액 상위 100
    - 거래량 상위 100
    → 중복 제거 후 최대 300개
    """
    universe = {}

    print("🌐 전 종목 유니버스 구성 중...")

    # 1) KOSPI 시가총액 상위 100
    try:
        kospi_top = kis.get_market_cap_top(market="J", n=100)
        for item in kospi_top:
            ticker = item.get("mksc_shrn_iscd", "")
            name   = item.get("hts_kor_isnm", ticker)
            if ticker and len(ticker) == 6:
                universe[ticker] = {"name": name, "type": "STOCK"}
        print(f"  KOSPI 시가총액 상위: {len(kospi_top)}개")
    except Exception as e:
        print(f"  KOSPI 시가총액 조회 실패: {e}")

    # 2) KOSDAQ 시가총액 상위 100
    try:
        kosdaq_top = kis.get_market_cap_top(market="Q", n=100)
        for item in kosdaq_top:
            ticker = item.get("mksc_shrn_iscd", "")
            name   = item.get("hts_kor_isnm", ticker)
            if ticker and len(ticker) == 6:
                universe[ticker] = {"name": name, "type": "STOCK"}
        print(f"  KOSDAQ 시가총액 상위: {len(kosdaq_top)}개")
    except Exception as e:
        print(f"  KOSDAQ 시가총액 조회 실패: {e}")

    # 3) 거래량 상위 100 (당일 핫한 종목)
    try:
        vol_top = kis.get_volume_top(n=100)
        for item in vol_top:
            ticker = item.get("mksc_shrn_iscd", "")
            name   = item.get("hts_kor_isnm", ticker)
            if ticker and len(ticker) == 6:
                universe[ticker] = {"name": name, "type": "STOCK"}
        print(f"  거래량 상위: {len(vol_top)}개")
    except Exception as e:
        print(f"  거래량 상위 조회 실패: {e}")

    # ETF도 추가 (주요 지수 ETF)
    etf_list = {
        "069500": "KODEX 200", "091160": "KODEX 반도체",
        "102780": "KODEX 삼성그룹", "229200": "KODEX 코스닥150",
        "139260": "TIGER 200 IT", "305540": "TIGER 2차전지테마",
    }
    for ticker, name in etf_list.items():
        universe[ticker] = {"name": name, "type": "ETF"}

    print(f"✅ 유니버스 구성 완료: 총 {len(universe)}개 종목\n")
    return universe


def _meets_buy_condition(indicators: dict, investor: dict = None, market: dict = None) -> tuple[bool, str]:
    """
    매수 후보 조건 체크
    Returns: (조건충족여부, 충족된 조건 설명)
    """
    rsi       = indicators.get("rsi") or 50
    macd      = indicators.get("macd", {}) or {}
    bb        = indicators.get("bollinger", {}) or {}
    vol_spike = indicators.get("volume_spike", {}) or {}
    ohlcv     = indicators.get("recent_ohlcv", []) or []
    ma5       = indicators.get("ma5", 0) or 0
    ma20      = indicators.get("ma20", 0) or 0
    investor  = investor or {}
    market    = market or {}

    reasons = []

    # ── 시장 분위기 체크 (코스피 -1.5% 이상 하락 시 매수 신중) ──
    kospi_rate = float(market.get("KOSPI", {}).get("change_rate", 0) or 0)
    if kospi_rate <= -1.5:
        # 시장 급락 시 매수 조건 강화 (RSI 30 이하만 허용)
        if rsi < 30:
            reasons.append(f"시장급락({kospi_rate:.1f}%)+RSI극과매도({rsi})")
        return len(reasons) > 0, " | ".join(reasons)

    # ── 기술적 지표 ──────────────────────────────────────────
    # 1) RSI 과매도
    if rsi < 40:
        reasons.append(f"RSI 과매도({rsi})")

    # 2) MACD 골든크로스
    if macd.get("cross") == "GOLDEN":
        reasons.append("MACD 골든크로스")

    # 3) 볼린저밴드 하단 근처
    bb_pos = bb.get("position")
    if bb_pos is not None and bb_pos < 0.2:
        reasons.append(f"볼린저밴드 하단({bb_pos:.2f})")

    # 4) 5일선이 20일선 위 (단기 상승 추세)
    if ma5 > 0 and ma20 > 0 and ma5 > ma20:
        reasons.append(f"5일선>20일선")

    # 5) 거래량 급증 + 가격 상승
    if vol_spike.get("is_spike") and len(ohlcv) >= 2:
        if ohlcv[-1]["close"] > ohlcv[-2]["close"]:
            reasons.append(f"거래량 급증({vol_spike.get('ratio', 0):.1f}배)+상승")

    # ── 수급 데이터 ──────────────────────────────────────────
    # 6) 외국인 순매수 양수
    if investor.get("foreign_net_buy", 0) > 0:
        reasons.append(f"외국인 순매수({investor['foreign_net_buy']:+,}주)")

    # 7) 기관 순매수 양수
    if investor.get("institution_net_buy", 0) > 0:
        reasons.append(f"기관 순매수({investor['institution_net_buy']:+,}주)")

    return len(reasons) > 0, " | ".join(reasons)


def _meets_sell_condition(indicators: dict, investor: dict = None, market: dict = None) -> tuple[bool, str]:
    """매도 후보 조건 체크 (보유 종목용)"""
    rsi      = indicators.get("rsi") or 50
    macd     = indicators.get("macd", {}) or {}
    bb       = indicators.get("bollinger", {}) or {}
    investor = investor or {}
    market   = market or {}

    reasons = []

    # RSI 과매수
    if rsi > 70:
        reasons.append(f"RSI 과매수({rsi})")

    # MACD 데드크로스
    if macd.get("cross") == "DEAD":
        reasons.append("MACD 데드크로스")

    # 볼린저밴드 상단
    bb_pos = bb.get("position")
    if bb_pos is not None and bb_pos > 0.8:
        reasons.append(f"볼린저밴드 상단({bb_pos:.2f})")

    # 외국인 순매도 지속
    if investor.get("foreign_net_buy", 0) < 0:
        reasons.append(f"외국인 순매도({investor['foreign_net_buy']:+,}주)")

    # 코스피 급락
    kospi_rate = float(market.get("KOSPI", {}).get("change_rate", 0) or 0)
    if kospi_rate <= -1.5:
        reasons.append(f"코스피 급락({kospi_rate:.1f}%)")

    return len(reasons) > 0, " | ".join(reasons)


def screen_stocks(kis, held_tickers: list = None) -> list[dict]:
    """전체 유니버스 동적 스캔 → 조건 충족 종목 반환"""
    from core.indicators import summarize_investor
    held_tickers = held_tickers or []
    result = []

    # 시장 분위기 (한 번만 조회)
    market = {}
    try:
        market = kis.get_market_index()
        kospi  = market.get("KOSPI", {})
        kosdaq = market.get("KOSDAQ", {})
        print(f"\n📈 KOSPI: {kospi.get('current')} ({kospi.get('change_rate')}%) | "
              f"KOSDAQ: {kosdaq.get('current')} ({kosdaq.get('change_rate')}%)")
    except Exception as e:
        print(f"시장 지수 조회 실패: {e}")

    # 동적 유니버스 구성
    universe = build_universe(kis)
    print(f"🔍 스크리닝 시작 ({len(universe)}개 종목 분석 중...)")

    for ticker, info in universe.items():
        name       = info["name"]
        stock_type = info["type"]
        try:
            ohlcv = kis.get_daily_ohlcv(ticker, period=30)
            if not ohlcv:
                continue
            indicators = build_indicators(ohlcv)

            # 현재가 업데이트
            try:
                pd = kis.get_stock_price(ticker)
                raw = pd.get("stck_prpr", "")
                if raw:
                    indicators["current_price"] = _safe_float(raw)
            except Exception:
                pass

            # 수급 데이터
            investor = {}
            try:
                investor_raw = kis.get_investor_trend(ticker)
                investor = summarize_investor(investor_raw)
            except Exception:
                pass

            is_held = ticker in held_tickers

            if is_held:
                sell_ok, sell_reason = _meets_sell_condition(indicators, investor, market)
                result.append({
                    "ticker": ticker, "name": name, "type": stock_type,
                    "indicators": indicators, "investor": investor,
                    "screen_reason": sell_reason or "보유 종목 (정기 체크)",
                    "priority": "SELL" if sell_ok else "WATCH",
                    "is_held": True,
                })
            else:
                buy_ok, buy_reason = _meets_buy_condition(indicators, investor, market)
                if buy_ok:
                    result.append({
                        "ticker": ticker, "name": name, "type": stock_type,
                        "indicators": indicators, "investor": investor,
                        "screen_reason": buy_reason,
                        "priority": "BUY",
                        "is_held": False,
                    })

            time.sleep(0.15)

        except Exception as e:
            continue

    result.sort(key=lambda x: (0 if x["is_held"] else 1))
    buy_cnt  = sum(1 for r in result if r["priority"] == "BUY")
    hold_cnt = sum(1 for r in result if r["priority"] in ("SELL", "WATCH"))
    print(f"✅ 스크리닝 완료: 매수후보 {buy_cnt}개 | 보유종목 {hold_cnt}개")
    return result

            # 보유 중: 매도 조건 체크
            if is_held:
                sell_ok, sell_reason = _meets_sell_condition(indicators)
                result.append({
                    "ticker": ticker, "name": name, "type": stock_type,
                    "indicators": indicators,
                    "screen_reason": sell_reason or "보유 종목 (정기 체크)",
                    "priority": "SELL" if sell_ok else "WATCH",
                    "is_held": True,
                })
            else:
                # 미보유: 매수 조건 체크
                buy_ok, buy_reason = _meets_buy_condition(indicators)
                if buy_ok:
                    result.append({
                        "ticker": ticker, "name": name, "type": stock_type,
                        "indicators": indicators,
                        "screen_reason": buy_reason,
                        "priority": "BUY",
                        "is_held": False,
                    })

            time.sleep(0.2)

        except Exception as e:
            print(f"  [{ticker}] {name} 스크린 실패: {e}")
            continue

    # 보유 종목 우선, 그 다음 매수 후보
    result.sort(key=lambda x: (0 if x["is_held"] else 1))

    buy_cnt  = sum(1 for r in result if r["priority"] == "BUY")
    sell_cnt = sum(1 for r in result if r["priority"] in ("SELL", "WATCH"))
    print(f"✅ 스크리닝 완료: 매수후보 {buy_cnt}개 | 보유종목 {sell_cnt}개")

    return result
