"""
메인 자동매매 실행 파일 v2
- 공휴일/휴장일 자동 감지
- 하루 3회 스케줄 (09:30 / 13:00 / 15:00)
- OpenAI GPT 분석
- 텔레그램 알림
- 계좌 자동 동기화
- AI 정확도 추적

실행 방법:
  python main.py          # 스케줄러 모드
  python main.py --now    # 즉시 1회 실행 (테스트)
  python main.py --dry    # DRY-RUN (실제 주문 없음)
  python main.py --bot    # 텔레그램 봇만 실행
"""
import argparse
import time
import schedule
import threading
from datetime import datetime

from config.settings import (
    KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, KIS_IS_MOCK,
    OPENAI_API_KEY, OPENAI_MODEL,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    WATCHLIST, USE_VOLUME_TOP10, SCHEDULE_TIMES,
)
from api.kis_api import KISApi
from core.indicators import build_indicators, summarize_investor
from core.ai_analyzer import analyze_stock
from core.trader import decide_and_execute
from bot.telegram_bot import (
    notify_buy, notify_sell, notify_cycle_summary, notify_holiday_skip, create_bot,
)


# ─────────────────────────────────────────────────────────
# 분석 사이클
# ─────────────────────────────────────────────────────────
def run_cycle(kis: KISApi, dry_run: bool = False):
    print(f"\n{'='*60}")
    print(f"🤖 분석 사이클 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # ── 휴장일 체크 ─────────────────────────────────────
    if kis.is_holiday_today():
        print("📅 오늘은 휴장일 → 매매 스킵")
        notify_holiday_skip(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        return

    # ── 시장 현황 ────────────────────────────────────────
    try:
        market = kis.get_market_index()
        kospi  = market.get("KOSPI",  {})
        kosdaq = market.get("KOSDAQ", {})
        print(f"KOSPI: {kospi.get('current')} ({kospi.get('change_rate')}%)")
        print(f"KOSDAQ: {kosdaq.get('current')} ({kosdaq.get('change_rate')}%)")
    except Exception as e:
        print(f"시장 지수 조회 실패: {e}")
        market = {}

    # ── 스크리너로 분석 대상 종목 선정 ─────────────────────
    from core.screener import screen_stocks
    from core.trader import load_positions
    held_tickers = list(load_positions().keys())
    candidates = screen_stocks(kis, held_tickers=held_tickers)

    if not candidates:
        print("📭 조건 충족 종목 없음 — 다음 사이클에서 재시도")
        return

    print(f"\n📋 분석 대상: {len(candidates)}개 종목")
    summary_results = []

    for item in candidates:
        ticker        = item["ticker"]
        name          = item["name"]
        stock_type    = item["type"]
        indicators    = item["indicators"]
        screen_reason = item["screen_reason"]

        print(f"\n[{ticker}] {name} ({stock_type}) — {screen_reason}")

        try:
            investor_raw = kis.get_investor_trend(ticker)
            investor     = summarize_investor(investor_raw)

            print(f"  현재가: {indicators['current_price']:,.0f}원 | "
                  f"RSI: {indicators['rsi']} | "
                  f"MACD: {indicators.get('macd', {}).get('histogram', 'N/A')}")

            # OpenAI GPT 분석
            ai_result = analyze_stock(
                api_key=OPENAI_API_KEY,
                ticker=ticker,
                name=name,
                stock_type=stock_type,
                indicators=indicators,
                investor=investor,
                market=market,
                model_name=OPENAI_MODEL,
            )
            print(f"  GPT → {ai_result['signal']} "
                  f"({ai_result['confidence']}%) | {ai_result['reason'][:60]}...")

            # 매수/매도 실행
            decision = decide_and_execute(
                kis, ticker, name,
                indicators["current_price"],
                ai_result,
                dry_run=dry_run,
            )
            action = decision["action"]
            print(f"  실행: {action} — {decision['reason']}")

            # 텔레그램 알림
            if action == "BUY":
                notify_buy(
                    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                    ticker, name, indicators["current_price"],
                    decision["qty"], decision["reason"],
                )
            elif action == "SELL":
                notify_sell(
                    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                    ticker, name, indicators["current_price"],
                    decision["qty"],
                    decision.get("pnl_rate", 0),
                    decision.get("pnl_amount", 0),
                    decision["reason"],
                )

            summary_results.append({
                "ticker":     ticker,
                "name":       name,
                "action":     action,
                "confidence": ai_result["confidence"],
            })
            time.sleep(3)  # API rate limit 방지 (무료 티어: 분당 제한 있음)

        except Exception as e:
            print(f"  ❌ 오류: {e}")
            summary_results.append({
                "ticker": ticker, "name": name, "action": "ERROR", "confidence": 0
            })

    # ── 사이클 요약 알림 ─────────────────────────────────
    if summary_results:
        notify_cycle_summary(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, summary_results)

    # ── 골든크로스 자동 스캔 (09:30 사이클에서만) ────────
    now_h = datetime.now().hour
    if now_h < 10:  # 아침 사이클에서만 실행 (하루 1회)
        print("\n🔍 골든크로스 자동 스캔 중...")
        try:
            from core.golden_cross import scan_golden_cross, format_scan_result
            from bot.telegram_bot import _send_message
            gc_result = scan_golden_cross(kis, short_period=5, long_period=20)
            if gc_result["golden"]:
                msg = format_scan_result(gc_result)
                _send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
                print(f"  🟢 골든크로스 {len(gc_result['golden'])}건 발견 → 텔레그램 알림")
            else:
                print("  골든크로스 발생 종목 없음")
        except Exception as e:
            print(f"  골든크로스 스캔 실패: {e}")

    print(f"\n✅ 사이클 완료 ({len(summary_results)}개 종목 분석)")


# ─────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AI 자동매매 봇 v2 (OpenAI + 텔레그램)")
    parser.add_argument("--now", action="store_true", help="즉시 1회 실행")
    parser.add_argument("--dry", action="store_true", help="DRY-RUN (실제 주문 없음)")
    parser.add_argument("--bot", action="store_true", help="텔레그램 봇만 실행")
    args = parser.parse_args()

    kis = KISApi(KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, is_mock=KIS_IS_MOCK)

    print("🚀 AI 자동매매 봇 v2 시작")
    print(f"   모드:   {'모의투자' if KIS_IS_MOCK else '실전투자'} | {'DRY-RUN' if args.dry else 'LIVE'}")
    print(f"   AI:     OpenAI ({OPENAI_MODEL})")
    print(f"   알림:   텔레그램")
    print(f"   종목수: {len(WATCHLIST)}개")
    print(f"   스케줄: {', '.join(SCHEDULE_TIMES)}")

    # 텔레그램 봇 (별도 스레드로 상시 실행)
    bot_app = create_bot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, kis, WATCHLIST)

    if args.bot:
        print("\n📱 텔레그램 봇 단독 실행 모드")
        if bot_app:
            bot_app.run_polling()
        return

    if args.now or args.dry:
        run_cycle(kis, dry_run=args.dry)
        return

    # 텔레그램 봇을 백그라운드 스레드에서 실행
    if bot_app:
        def run_bot():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot_app.run_polling()

        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        print("📱 텔레그램 봇 백그라운드 실행 중...")

    # 스케줄 등록
    def job():
        run_cycle(kis, dry_run=False)

    for t in SCHEDULE_TIMES:
        schedule.every().day.at(t).do(job)

    print(f"⏰ 스케줄 등록: {' / '.join(SCHEDULE_TIMES)}")
    print("   (Ctrl+C 로 종료)\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
