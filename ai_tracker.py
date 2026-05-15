"""
AI 정확도 추적 모듈 (v2 신규)
매수 시 AI 예측 저장 → 매도 시 실제 결과와 비교 기록
대시보드에서 승률, 평균 수익률, 신뢰도별 성과 확인 가능
"""
import json
from pathlib import Path
from datetime import datetime

AI_TRACK_PATH = Path("data/ai_tracking.json")


def load_tracking() -> list[dict]:
    AI_TRACK_PATH.parent.mkdir(exist_ok=True)
    if AI_TRACK_PATH.exists():
        return json.loads(AI_TRACK_PATH.read_text(encoding="utf-8"))
    return []


def save_tracking(data: list[dict]):
    AI_TRACK_PATH.parent.mkdir(exist_ok=True)
    AI_TRACK_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_buy_prediction(ticker: str, name: str, ai_result: dict, buy_price: float):
    """매수 시: AI 예측 내용 저장"""
    records = load_tracking()
    records.append({
        "id":             f"{ticker}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "ticker":         ticker,
        "name":           name,
        "buy_date":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "buy_price":      buy_price,
        "ai_signal":      ai_result.get("signal"),
        "ai_confidence":  ai_result.get("confidence"),
        "ai_target":      ai_result.get("target_price"),
        "ai_stop_loss":   ai_result.get("stop_loss"),
        "ai_reason":      ai_result.get("reason"),
        # 매도 후 채워질 필드
        "sell_date":      None,
        "sell_price":     None,
        "actual_pnl_rate": None,
        "target_reached": None,
        "result":         "OPEN",  # OPEN / WIN / LOSS
    })
    save_tracking(records)


def record_sell_result(ticker: str, sell_price: float, buy_price: float):
    """매도 시: 실제 결과 업데이트"""
    records = load_tracking()
    pnl_rate = (sell_price - buy_price) / buy_price if buy_price else 0

    # 가장 최근 미결 레코드 업데이트
    for rec in reversed(records):
        if rec["ticker"] == ticker and rec["result"] == "OPEN":
            rec["sell_date"]      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rec["sell_price"]     = sell_price
            rec["actual_pnl_rate"] = round(pnl_rate, 4)
            rec["target_reached"] = (
                sell_price >= rec["ai_target"]
                if rec.get("ai_target") and rec["ai_target"] > 0 else False
            )
            rec["result"] = "WIN" if pnl_rate >= 0 else "LOSS"
            break

    save_tracking(records)


def get_stats() -> dict:
    """AI 정확도 통계 계산"""
    records = [r for r in load_tracking() if r["result"] != "OPEN"]
    if not records:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0, "target_hit_rate": 0, "by_confidence": {}}

    wins   = [r for r in records if r["result"] == "WIN"]
    pnls   = [r["actual_pnl_rate"] for r in records if r["actual_pnl_rate"] is not None]
    target = [r for r in records if r.get("target_reached")]

    # 신뢰도 구간별 성과
    by_conf = {}
    for bucket in ["50-59", "60-69", "70-79", "80+"]:
        lo = int(bucket.split("-")[0].replace("+", ""))
        hi = int(bucket.split("-")[1]) if "-" in bucket else 999
        subset = [r for r in records if lo <= (r.get("ai_confidence") or 0) <= hi]
        if subset:
            w = [x for x in subset if x["result"] == "WIN"]
            p = [x["actual_pnl_rate"] for x in subset if x["actual_pnl_rate"] is not None]
            by_conf[bucket] = {
                "count": len(subset),
                "win_rate": round(len(w) / len(subset) * 100, 1),
                "avg_pnl": round(sum(p) / len(p) * 100, 2) if p else 0,
            }

    return {
        "total":           len(records),
        "win_rate":        round(len(wins) / len(records) * 100, 1),
        "avg_pnl":         round(sum(pnls) / len(pnls) * 100, 2) if pnls else 0,
        "target_hit_rate": round(len(target) / len(records) * 100, 1),
        "by_confidence":   by_conf,
        "recent":          list(reversed(records))[:10],
    }
