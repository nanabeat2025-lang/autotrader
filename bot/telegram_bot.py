"""
텔레그램 봇 모듈 (Discord 대체)
알림 전송 + 명령어 처리

명령어 목록:
  /report      - 현재 포트폴리오 현황
  /잔고         - 예수금 조회
  /거래량        - 거래량 TOP10 조회
  /쿨다운        - 재매수 금지 종목 목록
  /쿨다운해제 종목명 - 특정 종목 쿨다운 즉시 해제
  /매수 종목명 n주 - 수동 매수
  /매도 종목명 n주 - 수동 매도
  /동기화        - 증권 계좌와 포지션 동기화
  /ai성과        - AI 정확도 통계

설치: pip install python-telegram-bot
"""
import asyncio
from datetime import datetime
from typing import Optional

import requests as http_requests

# python-telegram-bot v20+
try:
    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


# ─────────────────────────────────────────────────────────
# 단방향 알림 (봇 없이도 동작 — HTTP API 직접 호출)
# ─────────────────────────────────────────────────────────
def _send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML"):
    """텔레그램 메시지 전송 (동기 방식)"""
    if not token or not chat_id:
        print(f"[텔레그램 미설정] {text}")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        resp = http_requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print(f"텔레그램 전송 실패: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"텔레그램 오류: {e}")


def notify_buy(token: str, chat_id: str,
               ticker: str, name: str, price: float, qty: int, reason: str):
    text = (
        f"🟢 <b>매수 체결</b> — {name} ({ticker})\n"
        f"├ 체결가: <b>{price:,.0f}원</b>\n"
        f"├ 수량:   {qty}주\n"
        f"├ 금액:   {price*qty:,.0f}원\n"
        f"└ AI 근거: {reason}"
    )
    _send_message(token, chat_id, text)


def notify_sell(token: str, chat_id: str,
                ticker: str, name: str, price: float, qty: int,
                pnl_rate: float, pnl_amount: int, reason: str):
    emoji = "💰" if pnl_amount >= 0 else "🔴"
    sign  = "+" if pnl_amount >= 0 else ""
    text = (
        f"{emoji} <b>매도 체결</b> — {name} ({ticker})\n"
        f"├ 체결가: <b>{price:,.0f}원</b>\n"
        f"├ 수량:   {qty}주\n"
        f"├ 손익:   <b>{sign}{pnl_amount:,}원 ({pnl_rate:.2%})</b>\n"
        f"└ 사유:   {reason}"
    )
    _send_message(token, chat_id, text)


def notify_cycle_summary(token: str, chat_id: str, results: list[dict]):
    """분석 사이클 요약"""
    icons = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⬜", "ERROR": "❌"}
    lines = [f"<b>📊 분석 완료 — {datetime.now().strftime('%H:%M')}</b>\n"]
    for r in results:
        icon = icons.get(r.get("action", "HOLD"), "⬜")
        lines.append(f"{icon} <code>{r['ticker']}</code> {r['name']} → <b>{r.get('action','HOLD')}</b> ({r.get('confidence', '-')}%)")
    _send_message(token, chat_id, "\n".join(lines))


def notify_holiday_skip(token: str, chat_id: str):
    today = datetime.now().strftime("%Y-%m-%d (%a)")
    _send_message(token, chat_id, f"📅 오늘({today})은 휴장일입니다. 매매를 건너뜁니다.")


# ─────────────────────────────────────────────────────────
# 텔레그램 봇 (양방향 명령어)
# ─────────────────────────────────────────────────────────
def create_bot(token: str, chat_id: str, kis, watchlist: dict):
    """텔레그램 봇 생성. run_polling()으로 실행."""
    if not TELEGRAM_AVAILABLE:
        print("python-telegram-bot 미설치. pip install python-telegram-bot")
        return None

    app = Application.builder().token(token).build()

    def _only_owner(update: Update) -> bool:
        """봇 주인만 명령 허용"""
        return str(update.effective_chat.id) == str(chat_id)

    # ── /report ──────────────────────────────────────────
    async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        from core.trader import load_positions
        positions = load_positions()
        if not positions:
            await update.message.reply_text("📭 현재 보유 종목이 없습니다.")
            return
        lines = ["<b>📈 현재 포트폴리오</b>\n"]
        total_pnl = 0
        for ticker, pos in positions.items():
            try:
                pd = kis.get_stock_price(ticker)
                cur = float(pd.get("stck_prpr", pos["buy_price"]))
            except Exception:
                cur = float(pos["buy_price"])
            pnl_rate = (cur - pos["buy_price"]) / pos["buy_price"]
            pnl_amt  = int((cur - pos["buy_price"]) * pos["qty"])
            total_pnl += pnl_amt
            sign = "+" if pnl_rate >= 0 else ""
            lines.append(
                f"<code>{ticker}</code> {pos['name']} | {pos['qty']}주\n"
                f"  매수가 {pos['buy_price']:,.0f}원 → 현재 {cur:,.0f}원\n"
                f"  손익: <b>{sign}{pnl_amt:,}원 ({sign}{pnl_rate:.2%})</b>"
            )
        sign = "+" if total_pnl >= 0 else ""
        lines.append(f"\n<b>총 손익: {sign}{total_pnl:,}원</b>")
        await update.message.reply_html("\n".join(lines))

    # ── /잔고 ────────────────────────────────────────────
    async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        try:
            bal = kis.get_balance()
            s = bal.get("summary", {})
            cash  = int(s.get("dnca_tot_amt", 0))
            total = int(s.get("tot_evlu_amt", 0))
            await update.message.reply_html(
                f"💰 <b>계좌 현황</b>\n"
                f"├ 예수금:    {cash:,}원\n"
                f"└ 총 평가금액: {total:,}원"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 잔고 조회 실패: {e}")

    # ── /거래량 ──────────────────────────────────────────
    async def cmd_volume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        try:
            top10 = kis.get_volume_top10()
            lines = ["<b>📊 거래량 TOP 10</b>\n"]
            for i, item in enumerate(top10, 1):
                nm  = item.get("hts_kor_isnm", "")
                cd  = item.get("mksc_shrn_iscd", "")
                vol = int(item.get("acml_vol", 0))
                prc = int(item.get("stck_prpr", 0))
                lines.append(f"{i}. {nm} <code>({cd})</code> | {prc:,}원 | 거래량 {vol:,}")
            await update.message.reply_html("\n".join(lines))
        except Exception as e:
            await update.message.reply_text(f"❌ 거래량 조회 실패: {e}")

    # ── /쿨다운 ──────────────────────────────────────────
    async def cmd_cooldown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        from core.trader import get_all_cooldowns
        cds = get_all_cooldowns()
        if not cds:
            await update.message.reply_text("✅ 쿨다운 중인 종목이 없습니다.")
            return
        lines = ["<b>⏳ 쿨다운 목록 (재매수 금지)</b>\n"]
        for ticker, days in cds.items():
            name = watchlist.get(ticker, {}).get("name", ticker) if isinstance(watchlist.get(ticker), dict) else ticker
            lines.append(f"<code>{ticker}</code> {name} — {days}일 남음")
        lines.append("\n/쿨다운해제 종목명 으로 즉시 해제 가능")
        await update.message.reply_html("\n".join(lines))

    # ── /쿨다운해제 ──────────────────────────────────────
    async def cmd_clear_cooldown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        if not ctx.args:
            await update.message.reply_text("사용법: /쿨다운해제 종목코드\n예) /쿨다운해제 005930")
            return
        ticker = ctx.args[0].strip()
        from core.trader import clear_cooldown
        clear_cooldown(ticker)
        await update.message.reply_text(f"✅ {ticker} 쿨다운 해제 완료")

    # ── /매도 ────────────────────────────────────────────
    async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        # 사용법: /매도 005930 10
        if len(ctx.args) < 2:
            await update.message.reply_text("사용법: /매도 종목코드 수량\n예) /매도 005930 10")
            return
        ticker = ctx.args[0]
        try:
            qty = int(ctx.args[1])
        except ValueError:
            await update.message.reply_text("수량은 숫자로 입력하세요.")
            return

        from core.trader import load_positions, save_positions, log_trade
        positions = load_positions()
        if ticker not in positions:
            await update.message.reply_text(f"❌ {ticker} 보유 중이 아닙니다.")
            return

        pos      = positions[ticker]
        sell_qty = min(qty, pos["qty"])
        try:
            kis.sell_market(ticker, sell_qty)
            pd  = kis.get_stock_price(ticker)
            cur = float(pd.get("stck_prpr", pos["buy_price"]))
            pnl_rate = (cur - pos["buy_price"]) / pos["buy_price"]
            pnl_amt  = int((cur - pos["buy_price"]) * sell_qty)
            if sell_qty >= pos["qty"]:
                del positions[ticker]
            else:
                positions[ticker]["qty"] -= sell_qty
            save_positions(positions)
            log_trade({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker": ticker, "name": pos.get("name", ticker),
                "action": "SELL", "price": cur, "qty": sell_qty,
                "pnl_rate": f"{pnl_rate:.2%}", "pnl_amount": pnl_amt,
                "reason": "수동 매도 (텔레그램 명령)",
            })
            sign = "+" if pnl_amt >= 0 else ""
            await update.message.reply_html(
                f"✅ <b>{pos.get('name', ticker)}</b> {sell_qty}주 매도 완료\n"
                f"체결가: {cur:,.0f}원 | 손익: <b>{sign}{pnl_amt:,}원 ({sign}{pnl_rate:.2%})</b>"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 매도 실패: {e}")

    # ── /매수 ────────────────────────────────────────────
    async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        if len(ctx.args) < 2:
            await update.message.reply_text("사용법: /매수 종목코드 수량\n예) /매수 005930 5")
            return
        ticker = ctx.args[0]
        try:
            qty = int(ctx.args[1])
        except ValueError:
            await update.message.reply_text("수량은 숫자로 입력하세요.")
            return
        try:
            kis.buy_market(ticker, qty)
            pd  = kis.get_stock_price(ticker)
            cur = float(pd.get("stck_prpr", 0))
            name = watchlist.get(ticker, {}).get("name", ticker) if isinstance(watchlist.get(ticker), dict) else ticker
            from core.trader import load_positions, save_positions, log_trade
            positions = load_positions()
            positions[ticker] = {
                "name": name, "qty": qty, "buy_price": cur, "target_price": 0,
                "bought_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_positions(positions)
            log_trade({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker": ticker, "name": name, "action": "BUY",
                "price": cur, "qty": qty, "reason": "수동 매수 (텔레그램 명령)",
            })
            await update.message.reply_html(
                f"✅ <b>{name}</b> {qty}주 매수 완료\n체결가: {cur:,.0f}원"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ 매수 실패: {e}")

    # ── /동기화 ──────────────────────────────────────────
    async def cmd_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        try:
            synced = kis.sync_positions_from_broker()
            await update.message.reply_text(f"✅ 계좌 동기화 완료: {len(synced)}개 종목 반영")
        except Exception as e:
            await update.message.reply_text(f"❌ 동기화 실패: {e}")

    # ── /ai성과 ──────────────────────────────────────────
    async def cmd_ai_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        from core.ai_tracker import get_stats
        s = get_stats()
        if s["total"] == 0:
            await update.message.reply_text("📊 아직 완료된 매매 데이터가 없습니다.")
            return
        lines = [
            "<b>🤖 AI 정확도 통계</b>\n",
            f"├ 총 매매:      {s['total']}건",
            f"├ 승률:         <b>{s['win_rate']}%</b>",
            f"├ 평균 손익률:  <b>{s['avg_pnl']:+.2f}%</b>",
            f"└ 목표가 도달률: {s['target_hit_rate']}%",
            "\n<b>[신뢰도별 성과]</b>",
        ]
        for bucket, stat in s.get("by_confidence", {}).items():
            lines.append(f"  {bucket}%: 승률 {stat['win_rate']}% | 평균 {stat['avg_pnl']:+.2f}% ({stat['count']}건)")
        await update.message.reply_html("\n".join(lines))

    # ── /골든크로스 ────────────────────────────────────────
    async def cmd_golden_cross(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        /골든크로스         → 기본 5일/20일 스캔
        /골든크로스 중기     → 20일/60일 스캔
        /골든크로스 장기     → 20일/120일 스캔
        """
        if not _only_owner(update): return
        from core.golden_cross import scan_golden_cross, format_scan_result

        # 기간 파싱
        arg = ctx.args[0] if ctx.args else "short"
        if arg in ("mid", "중기"):
            short_p, long_p = 20, 60
        elif arg in ("long", "장기"):
            short_p, long_p = 20, 120
        else:
            short_p, long_p = 5, 20

        await update.message.reply_text(
            f"🔍 골든크로스 스캔 중... ({short_p}일/{long_p}일)\n잠시만 기다려주세요 ⏳"
        )

        try:
            result = scan_golden_cross(
                kis,
                short_period=short_p,
                long_period=long_p,
                include_near=True,
            )
            msg = format_scan_result(result)

            # 텔레그램 메시지 길이 제한 (4096자)
            if len(msg) > 4000:
                parts = msg.split("\n\n")
                for part in parts:
                    if part.strip():
                        await update.message.reply_html(part)
            else:
                await update.message.reply_html(msg)
        except Exception as e:
            await update.message.reply_text(f"❌ 골든크로스 스캔 실패: {e}")

    # ── /골든추가 (골든크로스 종목을 감시목록에 추가) ────
    async def cmd_golden_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """
        /골든추가 005930  → 골든크로스 발생 종목을 감시목록에 추가
        """
        if not _only_owner(update): return
        if not ctx.args:
            await update.message.reply_text("사용법: /골든추가 종목코드\n예) /골든추가 005930")
            return
        ticker = ctx.args[0].strip()
        from core.golden_cross import SCAN_UNIVERSE
        name = SCAN_UNIVERSE.get(ticker, ticker)
        try:
            pd = kis.get_stock_price(ticker)
            name = pd.get("rprs_mrkt_kor_name", name) or name
        except Exception:
            pass

        # settings의 WATCHLIST에 동적 추가 (런타임)
        from config import settings
        if ticker not in settings.WATCHLIST:
            settings.WATCHLIST[ticker] = {"name": name, "type": "STOCK"}
            await update.message.reply_html(
                f"✅ <b>{name}</b> (<code>{ticker}</code>)을 감시목록에 추가했습니다.\n"
                f"다음 분석 사이클에서 AI가 매매 판단합니다."
            )
        else:
            await update.message.reply_text(f"이미 감시목록에 있습니다: {ticker}")

    # ── /help ──────────────────────────────────────────
    async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _only_owner(update): return
        text = (
            "<b>🤖 AI 자동매매 봇 명령어</b>\n\n"
            "<b>[포트폴리오]</b>\n"
            "/report — 현재 보유 종목 현황\n"
            "/balance — 예수금 조회\n"
            "/sync — 증권 계좌 동기화\n\n"
            "<b>[매매]</b>\n"
            "/buy [종목코드] [수량] — 수동 매수\n"
            "/sell [종목코드] [수량] — 수동 매도\n"
            "/cooldown — 재매수 금지 목록\n"
            "/cooldown_off [종목코드] — 쿨다운 해제\n\n"
            "<b>[분석]</b>\n"
            "/golden — 5일/20일 골든크로스 스캔\n"
            "/golden mid — 20일/60일 스캔\n"
            "/golden long — 20일/120일 스캔\n"
            "/golden_add [종목코드] — 감시목록에 추가\n"
            "/volume — 거래량 TOP10\n"
            "/ai_stats — AI 정확도 통계\n\n"
            "/help — 이 메시지"
        )
        await update.message.reply_html(text)

    # 명령어 등록
    app.add_handler(CommandHandler("report",       cmd_report))
    app.add_handler(CommandHandler("balance",      cmd_balance))
    app.add_handler(CommandHandler("volume",       cmd_volume))
    app.add_handler(CommandHandler("cooldown",     cmd_cooldown))
    app.add_handler(CommandHandler("cooldown_off", cmd_clear_cooldown))
    app.add_handler(CommandHandler("sell",          cmd_sell))
    app.add_handler(CommandHandler("buy",           cmd_buy))
    app.add_handler(CommandHandler("sync",          cmd_sync))
    app.add_handler(CommandHandler("ai_stats",      cmd_ai_stats))
    app.add_handler(CommandHandler("golden",       cmd_golden_cross))
    app.add_handler(CommandHandler("golden_add",   cmd_golden_add))
    app.add_handler(CommandHandler("help",          cmd_help))
    app.add_handler(CommandHandler("start",         cmd_help))

    return app
