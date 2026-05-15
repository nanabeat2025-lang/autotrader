"""
매매 실행 로직 v3
- 트레일링 스탑 (수익 보호)
- 변동성 기반 포지션 조절
- 최대 보유 종목수 제한
- 섹터 분산 투자
- 분할매수/분할매도
- 쿨다운 (익절 면제)
- AI 정확도 추적
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from core.ai_tracker import record_buy_prediction, record_sell_result

from config.settings import (
    BUY_CONFIDENCE_MIN, SELL_CONFIDENCE_MIN,
    TAKE_PROFIT_RATE, STOP_LOSS_RATE,
    MAX_BUDGET_PER_STOCK, COOLDOWN_DAYS,
    MAX_HOLDINGS, TRAILING_STOP_RATE, SPLIT_BUY_COUNT,
    VOLATILITY_ADJUST, MAX_PER_SECTOR, STOCK_SECTORS,
)

POSITION_PATH  = Path("data/positions.json")
TRADE_LOG_PATH = Path("data/trade_log.json")
COOLDOWN_PATH  = Path("data/cooldown.json")


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


# ── 쿨다운 ─────────────────────────────────────────────────
def is_in_cooldown(ticker: str) -> tuple:
    cooldown = load_cooldown()
    if ticker not in cooldown:
        return False, 0
    expire = datetime.fromisoformat(cooldown[ticker])
    if datetime.now() >= expire:
        del cooldown[ticker]
        save_cooldown(cooldown)
        return False, 0
    return True, (expire - datetime.now()).days + 1

def set_cooldown(ticker: str, days: int = COOLDOWN_DAYS):
    cooldown = load_cooldown()
    cooldown[ticker] = (datetime.now() + timedelta(days=days)).isoformat()
    save_cooldown(cooldown)

def clear_cooldown(ticker: str):
    cooldown = load_cooldown()
    if ticker in cooldown:
        del cooldown[ticker]
        save_cooldown(cooldown)

def get_all_cooldowns() -> dict:
    cooldown = load_cooldown()
    result = {}
    now = datetime.now()
    for ticker, expire_str in list(cooldown.items()):
        expire = datetime.fromisoformat(expire_str)
        if now < expire:
            result[ticker] = (expire - now).days + 1
    return result


# ── 리스크 관리 함수들 ──────────────────────────────────────
def calc_pnl_rate(buy_price: float, current_price: float) -> float:
    return (current_price - buy_price) / buy_price if buy_price else 0.0


def check_max_holdings() -> bool:
    """최대 보유 종목수 초과 여부"""
    positions = load_positions()
    return len(positions) >= MAX_HOLDINGS


def check_sector_limit(ticker: str) -> bool:
    """같은 섹터 종목수 초과 여부"""
    sector = STOCK_SECTORS.get(ticker, "기타")
    positions = load_positions()
    same_sector = sum(1 for t in positions if STOCK_SECTORS.get(t, "기타") == sector)
    return same_sector >= MAX_PER_SECTOR


def calc_position_size(current_price: float, volatility: float = None) -> int:
    """
    변동성 기반 포지션 크기 조절
    변동성 높으면 적게, 낮으면 많이 투자
    """
    budget = MAX_BUDGET_PER_STOCK

    if VOLATILITY_ADJUST and volatility and volatility > 0:
        # 기준: 변동성 30%를 1배로, 60%면 0.5배, 15%면 2배 (최대 2배)
        vol_factor = min(2.0, 30.0 / volatility)
        budget = int(budget * vol_factor)
        budget = max(budget, 5000)  # 최소 5천원

    qty = max(1, int(budget // current_price))
    return qty


def update_trailing_stop(pos: dict, current_price: float) -> dict:
    """
    트레일링 스탑 업데이트
    최고가 갱신 시 → 손절가도 올라감
    """
    highest = max(pos.get("highest_price", current_price), current_price)
    trailing_stop = highest * (1 - TRAILING_STOP_RATE)

    pos["highest_price"] = highest
    pos["trailing_stop"] = trailing_stop
    return pos


def calc_split_qty(total_qty: int, split_count: int = SPLIT_BUY_COUNT) -> int:
    """분할매수 1회 수량 계산"""
    return max(1, total_qty // split_count)


# ── 핵심 매매 판단 ──────────────────────────────────────────
def decide_and_execute(
    kis,
    ticker: str,
    name: str,
    current_price: float,
    ai_result: dict,
    indicators: dict = None,
    dry_run: bool = False,
) -> dict:
    positions  = load_positions()
    signal     = ai_result.get("signal", "HOLD")
    confidence = ai_result.get("confidence", 0)
    target_price = float(ai_result.get("target_price") or 0)
    ai_reason  = ai_result.get("reason", "")
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    volatility = indicators.get("volatility") if indicators else None

    # ── 보유 중: 매도 조건 ──────────────────────────────────
    if ticker in positions:
        pos       = positions[ticker]
        buy_price = float(pos["buy_price"])
        qty       = int(pos["qty"])
        pnl_rate  = calc_pnl_rate(buy_price, current_price)
        pnl_amt   = int((current_price - buy_price) * qty)

        # 트레일링 스탑 업데이트
        pos = update_trailing_stop(pos, current_price)
        positions[ticker] = pos
        save_positions(positions)

        sell_reason = None
        cooldown_apply = True
        sell_qty = qty  # 기본: 전량 매도

        # 1) 트레일링 스탑 히트
        trailing_stop = pos.get("trailing_stop", 0)
        if trailing_stop and current_price <= trailing_stop and pnl_rate > 0:
            sell_reason = f"트레일링 스탑 ({pnl_rate:.1%}, 최고가 대비 {TRAILING_STOP_RATE:.0%} 하락)"
            cooldown_apply = False

        # 2) 목표가 익절
        elif pnl_rate >= TAKE_PROFIT_RATE and target_price and current_price >= target_price:
            sell_reason = f"익절 ({pnl_rate:.1%}, 목표가 도달)"
            cooldown_apply = False

        # 3) 손절
        elif pnl_rate <= STOP_LOSS_RATE:
            sell_reason = f"손절 ({pnl_rate:.1%})"

        # 4) AI 매도 (분할매도: 50%씩)
        elif signal == "SELL" and confidence >= SELL_CONFIDENCE_MIN:
            sell_qty = calc_split_qty(qty)  # 분할매도
            sell_reason = f"AI 매도 (신뢰도 {confidence}%, {sell_qty}/{qty}주 분할매도) - {ai_reason}"

        if sell_reason:
            if not dry_run:
                kis.sell_market(ticker, sell_qty)
                if sell_qty >= qty:
                    if cooldown_apply:
                        set_cooldown(ticker)
                    del positions[ticker]
                else:
                    positions[ticker]["qty"] -= sell_qty
                save_positions(positions)

            record_sell_result(ticker, current_price, buy_price)
            record = {
                "time": now_str, "ticker": ticker, "name": name, "action": "SELL",
                "price": current_price, "qty": sell_qty, "buy_price": buy_price,
                "pnl_rate": f"{pnl_rate:.2%}", "pnl_amount": pnl_amt,
                "reason": sell_reason, "cooldown_applied": cooldown_apply,
            }
            log_trade(record)
            return {"action": "SELL", "reason": sell_reason, "qty": sell_qty,
                    "pnl_rate": pnl_rate, "pnl_amount": pnl_amt}

        return {"action": "HOLD", "reason": f"보유 관망 ({pnl_rate:.1%})", "qty": 0}

    # ── 미보유: 매수 조건 ───────────────────────────────────
    # 쿨다운 체크
    in_cd, cd_days = is_in_cooldown(ticker)
    if in_cd:
        return {"action": "HOLD", "reason": f"쿨다운 중 ({cd_days}일 남음)", "qty": 0}

    # 최대 보유 종목수 체크
    if check_max_holdings():
        return {"action": "HOLD", "reason": f"최대 보유 종목수({MAX_HOLDINGS}개) 도달", "qty": 0}

    # 섹터 분산 체크
    if check_sector_limit(ticker):
        sector = STOCK_SECTORS.get(ticker, "기타")
        return {"action": "HOLD", "reason": f"섹터 집중 방지 ({sector} 섹터 {MAX_PER_SECTOR}종목 보유 중)", "qty": 0}

    if signal == "BUY" and confidence >= BUY_CONFIDENCE_MIN:
        # 변동성 기반 포지션 크기 계산
        total_qty = calc_position_size(current_price, volatility)

        # 분할매수: 첫 회차 수량
        buy_qty = calc_split_qty(total_qty)
        reason = (
            f"AI 매수 (신뢰도 {confidence}%, {buy_qty}주 분할매수"
            f"{f', 변동성 {volatility:.0f}%' if volatility else ''}) - {ai_reason}"
        )

        if not dry_run:
            kis.buy_market(ticker, buy_qty)
            positions[ticker] = {
                "name": name, "qty": buy_qty, "buy_price": current_price,
                "target_price": target_price, "bought_at": now_str,
                "ai_prediction": ai_result,
                "total_planned_qty": total_qty,
                "buy_count": 1,
                "highest_price": current_price,
                "trailing_stop": current_price * (1 - TRAILING_STOP_RATE),
            }
            save_positions(positions)

        record_buy_prediction(ticker, name, ai_result, current_price)
        log_trade({
            "time": now_str, "ticker": ticker, "name": name, "action": "BUY",
            "price": current_price, "qty": buy_qty, "reason": reason,
        })
        return {"action": "BUY", "reason": reason, "qty": buy_qty}

    return {"action": "HOLD", "reason": f"신호 없음 (signal={signal}, conf={confidence}%)", "qty": 0}
