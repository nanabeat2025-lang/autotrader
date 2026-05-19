"""기술적 지표 계산 (RSI, MACD, 볼린저밴드, 이동평균선, 거래량, 변동성)"""
import math
from typing import Optional


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val != "" else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0) -> int:
    try:
        return int(val) if val != "" else default
    except (ValueError, TypeError):
        return default


def calc_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def calc_ma(closes: list[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def _ema(data: list[float], period: int) -> list[float]:
    """지수이동평균"""
    if len(data) < period:
        return []
    k = 2 / (period + 1)
    ema_vals = [sum(data[:period]) / period]
    for price in data[period:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return ema_vals


def calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD: 추세 전환 감지"""
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None, "cross": None}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    diff = len(ema_fast) - len(ema_slow)
    macd_line = [f - s for f, s in zip(ema_fast[diff:], ema_slow)]
    signal_line = _ema(macd_line, signal)
    diff2 = len(macd_line) - len(signal_line)
    histogram = [m - s for m, s in zip(macd_line[diff2:], signal_line)]
    cross = None
    if len(histogram) >= 2:
        if histogram[-2] <= 0 and histogram[-1] > 0:
            cross = "GOLDEN"
        elif histogram[-2] >= 0 and histogram[-1] < 0:
            cross = "DEAD"
    return {
        "macd": round(macd_line[-1], 2) if macd_line else None,
        "signal": round(signal_line[-1], 2) if signal_line else None,
        "histogram": round(histogram[-1], 2) if histogram else None,
        "cross": cross,
    }


def calc_bollinger(closes: list[float], period: int = 20, num_std: float = 2.0) -> dict:
    """볼린저밴드: 변동성 기반 매매"""
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None, "position": None, "width": None}
    recent = closes[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = middle + num_std * std
    lower = middle - num_std * std
    band_width = upper - lower
    position = (closes[-1] - lower) / band_width if band_width > 0 else 0.5
    return {
        "upper": round(upper, 0),
        "middle": round(middle, 0),
        "lower": round(lower, 0),
        "width": round(band_width / middle * 100, 2) if middle else 0,
        "position": round(position, 3),
    }


def detect_volume_spike(volumes: list[int], threshold: float = 1.5) -> dict:
    """거래량 급증 감지 (20일 평균 대비 1.5배 이상)"""
    if len(volumes) < 21:
        return {"is_spike": False, "ratio": 0, "today_vol": 0, "avg_vol": 0}
    avg_20 = sum(volumes[-21:-1]) / 20
    today = volumes[-1]
    ratio = today / avg_20 if avg_20 > 0 else 0
    return {
        "is_spike": ratio >= threshold,
        "ratio": round(ratio, 2),
        "today_vol": today,
        "avg_vol": round(avg_20, 0),
    }


def detect_rsi_uturn(closes: list[float]) -> dict:
    """
    RSI U턴 감지 (반등 포착)
    - 어제 RSI가 과매도 구간(< 35)에 있었고
    - 오늘 RSI가 어제보다 올라간 경우 → 반등 시작
    """
    if len(closes) < 16:
        return {"is_uturn": False, "rsi_today": None, "rsi_yesterday": None}
    rsi_today     = calc_rsi(closes)
    rsi_yesterday = calc_rsi(closes[:-1])
    is_uturn = (
        rsi_today is not None and rsi_yesterday is not None
        and rsi_yesterday < 35 and rsi_today > rsi_yesterday
    )
    return {
        "is_uturn": is_uturn,
        "rsi_today": rsi_today,
        "rsi_yesterday": rsi_yesterday,
    }


def detect_bollinger_breakout(closes: list[float], period: int = 20) -> dict:
    """
    볼린저밴드 하단 이탈 후 복귀 감지 (반등 포착)
    - 어제 종가가 하단 밴드 아래
    - 오늘 종가가 하단 밴드 위로 복귀
    """
    if len(closes) < period + 1:
        return {"is_breakout": False}
    bb_today     = calc_bollinger(closes, period)
    bb_yesterday = calc_bollinger(closes[:-1], period)
    if bb_today.get("lower") is None or bb_yesterday.get("lower") is None:
        return {"is_breakout": False}
    is_breakout = (
        closes[-2] < bb_yesterday["lower"]
        and closes[-1] > bb_today["lower"]
    )
    return {
        "is_breakout": is_breakout,
        "lower_today": bb_today["lower"],
        "close_today": closes[-1],
        "close_yesterday": closes[-2],
    }


def calc_volatility(closes: list[float], period: int = 20) -> Optional[float]:
    """변동성 (연율화 %)"""
    if len(closes) < period + 1:
        return None
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(-period, 0)]
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / len(returns)
    daily_vol = math.sqrt(variance)
    return round(daily_vol * math.sqrt(252) * 100, 2)


def build_indicators(ohlcv_list: list[dict]) -> dict:
    """KIS API OHLCV -> 전체 기술적 지표"""
    ordered = list(reversed(ohlcv_list))
    closes = [_safe_float(d.get("stck_clpr", 0)) for d in ordered]
    vols = [_safe_int(d.get("acml_vol", 0)) for d in ordered]
    recent = [
        {
            "date": d.get("stck_bsop_date", ""),
            "open": _safe_float(d.get("stck_oprc", 0)),
            "high": _safe_float(d.get("stck_hgpr", 0)),
            "low": _safe_float(d.get("stck_lwpr", 0)),
            "close": _safe_float(d.get("stck_clpr", 0)),
            "volume": _safe_int(d.get("acml_vol", 0)),
        }
        for d in ordered[-20:]
    ]
    return {
        "rsi": calc_rsi(closes),
        "ma5": calc_ma(closes, 5) or 0,
        "ma20": calc_ma(closes, 20) or 0,
        "current_price": closes[-1] if closes else 0,
        "recent_ohlcv": recent,
        "avg_volume_5d": round(sum(vols[-5:]) / min(5, len(vols)), 0) if vols else 0,
        "macd": calc_macd(closes),
        "bollinger": calc_bollinger(closes),
        "volume_spike": detect_volume_spike(vols),
        "volatility": calc_volatility(closes),
        "rsi_uturn": detect_rsi_uturn(closes),
        "bb_breakout": detect_bollinger_breakout(closes),
    }


def summarize_investor(investor_data: list[dict]) -> dict:
    return {
        "foreign_net_buy": sum(_safe_int(d.get("frgn_ntby_qty", 0)) for d in investor_data[:5]),
        "institution_net_buy": sum(_safe_int(d.get("orgn_ntby_qty", 0)) for d in investor_data[:5]),
        "individual_net_buy": sum(_safe_int(d.get("prsn_ntby_qty", 0)) for d in investor_data[:5]),
    }
