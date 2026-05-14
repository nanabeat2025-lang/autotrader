# ☁️ Google Cloud 서버 배포 가이드

컴퓨터가 꺼져도 24시간 자동 매매가 동작합니다.

---

## 💰 비용

- 무료 체험: **$300 크레딧 (3개월)**
- 체험 후: 월 약 **5,000~7,000원** (e2-micro 기준)
- e2-micro는 매월 무료 사용량이 있어서 실제론 더 저렴할 수 있음

---

## Step 1. Google Cloud 가입

1. https://cloud.google.com 접속
2. **"무료로 시작하기"** 클릭
3. 구글 계정으로 로그인
4. 결제 정보 입력 (무료 체험 동안 과금 안 됨)

---

## Step 2. VM 인스턴스 만들기

1. Google Cloud Console (https://console.cloud.google.com) 접속
2. 왼쪽 메뉴 → **Compute Engine** → **VM 인스턴스**
3. **"인스턴스 만들기"** 클릭

### 설정값:

| 항목 | 값 |
|------|-----|
| 이름 | `autotrader` |
| 리전 | `asia-northeast3 (서울)` |
| 머신 유형 | `e2-micro` (가장 저렴) |
| 부팅 디스크 | `Ubuntu 22.04 LTS` |
| 디스크 크기 | `10GB` (기본값 OK) |
| 방화벽 | HTTP, HTTPS 트래픽 허용 체크 |

4. **"만들기"** 클릭 → 1~2분 후 VM 생성 완료

---

## Step 3. VM에 접속하기

VM 인스턴스 목록에서 **"SSH"** 버튼 클릭 → 브라우저에서 터미널이 열림

---

## Step 4. 프로젝트 파일 업로드

### 방법 A: SSH 창에서 직접 업로드
1. SSH 창 오른쪽 상단 톱니바퀴 → **"파일 업로드"**
2. `autotrader_v2.zip` 선택

### 방법 B: 명령어로 (GitHub 사용 시)
```bash
git clone https://github.com/내계정/autotrader_v2.git ~/autotrader
```

---

## Step 5. 압축 풀기 + 설정

```bash
# 압축 풀기
cd ~
sudo apt install -y unzip
unzip autotrader_v2.zip
mv autotrader_v2 autotrader
cd autotrader

# .env 파일 만들기
cp .env.example .env
nano .env
```

`nano` 에디터에서 API 키들을 입력:
- 방향키로 이동
- 값 수정
- `Ctrl + O` → 엔터 (저장)
- `Ctrl + X` (나가기)

---

## Step 6. 설치 및 실행

```bash
# 시스템 업데이트 + Python 설치
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# 가상환경 만들기
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 테스트 (DRY-RUN)
python main.py --dry
```

정상 동작 확인되면 다음 단계로!

---

## Step 7. 서비스 등록 (자동 실행 + 자동 재시작)

```bash
# 서비스 파일 복사 (USER_NAME을 본인 계정으로 수정)
sudo cp deploy/autotrader.service /etc/systemd/system/

# 본인 계정 이름 확인
whoami
# 예: user_name 이 나오면 아래에서 USER_NAME을 이것으로 변경

# 서비스 파일 수정
sudo nano /etc/systemd/system/autotrader.service
# USER_NAME 부분을 본인 계정으로 변경 (3군데)
# Ctrl+O 저장, Ctrl+X 나가기

# 서비스 등록 + 시작
sudo systemctl daemon-reload
sudo systemctl enable autotrader    # 서버 재시작 시 자동 실행
sudo systemctl start autotrader     # 지금 바로 시작
```

---

## Step 8. 확인

```bash
# 상태 확인
sudo systemctl status autotrader

# 실시간 로그 보기
sudo journalctl -u autotrader -f

# 최근 로그 보기
sudo journalctl -u autotrader --since "1 hour ago"
```

`Active: active (running)` 이 나오면 성공! 🎉

---

## 자주 쓰는 명령어

| 명령어 | 기능 |
|--------|------|
| `sudo systemctl status autotrader` | 상태 확인 |
| `sudo systemctl restart autotrader` | 재시작 |
| `sudo systemctl stop autotrader` | 중지 |
| `sudo journalctl -u autotrader -f` | 실시간 로그 |
| `sudo journalctl -u autotrader --since today` | 오늘 로그 |

---

## ❗ 주의사항

- VM을 **중지(Stop)** 하면 봇도 멈춥니다 (비용은 안 나감)
- VM을 **삭제(Delete)** 하면 모든 데이터가 사라집니다
- 무료 체험 끝나면 자동 과금 → 결제 알림 설정 권장
- `.env` 파일에 API 키가 있으므로 VM 보안 주의

---

## 웹 대시보드도 같이 띄우기 (선택)

```bash
# 대시보드용 서비스 추가 생성
sudo nano /etc/systemd/system/autotrader-dashboard.service
```

내용:
```
[Unit]
Description=AI Trading Dashboard
After=network.target

[Service]
Type=simple
User=USER_NAME
WorkingDirectory=/home/USER_NAME/autotrader
ExecStart=/home/USER_NAME/autotrader/venv/bin/python dashboard/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable autotrader-dashboard
sudo systemctl start autotrader-dashboard
```

브라우저에서 `http://VM외부IP:5000` 으로 대시보드 접속 가능!
(방화벽에서 5000번 포트 열어야 함)
