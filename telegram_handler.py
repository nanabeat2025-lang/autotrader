"""
텔레그램 명령어 처리기 (GitHub Actions용)
5분마다 실행되어 새 메시지를 확인하고 응답
polling 없이 getUpdates API로 동작
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime

import requests

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, KIS_IS_MOCK,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WATCHLIST,
)
from api.kis_api import KISApi

OFFSET_PATH = Path("data/telegram_offset.txt")


def get_updates(token: str, offset: int = 0) -> list:
    """텔레그램 새 메시지 가져오기"""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"offset": offset, "timeout": 5}
    resp = requests.get(url, params=params, timeout=10)
    if resp.ok:
        return resp.json().get("result", [])
    return []


def send_reply(token: str, chat_id: str, text: str):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)


def load_offset() -> int:
    OFFSET_PATH.parent.mkdir(exist_ok=True)
    if OFFSET_PATH.exists():
        try:
            return int(OFFSET_PATH.read_text().strip())
        except ValueError:
            return 0
    return 0


def save_offset(offset: int):
    OFFSET_PATH.parent.mkdir(exist_ok=True)
    OFFSET_PATH.write_text(str(offset))


def handle_command(command: str, args: list, kis) -> str:
    """명령어 처리 → 응답 텍스트 반환"""

    if command in ("/help", "/start"):
        return (
            "<b>🤖 AI 자동매매 봇 명령어</b>\n\n"
            "<b>[포트폴리오]</b>\n"
            "/report — 보유 종목 현황\n"
            "/balance — 예수금 조회\n"
            "/sync — 계좌 동기화\n\n"
            "<b>[매매]</b>\n"
            "/buy 종목코드 수량\n"
            "/sell 종목코드 수량\n"
            "/cooldown — 쿨다운 목록\n"
            "/cooldown_off 종목코드\n\n"
            "<b>[분석]</b>\n"
            "/volume — 거래량 TOP10\n"
            "/ai_stats — AI 성과\n"
            "/golden — 5/20/60 정배열 종목\n"
        )

    elif command == "/report":
        from core.trader import load_positions
        positions = load_positions()
        if not positions:
            return "📭 현재 보유 종목이 없습니다."
        lines = ["<b>📈 현재 포트폴리오</b>\n"]
        total_pnl = 0
        for ticker, pos in positions.items():
            try:
                pd = kis.get_stock_price(ticker)
                cur = float(pd.get("stck_prpr", pos["buy_price"]))
            except Exception:
                cur = float(pos["buy_price"])
            pnl_rate = (cur - pos["buy_price"]) / pos["buy_price"]
            pnl_amt = int((cur - pos["buy_price"]) * pos["qty"])
            total_pnl += pnl_amt
            sign = "+" if pnl_rate >= 0 else ""
            lines.append(
                f"<code>{ticker}</code> {pos['name']} | {pos['qty']}주\n"
                f"  {pos['buy_price']:,.0f}원 → {cur:,.0f}원\n"
                f"  <b>{sign}{pnl_amt:,}원 ({sign}{pnl_rate:.2%})</b>"
            )
        sign = "+" if total_pnl >= 0 else ""
        lines.append(f"\n<b>총 손익: {sign}{total_pnl:,}원</b>")
        return "\n".join(lines)

    elif command == "/balance":
        try:
            bal = kis.get_balance()
            s = bal.get("summary", {})
            cash = int(s.get("dnca_tot_amt", 0))
            total = int(s.get("tot_evlu_amt", 0))
            return f"💰 <b>계좌 현황</b>\n├ 예수금: {cash:,}원\n└ 총 평가: {total:,}원"
        except Exception as e:
            return f"❌ 잔고 조회 실패: {e}"

    elif command == "/cooldown":
        from core.trader import get_all_cooldowns
        cds = get_all_cooldowns()
        if not cds:
            return "✅ 쿨다운 중인 종목이 없습니다."
        lines = ["<b>⏳ 쿨다운 목록</b>\n"]
        for ticker, days in cds.items():
            lines.append(f"<code>{ticker}</code> — {days}일 남음")
        return "\n".join(lines)

    elif command == "/cooldown_off":
        if not args:
            return "사용법: /cooldown_off 종목코드"
        from core.trader import clear_cooldown
        clear_cooldown(args[0])
        return f"✅ {args[0]} 쿨다운 해제 완료"

    elif command == "/volume":
        try:
            top10 = kis.get_volume_top10()
            lines = ["<b>📊 거래량 TOP 10</b>\n"]
            for i, item in enumerate(top10, 1):
                nm = item.get("hts_kor_isnm", "")
                cd = item.get("mksc_shrn_iscd", "")
                vol = int(item.get("acml_vol", 0))
                lines.append(f"{i}. {nm} <code>({cd})</code> | 거래량 {vol:,}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 거래량 조회 실패: {e}"

    elif command == "/ai_stats":
        from core.ai_tracker import get_stats
        s = get_stats()
        if s["total"] == 0:
            return "📊 아직 완료된 매매 데이터가 없습니다."
        return (
            f"<b>🤖 AI 정확도 통계</b>\n\n"
            f"├ 총 매매: {s['total']}건\n"
            f"├ 승률: <b>{s['win_rate']}%</b>\n"
            f"├ 평균 손익률: <b>{s['avg_pnl']:+.2f}%</b>\n"
            f"└ 목표가 도달률: {s['target_hit_rate']}%"
        )

    elif command == "/golden":
        try:
            from core.golden_cross import scan_triple_alignment, format_triple_alignment
            result = scan_triple_alignment(kis, max_stocks=150)
            return format_triple_alignment(result)
        except Exception as e:
            return f"❌ 정배열 스캔 실패: {e}"

    elif command == "/sync":
        try:
            synced = kis.sync_positions_from_broker()
            return f"✅ 계좌 동기화 완료: {len(synced)}개 종목"
        except Exception as e:
            return f"❌ 동기화 실패: {e}"

    elif command == "/buy":
        if len(args) < 2:
            return "사용법: /buy 종목코드 수량\n예) /buy 005930 5"
        ticker, qty = args[0], int(args[1])
        try:
            kis.buy_market(ticker, qty)
            pd = kis.get_stock_price(ticker)
            cur = float(pd.get("stck_prpr", 0))
            from core.trader import load_positions, save_positions, log_trade
            positions = load_positions()
            name = WATCHLIST.get(ticker, {}).get("name", ticker) if isinstance(WATCHLIST.get(ticker), dict) else ticker
            positions[ticker] = {"name": name, "qty": qty, "buy_price": cur, "target_price": 0,
                                 "bought_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            save_positions(positions)
            log_trade({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ticker": ticker,
                        "name": name, "action": "BUY", "price": cur, "qty": qty, "reason": "수동 매수 (텔레그램)"})
            return f"✅ <b>{name}</b> {qty}주 매수 완료\n체결가: {cur:,.0f}원"
        except Exception as e:
            return f"❌ 매수 실패: {e}"

    elif command == "/sell":
        if len(args) < 2:
            return "사용법: /sell 종목코드 수량\n예) /sell 005930 5"
        ticker, qty = args[0], int(args[1])
        from core.trader import load_positions, save_positions, log_trade
        positions = load_positions()
        if ticker not in positions:
            return f"❌ {ticker} 보유 중이 아닙니다."
        pos = positions[ticker]
        try:
            kis.sell_market(ticker, min(qty, pos["qty"]))
            pd = kis.get_stock_price(ticker)
            cur = float(pd.get("stck_prpr", pos["buy_price"]))
            pnl_rate = (cur - pos["buy_price"]) / pos["buy_price"]
            pnl_amt = int((cur - pos["buy_price"]) * min(qty, pos["qty"]))
            if qty >= pos["qty"]:
                del positions[ticker]
            else:
                positions[ticker]["qty"] -= qty
            save_positions(positions)
            sign = "+" if pnl_amt >= 0 else ""
            return f"✅ <b>{pos['name']}</b> {qty}주 매도 완료\n체결가: {cur:,.0f}원 | 손익: <b>{sign}{pnl_amt:,}원</b>"
        except Exception as e:
            return f"❌ 매도 실패: {e}"

    return "❓ 알 수 없는 명령어입니다. /help 를 입력해보세요."


def is_korean_holiday() -> bool:
    """한국 공휴일 + 주말 확인"""
    from datetime import date
    today = date.today()
    if today.weekday() >= 5:
        return True
    try:
        import holidays
        kr_holidays = holidays.SouthKorea()
        if today in kr_holidays:
            return True
    except ImportError:
        major_holidays = {
            (1, 1), (3, 1), (5, 5), (6, 6),
            (8, 15), (10, 3), (10, 9), (12, 25),
        }
        if (today.month, today.day) in major_holidays:
            return True
    return False


def is_market_hours() -> bool:
    """한국 주식시장 운영시간 확인 (평일 09:00 ~ 16:00 KST)"""
    from datetime import datetime, timezone, timedelta
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    hour = now.hour
    # 09:00 ~ 15:59 KST 사이만 시장 시간으로 인정
    return 9 <= hour < 16


def main():
    """새 메시지 확인 → 명령어 처리 → 응답"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 설정 없음, 스킵")
        return

    # 공휴일/주말은 KIS API 호출 안 함
    if is_korean_holiday():
        print("📅 휴장일(공휴일/주말) - KIS API 호출 스킵")
        return

    # 장 시간 외에는 KIS API 호출 안 함
    if not is_market_hours():
        print("⏰ 장 외 시간 - KIS API 호출 스킵")
        return

    kis = KISApi(KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, is_mock=KIS_IS_MOCK)
    offset = load_offset()
    updates = get_updates(TELEGRAM_BOT_TOKEN, offset)

    if not updates:
        print("새 메시지 없음")
        return

    print(f"📨 {len(updates)}개 메시지 처리 중...")

    for update in updates:
        update_id = update["update_id"]
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        # 봇 주인만 응답
        if chat_id != str(TELEGRAM_CHAT_ID):
            offset = update_id + 1
            continue

        if not text.startswith("/"):
            offset = update_id + 1
            continue

        parts = text.split()
        command = parts[0].split("@")[0].lower()  # /command@botname 처리
        args = parts[1:]

        print(f"  명령어: {command} {args}")

        try:
            reply = handle_command(command, args, kis)
            send_reply(TELEGRAM_BOT_TOKEN, chat_id, reply)
        except Exception as e:
            send_reply(TELEGRAM_BOT_TOKEN, chat_id, f"❌ 오류: {e}")

        offset = update_id + 1

    save_offset(offset)
    print("✅ 메시지 처리 완료")


if __name__ == "__main__":
    main()
