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


def _is_etf(name: str) -> bool:
    """ETF 종목명 필터링 (브랜드 prefix로 판별)"""
    etf_brands = [
        "KODEX", "TIGER", "KBSTAR", "ARIRANG", "HANARO", "WOORI",
        "MASTER", "ACE", "KOACT", "PLUS", "RISE", "TIMEFOLIO",
        "BNK", "SOL", "SSO", "QV", "ZIG", "ETN", "ETF",
    ]
    name_upper = name.upper()
    return any(brand in name_upper for brand in etf_brands)


# ── 폴백 주요 종목 리스트 (시가총액 API 실패 시 사용) ────
MAJOR_STOCKS_FALLBACK = {
    # KOSPI 대형주
    "005930": "삼성전자", "000660": "SK하이닉스", "207940": "삼성바이오로직스",
    "373220": "LG에너지솔루션", "005380": "현대차", "035420": "NAVER",
    "000270": "기아", "006400": "삼성SDI", "035720": "카카오", "051910": "LG화학",
    "068270": "셀트리온", "105560": "KB금융", "055550": "신한지주",
    "012330": "현대모비스", "066570": "LG전자", "003670": "포스코퓨처엠",
    "017670": "SK텔레콤", "030200": "KT", "034730": "SK", "003550": "LG",
    "009150": "삼성전기", "033780": "KT&G", "086790": "하나금융지주",
    "316140": "우리금융지주", "010130": "고려아연", "011200": "HMM",
    "047810": "한국항공우주", "267260": "HD현대일렉트릭", "402340": "SK스퀘어",
    "032830": "삼성생명", "323410": "카카오뱅크", "036570": "엔씨소프트",
    "010950": "S-Oil", "024110": "기업은행", "138040": "메리츠금융지주",
    "028260": "삼성물산", "015760": "한국전력", "316140": "우리금융지주",
    "088350": "한화생명", "001450": "현대해상", "071050": "한국금융지주",
    "139480": "이마트", "097950": "CJ제일제당", "078930": "GS",
    "267250": "HD현대중공업", "010140": "삼성중공업", "042660": "한화오션",
    "009540": "HD한국조선해양", "029780": "삼성카드", "086280": "현대글로비스",
    "009830": "한화솔루션", "180640": "한진칼", "180640": "한진칼",
    "000810": "삼성화재", "021240": "코웨이", "008770": "호텔신라",
    "069960": "현대백화점", "000150": "두산", "005490": "POSCO홀딩스",
    "001040": "CJ", "047040": "대우건설", "036460": "한국가스공사",
    # KOSDAQ 대형주
    "247540": "에코프로비엠", "086520": "에코프로", "091990": "셀트리온헬스케어",
    "263750": "펄어비스", "293490": "카카오게임즈", "035900": "JYP Ent.",
    "041510": "에스엠", "112040": "위메이드", "036570": "엔씨소프트",
    "066970": "엘앤에프", "058470": "리노공업", "278280": "천보",
    "121600": "나노신소재", "067160": "아프리카TV", "095340": "ISC",
    "240810": "원익IPS", "036930": "주성엔지니어링", "108860": "셀바스AI",
    "095700": "제넥신", "214150": "클래시스", "298540": "더네이쳐홀딩스",
    "032500": "케이엠더블유", "039030": "이오테크닉스", "278280": "천보",
    "067310": "하나마이크론", "131970": "테스나", "131290": "티에스이",
    "036540": "SFA반도체", "041830": "위메이드플레이",
    "182400": "에코프로에이치엔", "024720": "한국콜마", "143240": "사람인",
}


