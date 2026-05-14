#!/bin/bash
# Google Cloud VM 초기 설정 스크립트
# 사용법: bash setup.sh

echo "=========================================="
echo " AI 자동매매 봇 서버 설정 시작"
echo "=========================================="

# 1. 시스템 업데이트
echo "📦 시스템 업데이트 중..."
sudo apt update && sudo apt upgrade -y

# 2. Python 설치
echo "🐍 Python 설치 중..."
sudo apt install -y python3 python3-pip python3-venv

# 3. 프로젝트 폴더 생성
echo "📁 프로젝트 설정 중..."
mkdir -p ~/autotrader
cd ~/autotrader

# 4. 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 5. 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt

# 6. systemd 서비스 등록 (자동 재시작)
echo "⚙️ 서비스 등록 중..."
sudo cp deploy/autotrader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable autotrader
sudo systemctl start autotrader

echo ""
echo "=========================================="
echo " ✅ 설정 완료!"
echo "=========================================="
echo ""
echo " 상태 확인:  sudo systemctl status autotrader"
echo " 로그 확인:  sudo journalctl -u autotrader -f"
echo " 재시작:     sudo systemctl restart autotrader"
echo " 중지:       sudo systemctl stop autotrader"
echo ""
