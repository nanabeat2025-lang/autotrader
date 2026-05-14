"""기술적 지표 계산 (RSI, 이동평균선)"""
from typing import Optional


def _safe_float(val, default=0.0) -> float:
    """KIS API가 빈 문자열을 반환하는 경우 대비"""
    try:
        return float(val) if val != "" else default
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=0) -> int:
    """KIS API가 빈 문자열을 반환하는 경우 대비"""
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


def build_indicators(ohlcv_list: list[dict]) -> dict:
    """KIS API OHLCV 리스트 → 기술적 지표 딕셔너리 (최신→과거 순서 가정)"""
    ordered = list(reversed(ohlcv_list))
    closes = [_safe_float(d.get("stck_clpr", 0)) for d in ordered]
    vols   = [_safe_int(d.get("acml_vol", 0))    for d in ordered]
    recent = [
        {
            "date":   d.get("stck_bsop_date", ""),
            "open":   _safe_float(d.get("stck_oprc", 0)),
            "high":   _safe_float(d.get("stck_hgpr", 0)),
            "low":    _safe_float(d.get("stck_lwpr", 0)),
            "close":  _safe_float(d.get("stck_clpr", 0)),
            "volume": _safe_int(d.get("acml_vol", 0)),
        }
        for d in ordered[-20:]
    ]
    return {
        "rsi":            calc_rsi(closes),
        "ma5":            calc_ma(closes, 5)  or 0,
        "ma20":           calc_ma(closes, 20) or 0,
        "current_price":  closes[-1] if closes else 0,
        "recent_ohlcv":   recent,
        "avg_volume_5d":  round(sum(vols[-5:]) / min(5, len(vols)), 0) if vols else 0,
    }


def summarize_investor(investor_data: list[dict]) -> dict:
    return {
        "foreign_net_buy":     sum(_safe_int(d.get("frgn_ntby_qty", 0)) for d in investor_data[:5]),
        "institution_net_buy": sum(_safe_int(d.get("orgn_ntby_qty",  0)) for d in investor_data[:5]),
        "individual_net_buy":  sum(_safe_int(d.get("prsn_ntby_qty",  0)) for d in investor_data[:5]),
    }
