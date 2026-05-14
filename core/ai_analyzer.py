"""
OpenAI GPT 기반 주식 분석 모듈 (v2)
- ETF / 개별주식 분기 처리
- 4단계 분석 프레임워크
- 429 자동 재시도
"""
import json
import re
import time
from openai import OpenAI

MAX_RETRIES = 3


# ── 공통 응답 형식 ──────────────────────────────────────────
RESPONSE_FORMAT = """
응답은 반드시 아래 JSON만 출력하세요. 다른 텍스트, 마크다운 블록 없이 순수 JSON만:
{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0~100 (정수),
  "target_price": 목표가(정수),
  "stop_loss": 손절가(정수),
  "reason": "판단 근거 2~3줄"
}
"""

# ── ETF 전용 시스템 프롬프트 ───────────────────────────────
ETF_SYSTEM_PROMPT = """당신은 국내 ETF 중장기 투자 전문 애널리스트입니다.
ETF는 개별 종목보다 변동성이 낮고 지수를 추종합니다.
보수적이고 안정적인 관점에서 분석하세요.

분석 프레임워크 (4단계로 순서대로 판단):
1. 시장 분위기 — 코스피/코스닥 흐름이 ETF에 우호적인가?
2. 수급 — 외국인/기관이 지속적으로 매수하고 있는가?
3. 기술적 위치 — RSI, 이평선 기준으로 현재 구간은?
4. 종합 판단 — 지금 포지션을 취하거나 유지하는 게 합리적인가?

판단 기준:
- ETF는 RSI 40 이하 과매도 구간에서 분할매수 긍정적
- RSI 75 이상 과열 구간에서는 보수적으로 접근
- 인버스 ETF는 시장 하락 시 매수, 상승 시 매도 신호
- 신뢰도 55 미만이면 반드시 HOLD
""" + RESPONSE_FORMAT

# ── 개별주식 전용 시스템 프롬프트 ────────────────────────
STOCK_SYSTEM_PROMPT = """당신은 국내 개별 주식 분석 전문 퀀트 애널리스트입니다.
기술적 지표와 수급 데이터를 종합하여 중단기 관점에서 판단합니다.

분석 프레임워크 (4단계로 순서대로 판단):
1. 시장 분위기 — 코스피/코스닥 흐름이 섹터에 우호적인가?
2. 수급 — 외국인/기관 순매수가 지속되는가? 개인 역매수인가?
3. 기술적 위치 — RSI, 5일/20일 이평선 배열과 거래량 확인
4. 종합 판단 — 현재 리스크 대비 기대수익이 충분한가?

판단 기준:
- RSI 30 이하: 과매도 → 반등 가능성 검토
- RSI 70 이상: 과매수 → 매도 or 관망
- 5일선 > 20일선: 단기 상승 추세
- 외국인+기관 동반 순매수: 강한 긍정 신호
- 신뢰도 55 미만이면 반드시 HOLD
""" + RESPONSE_FORMAT


def _build_user_message(ticker: str, name: str, stock_type: str,
                        indicators: dict, investor: dict, market: dict) -> str:
    ohlcv_summary = "\n".join(
        f"  {d['date']}: 시가{d['open']:,.0f} 고가{d['high']:,.0f} "
        f"저가{d['low']:,.0f} 종가{d['close']:,.0f} 거래량{d['volume']:,}"
        for d in indicators.get("recent_ohlcv", [])[-5:]
    )
    return f"""
[종목] {name} ({ticker}) / 유형: {stock_type}

[현재가] {indicators['current_price']:,.0f}원
[기술적 지표]
  RSI(14): {indicators.get('rsi', 'N/A')}
  5일 이동평균: {indicators.get('ma5', 0):,.0f}원
  20일 이동평균: {indicators.get('ma20', 0):,.0f}원
  5일 평균거래량: {indicators.get('avg_volume_5d', 0):,.0f}주

[최근 5일 OHLCV]
{ohlcv_summary}

[수급 (최근 5일 순매수)]
  외국인: {investor.get('foreign_net_buy', 0):+,}주
  기관:   {investor.get('institution_net_buy', 0):+,}주
  개인:   {investor.get('individual_net_buy', 0):+,}주

[시장 현황]
  KOSPI:  {market.get('KOSPI', {}).get('current', 'N/A')} ({market.get('KOSPI', {}).get('change_rate', '0')}%)
  KOSDAQ: {market.get('KOSDAQ', {}).get('current', 'N/A')} ({market.get('KOSDAQ', {}).get('change_rate', '0')}%)

위 데이터를 4단계 프레임워크로 분석하고 JSON만 응답하세요.
"""


def analyze_stock(
    api_key: str,
    ticker: str,
    name: str,
    stock_type: str,          # "ETF" or "STOCK"
    indicators: dict,
    investor: dict,
    market: dict,
    model_name: str = "gpt-4o-mini",
) -> dict:
    """
    OpenAI GPT로 종목 분석 → {signal, confidence, target_price, stop_loss, reason}
    """
    client = OpenAI(api_key=api_key)

    system_prompt = ETF_SYSTEM_PROMPT if stock_type == "ETF" else STOCK_SYSTEM_PROMPT
    user_message  = _build_user_message(ticker, name, stock_type, indicators, investor, market)

    # 429 Rate Limit 자동 재시도
    raw = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            raw = response.choices[0].message.content.strip()
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                wait = (attempt + 1) * 10
                print(f"  ⏳ API 한도 초과 → {wait}초 대기 후 재시도 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                raise

    if raw is None:
        return {"signal": "HOLD", "confidence": 0, "reason": "API 한도 초과 — 다음 사이클에서 재시도"}

    # JSON 파싱
    result = _parse_ai_response(raw)

    result.setdefault("signal", "HOLD")
    result.setdefault("confidence", 0)
    result.setdefault("target_price", 0)
    result.setdefault("stop_loss", 0)
    result.setdefault("reason", "")
    return result


def _parse_ai_response(raw: str) -> dict:
    """Gemini 응답에서 JSON 추출 — 최대한 단순하고 확실한 방식"""

    # 핵심: 원본에서 첫 { ~ 마지막 } 사이만 추출 → 줄바꿈 제거 → 파싱
    start = raw.find("{")
    end   = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        block = raw[start:end+1]

        # 모든 줄바꿈/캐리지리턴을 공백으로 변환
        one_line = block.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        # trailing comma 제거
        one_line = re.sub(r",\s*}", "}", one_line)

        try:
            return json.loads(one_line)
        except json.JSONDecodeError:
            pass

        # 작은따옴표 → 큰따옴표
        one_line = one_line.replace("'", '"')
        try:
            return json.loads(one_line)
        except json.JSONDecodeError:
            pass

    # 최후의 수단: 정규식으로 키-값 직접 추출
    signal     = re.search(r'"?signal"?\s*:\s*"?(BUY|SELL|HOLD)"?', raw, re.IGNORECASE)
    confidence = re.search(r'"?confidence"?\s*:\s*(\d+)', raw)
    target     = re.search(r'"?target_price"?\s*:\s*(\d+)', raw)
    stop       = re.search(r'"?stop_loss"?\s*:\s*(\d+)', raw)
    # reason: 큰따옴표 사이 내용 (줄바꿈 포함)
    reason     = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)

    return {
        "signal":       signal.group(1).upper() if signal else "HOLD",
        "confidence":   int(confidence.group(1)) if confidence else 0,
        "target_price": int(target.group(1)) if target else 0,
        "stop_loss":    int(stop.group(1)) if stop else 0,
        "reason":       reason.group(1).replace("\n", " ") if reason else "",
    }
