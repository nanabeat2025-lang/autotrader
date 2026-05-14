"""
매매 실행 로직 v2
- 쿨다운 개선: 익절은 쿨다운 없음, 손절/AI매도만 쿨다운
- AI 정확도 추적 연동
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from core.ai_tracker import record_buy_prediction, record_sell_result

POSITION_PATH  = Path("data/positions.json")
TRADE_LOG_PATH = Path("data/trade_log.json")
COOLDOWN_PATH  = Path("data/cooldown.json")

# .env 설정값 사용
from config.settings import (
    BUY_CONFIDENCE_MIN, SELL_CONFIDENCE_MIN,
    TAKE_PROFIT_RATE, STOP_LOSS_RATE,
    MAX_BUDGET_PER_STOCK, COOLDOWN_DAYS,
)


def _read_json(path: Path, default):
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _write_json(path: Path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_positions() -> dict:
    return _read_json(POSITION_PATH, {})


def save_positions(p: dict):
    _write_json(POSITION_PATH, p)


def load_cooldown() -> dict:
    return _read_json(COOLDOWN_PATH, {})


def save_cooldown(c: dict):
    _write_json(COOLDOWN_PATH, c)


def log_trade(record: dict):
    logs = _read_json(TRADE_LOG_PATH, [])
    logs.append(record)
    _write_json(TRADE_LOG_PATH, logs)


# ── 쿨다운 관리 ────────────────────────────────────────────
def is_in_cooldown(ticker: str) -> tuple[bool, int]:
    """쿨다운 중인지 확인. (True/False, 남은 일수)"""
    cooldown = load_cooldown()
    if ticker not in cooldown:
        return False, 0
    expire = datetime.fromisoformat(cooldown[ticker])
    remaining = (expire - datetime.now()).days + 1
    if datetime.now() >= expire:
        del cooldown[ticker]
        save_cooldown(cooldown)
        return False, 0
    return True, remaining


def set_cooldown(ticker: str, days: int = COOLDOWN_DAYS):
    """쿨다운 설정 (손절/AI매도 시 호출)"""
    cooldown = load_cooldown()
    cooldown[ticker] = (datetime.now() + timedelta(days=days)).isoformat()
    save_cooldown(cooldown)


def clear_cooldown(ticker: str):
    """쿨다운 수동 해제"""
    cooldown = load_cooldown()
    if ticker in cooldown:
        del cooldown[ticker]
        save_cooldown(cooldown)


def get_all_cooldowns() -> dict:
    """현재 쿨다운 목록과 남은 일수"""
    cooldown = load_cooldown()
    result = {}
    now = datetime.now()
    for ticker, expire_str in list(cooldown.items()):
        expire = datetime.fromisoformat(expire_str)
        if now >= expire:
            continue
        result[ticker] = (expire - now).days + 1
    return result


# ── 수익률 계산 ────────────────────────────────────────────
def calc_pnl_rate(buy_price: float, current_price: float) -> float:
    if buy_price == 0:
        return 0.0
    return (current_price - buy_price) / buy_price


# ── 핵심 매매 판단 ─────────────────────────────────────────
def decide_and_execute(
    kis,
    ticker: str,
    name: str,
    current_price: float,
    ai_result: dict,
    dry_run: bool = False,
) -> dict:
    positions  = load_positions()
    signal     = ai_result.get("signal", "HOLD")
    confidence = ai_result.get("confidence", 0)
    target_price = float(ai_result.get("target_price") or 0)
    ai_reason  = ai_result.get("reason", "")
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 보유 중: 매도 조건 ──────────────────────────────────
    if ticker in positions:
        pos      = positions[ticker]
        buy_price = float(pos["buy_price"])
        qty       = int(pos["qty"])
        pnl_rate  = calc_pnl_rate(buy_price, current_price)
        pnl_amt   = int((current_price - buy_price) * qty)

        sell_reason = None
        cooldown_apply = True   # 기본: 쿨다운 적용

        if pnl_rate >= TAKE_PROFIT_RATE and target_price and current_price >= target_price:
            sell_reason    = f"익절 ({pnl_rate:.1%}, 목표가 도달)"
            cooldown_apply = False  # ★ 익절 → 쿨다운 없음
        elif pnl_rate <= STOP_LOSS_RATE:
            sell_reason = f"손절 ({pnl_rate:.1%})"
        elif signal == "SELL" and confidence >= SELL_CONFIDENCE_MIN:
            sell_reason = f"AI 매도 신호 (신뢰도 {confidence}%) — {ai_reason}"

        if sell_reason:
            if not dry_run:
                kis.sell_market(ticker, qty)
                if cooldown_apply:
                    set_cooldown(ticker)
                del positions[ticker]
                save_positions(positions)

            record_sell_result(ticker, current_price, buy_price)
            record = {
                "time": now_str, "ticker": ticker, "name": name, "action": "SELL",
                "price": current_price, "qty": qty, "buy_price": buy_price,
                "pnl_rate": f"{pnl_rate:.2%}", "pnl_amount": pnl_amt,
                "reason": sell_reason, "cooldown_applied": cooldown_apply,
            }
            log_trade(record)
            return {"action": "SELL", "reason": sell_reason, "qty": qty,
                    "pnl_rate": pnl_rate, "pnl_amount": pnl_amt}

        return {"action": "HOLD", "reason": f"보유 관망 ({pnl_rate:.1%})", "qty": 0}

    # ── 미보유: 매수 조건 ───────────────────────────────────
    in_cd, cd_days = is_in_cooldown(ticker)
    if in_cd:
        return {"action": "HOLD", "reason": f"쿨다운 중 ({cd_days}일 남음)", "qty": 0}

    if signal == "BUY" and confidence >= BUY_CONFIDENCE_MIN:
        qty    = max(1, int(MAX_BUDGET_PER_STOCK // current_price))
        reason = f"AI 매수 신호 (신뢰도 {confidence}%) — {ai_reason}"

        if not dry_run:
            kis.buy_market(ticker, qty)
            positions[ticker] = {
                "name": name, "qty": qty, "buy_price": current_price,
                "target_price": target_price, "bought_at": now_str,
                "ai_prediction": ai_result,
            }
            save_positions(positions)

        record_buy_prediction(ticker, name, ai_result, current_price)
        log_trade({
            "time": now_str, "ticker": ticker, "name": name, "action": "BUY",
            "price": current_price, "qty": qty, "reason": reason,
        })
        return {"action": "BUY", "reason": reason, "qty": qty}

    return {"action": "HOLD", "reason": f"신호 없음 (signal={signal}, conf={confidence}%)", "qty": 0}
