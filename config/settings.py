"""
설정 파일 v2
- OpenAI → Google Gemini
- Discord → Telegram
- 공휴일 감지, 쿨다운, AI 정확도 추적 설정 추가
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── 한국투자증권 KIS OpenAPI ──────────────────────────────
KIS_APP_KEY    = os.getenv("KIS_APP_KEY",    "여기에_앱키_입력")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "여기에_앱시크릿_입력")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "50123456-01")
KIS_IS_MOCK    = os.getenv("KIS_IS_MOCK", "true").lower() == "true"

# ── OpenAI API ────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-여기에_오픈AI_키_입력")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # 가성비 최고

# ── Telegram 봇 ──────────────────────────────────────────
# BotFather에서 봇 생성 후 토큰 발급
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "여기에_텔레그램_봇토큰")
# 알림받을 채팅 ID (봇에게 /start 보낸 후 확인)
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "여기에_채팅ID")

# ── 감시 종목 (ETF 위주 추천) ────────────────────────────
# 종목코드: {"name": 종목명, "type": "ETF" or "STOCK"}
WATCHLIST = {
    "069500": {"name": "KODEX 200",          "type": "ETF"},
    "091160": {"name": "KODEX 반도체",        "type": "ETF"},
    "102780": {"name": "KODEX 삼성그룹",      "type": "ETF"},
    "005930": {"name": "삼성전자",            "type": "STOCK"},
    "000660": {"name": "SK하이닉스",          "type": "STOCK"},
}

# 거래량 TOP10 자동 편입 (블로그 기준: 꺼둠 - 변동성 리스크)
USE_VOLUME_TOP10 = False

# ── 매매 기준 ─────────────────────────────────────────────
MAX_BUDGET_PER_STOCK = int(os.getenv("MAX_BUDGET_PER_STOCK", "30000"))   # 3만원
BUY_CONFIDENCE_MIN   = int(os.getenv("BUY_CONFIDENCE_MIN",  "55"))
SELL_CONFIDENCE_MIN  = int(os.getenv("SELL_CONFIDENCE_MIN", "60"))
TAKE_PROFIT_RATE     = float(os.getenv("TAKE_PROFIT_RATE",  "0.015"))    # +1.5% 익절
STOP_LOSS_RATE       = float(os.getenv("STOP_LOSS_RATE",   "-0.10"))     # -10% 손절

# ── 리스크 관리 ────────────────────────────────────────────
MAX_HOLDINGS         = int(os.getenv("MAX_HOLDINGS", "5"))
TRAILING_STOP_RATE   = float(os.getenv("TRAILING_STOP_RATE", "0.05"))
SPLIT_BUY_COUNT      = int(os.getenv("SPLIT_BUY_COUNT", "1"))            # 1회 (전량 매수)
VOLATILITY_ADJUST    = os.getenv("VOLATILITY_ADJUST", "true").lower() == "true"

# 섹터 분류 (같은 섹터 최대 2종목까지)
MAX_PER_SECTOR       = int(os.getenv("MAX_PER_SECTOR", "2"))
STOCK_SECTORS = {
    "005930": "반도체", "000660": "반도체",
    "035420": "IT", "035720": "IT",
    "069500": "지수ETF", "091160": "반도체ETF", "102780": "그룹ETF",
}

# ── 쿨다운 (재매수 금지 기간) ────────────────────────────
COOLDOWN_DAYS = int(os.getenv("COOLDOWN_DAYS", "3"))

# ── 스케줄 (하루 3회) ─────────────────────────────────────
SCHEDULE_TIMES = ["09:30", "13:00", "15:00"]
