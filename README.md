# 🤖 AI 자동주식매매 v2 (Gemini + 텔레그램)

블로그 "파무침" 2탄 기반 업그레이드 버전

---

## ✨ v2 변경사항

| 항목 | v1 | v2 |
|------|----|----|
| AI 엔진 | OpenAI GPT | **Google Gemini** |
| 알림/명령 | Discord | **텔레그램 봇** |
| 스케줄 | 하루 4회 | **하루 3회** (09:30 / 13:00 / 15:00) |
| 공휴일 처리 | ❌ 없음 | ✅ KIS API로 자동 감지 |
| 쿨다운 | 익절도 적용 | ✅ **익절은 쿨다운 없음** |
| 계좌 동기화 | ❌ 없음 | ✅ 수동매매 후 자동 동기화 |
| AI 정확도 추적 | ❌ 없음 | ✅ 승률 / 신뢰도별 성과 차트 |
| 거래량 TOP10 | 자동 편입 | ✅ 조회만 가능, 자동매매 제외 |
| AI 프롬프트 | 단기 트레이딩 | ✅ ETF/주식 분리, 4단계 분석 |

---

## 📁 프로젝트 구조

```
autotrader_v2/
├── main.py                  # 메인 실행 (스케줄러 + 텔레그램 봇)
├── requirements.txt
├── .env.example
├── config/settings.py       # API 키, 종목, 매매 설정
├── api/kis_api.py           # KIS OpenAPI (공휴일 감지, 계좌 동기화)
├── core/
│   ├── indicators.py        # RSI, 이동평균선
│   ├── ai_analyzer.py       # Gemini AI 분석 (ETF/주식 분리 프롬프트)
│   ├── trader.py            # 매매 실행 + 쿨다운 관리
│   └── ai_tracker.py        # AI 정확도 추적
├── bot/telegram_bot.py      # 텔레그램 봇 알림 + 명령어
├── dashboard/app.py         # Flask 웹 대시보드
└── data/                    # 자동 생성
    ├── positions.json
    ├── trade_log.json
    ├── cooldown.json
    └── ai_tracking.json
```

---

## ⚙️ 설치 및 설정

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정
```bash
cp .env.example .env
# .env 파일 열어서 아래 항목 입력
```

### 3. API 키 발급

**Google Gemini API:**
1. [Google AI Studio](https://aistudio.google.com/app/apikey) 접속
2. `Get API key` → API 키 생성
3. 무료 티어: 분당 15회, 일 1500회 (소규모 운용 충분)
4. 유료: gemini-2.5-flash 기준 매우 저렴

**텔레그램 봇:**
1. 텔레그램에서 `@BotFather` 검색 → `/newbot` 입력
2. 봇 이름, 사용자명 입력 → **토큰 발급** (`.env`의 `TELEGRAM_BOT_TOKEN`)
3. 내 봇에게 `/start` 메시지 전송
4. 브라우저에서 아래 URL 접속 → `id` 값이 채팅 ID:
   ```
   https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates
   ```

**한국투자증권 KIS OpenAPI:**
1. [KIS Developers](https://apiportal.koreainvestment.com) 접속
2. 모의투자 앱키/앱시크릿 발급 후 `.env` 입력

---

## 🚀 실행 방법

```bash
# DRY-RUN (실제 주문 없이 전체 흐름 테스트) ← 처음엔 여기서 시작!
python main.py --dry

# 즉시 1회 실행 (실제 주문)
python main.py --now

# 스케줄러 모드 (09:30 / 13:00 / 15:00 자동)
python main.py

# 텔레그램 봇만 실행 (명령어 응답만)
python main.py --bot

# 웹 대시보드
python dashboard/app.py   # → http://localhost:5000
```

---

## 📱 텔레그램 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `/report` | 현재 포트폴리오 현황 |
| `/잔고` | 예수금 조회 |
| `/거래량` | 거래량 TOP10 |
| `/쿨다운` | 재매수 금지 목록 + 남은 기간 |
| `/쿨다운해제 005930` | 특정 종목 쿨다운 즉시 해제 |
| `/매수 005930 5` | 삼성전자 5주 수동 매수 |
| `/매도 005930 5` | 삼성전자 5주 수동 매도 |
| `/동기화` | 증권 계좌 ↔ 포지션 파일 동기화 |
| `/ai성과` | AI 승률, 신뢰도별 성과 통계 |

---

## 📊 매매 기준

| 구분 | 조건 |
|------|------|
| **매수** | Gemini BUY + 신뢰도 ≥ 55% + 쿨다운 아님 |
| **익절** | 목표가 도달 + 수익률 ≥ +2% → **쿨다운 없음** |
| **손절** | 수익률 ≤ -10% → 쿨다운 3일 적용 |
| **AI 매도** | Gemini SELL + 신뢰도 ≥ 60% → 쿨다운 3일 적용 |

---

## 💡 종목 설정 (config/settings.py)

```python
WATCHLIST = {
    "069500": {"name": "KODEX 200",   "type": "ETF"},    # ETF 프롬프트 사용
    "005930": {"name": "삼성전자",    "type": "STOCK"},  # 주식 프롬프트 사용
}
```
- `type: ETF` → 보수적 중장기 관점 프롬프트
- `type: STOCK` → 기술적+수급 분석 프롬프트

---

## ⚠️ 주의사항

- **반드시 `--dry` 모드로 먼저 테스트하세요**
- `KIS_IS_MOCK=true` 상태에서 모의투자 충분히 검증 후 실전 전환
- AI 판단이 항상 맞지 않습니다. 소액으로 시작하세요
- 투자 손익의 책임은 본인에게 있습니다