def build_universe(kis) -> dict:
    """
    동적 스캔 유니버스 구성 (ETF 제외 - 개별 종목만)
    - 주요 종목 폴백 리스트 (~80개)
    - KOSPI 시가총액 상위 100 (API 작동 시)
    - KOSDAQ 시가총액 상위 100 (API 작동 시)
    - 거래량 상위 100
    """
    universe = {}

    print("🌐 전 종목 유니버스 구성 중 (ETF 제외)...")

    # 0) 폴백 주요 종목 (시가총액 API 실패 대비)
    for ticker, name in MAJOR_STOCKS_FALLBACK.items():
        if not _is_etf(name):
            universe[ticker] = {"name": name, "type": "STOCK"}
    print(f"  주요 종목 폴백: {len(universe)}개")

    # 1) KOSPI 시가총액 상위 100
    try:
        kospi_top = kis.get_market_cap_top(market="J", n=100)
        added = 0
        for item in kospi_top:
            ticker = item.get("mksc_shrn_iscd", "")
            name   = item.get("hts_kor_isnm", ticker)
            if ticker and len(ticker) == 6 and not _is_etf(name):
                if ticker not in universe:
                    added += 1
                universe[ticker] = {"name": name, "type": "STOCK"}
        if kospi_top:
            print(f"  KOSPI 시가총액 상위: +{added}개")
    except Exception as e:
        print(f"  KOSPI 시가총액 조회 실패: {e}")

    # 2) KOSDAQ 시가총액 상위 100
    try:
        kosdaq_top = kis.get_market_cap_top(market="Q", n=100)
        added = 0
        for item in kosdaq_top:
            ticker = item.get("mksc_shrn_iscd", "")
            name   = item.get("hts_kor_isnm", ticker)
            if ticker and len(ticker) == 6 and not _is_etf(name):
                if ticker not in universe:
                    added += 1
                universe[ticker] = {"name": name, "type": "STOCK"}
        if kosdaq_top:
            print(f"  KOSDAQ 시가총액 상위: +{added}개")
    except Exception as e:
        print(f"  KOSDAQ 시가총액 조회 실패: {e}")

    # 3) 거래량 상위 100 (ETF 자동 제외)
    try:
        vol_top = kis.get_volume_top(n=100)
        added = 0
        for item in vol_top:
            ticker = item.get("mksc_shrn_iscd", "")
            name   = item.get("hts_kor_isnm", ticker)
            if ticker and len(ticker) == 6:
                if _is_etf(name):
                    continue
                if ticker not in universe:
                    added += 1
                universe[ticker] = {"name": name, "type": "STOCK"}
        print(f"  거래량 상위: +{added}개")
    except Exception as e:
        print(f"  거래량 상위 조회 실패: {e}")

    print(f"✅ 유니버스 구성 완료: 총 {len(universe)}개 개별 종목\n")
    return universe


def _meets_buy_condition(indicators: dict, investor: dict = None, market: dict = None) -> tuple[bool, str]:
    """
    매수 후보 조건 체크 (반등 포착 + 단순 조건 OR)
    Returns: (조건충족여부, 충족된 조건 설명)
    """
    rsi       = indicators.get("rsi") or 50
    macd      = indicators.get("macd", {}) or {}
    bb        = indicators.get("bollinger", {}) or {}
    vol_spike = indicators.get("volume_spike", {}) or {}
    rsi_uturn = indicators.get("rsi_uturn", {}) or {}
    bb_break  = indicators.get("bb_breakout", {}) or {}
    ohlcv     = indicators.get("recent_ohlcv", []) or []
    ma5       = indicators.get("ma5", 0) or 0
    ma20      = indicators.get("ma20", 0) or 0
    investor  = investor or {}
    market    = market or {}

    reasons = []

    # ── 시장 분위기 (코스피 -1.5% 이상 하락 시 매수 신중) ──
    kospi_rate = float(market.get("KOSPI", {}).get("change_rate", 0) or 0)
    if kospi_rate <= -1.5:
        if rsi < 30:
            reasons.append(f"시장급락({kospi_rate:.1f}%)+RSI극과매도({rsi})")
        return len(reasons) > 0, " | ".join(reasons)

    # ── 강한 매수 신호 (반등 포착) ──────────────────────────
    if rsi_uturn.get("is_uturn"):
        rsi_t = rsi_uturn.get("rsi_today")
        rsi_y = rsi_uturn.get("rsi_yesterday")
        reasons.append(f"⭐RSI U턴({rsi_y}→{rsi_t})")

    if bb_break.get("is_breakout"):
        reasons.append("⭐볼린저 하단복귀")

    if macd.get("cross") == "GOLDEN" and vol_spike.get("is_spike"):
        reasons.append(f"⭐MACD골든+거래량{vol_spike.get('ratio', 0):.1f}배")

    # ── 일반 매수 신호 (단순 조건) ───────────────────────────
    if rsi < 50:
        reasons.append(f"RSI 중립이하({rsi})")

    if macd.get("cross") == "GOLDEN":
        reasons.append("MACD 골든크로스")

    bb_pos = bb.get("position")
    if bb_pos is not None and bb_pos < 0.3:
        reasons.append(f"볼린저 하단권({bb_pos:.2f})")

    if ma5 > 0 and ma20 > 0 and ma5 > ma20:
        reasons.append("5일선>20일선")

    if vol_spike.get("is_spike") and len(ohlcv) >= 2:
        if ohlcv[-1]["close"] > ohlcv[-2]["close"]:
            reasons.append(f"거래량 급증({vol_spike.get('ratio', 0):.1f}배)+양봉")

    # ── 수급 ────────────────────────────────────────────────
    if investor.get("foreign_net_buy", 0) > 0:
        reasons.append(f"외국인매수")
    if investor.get("institution_net_buy", 0) > 0:
        reasons.append(f"기관매수")

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

            # 💰 예산 초과 종목 제외 (보유 중이 아닌 경우만)
            from config.settings import MAX_BUDGET_PER_STOCK
            is_held = ticker in held_tickers
            if not is_held and indicators["current_price"] > MAX_BUDGET_PER_STOCK:
                continue

            # 수급 데이터
            investor = {}
            try:
                investor_raw = kis.get_investor_trend(ticker)
                investor = summarize_investor(investor_raw)
            except Exception:
                pass

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
