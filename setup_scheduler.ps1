# Windows 작업 스케줄러 자동 등록 스크립트
# 관리자 권한으로 실행 필요!
# 사용법: 이 파일을 우클릭 → "PowerShell에서 실행"

$scriptPath = "D:\1.개인E\주식\autotrader_v2\autotrader_v2\run_once.bat"
$taskNames = @("AutoTrader_0930", "AutoTrader_1300", "AutoTrader_1500")
$times = @("09:30", "13:00", "15:00")

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " AI 자동매매 스케줄러 등록" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

for ($i = 0; $i -lt 3; $i++) {
    $name = $taskNames[$i]
    $time = $times[$i]

    # 기존 작업 삭제 (있으면)
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue

    # 트리거: 매일 지정 시간 (월~금만)
    $trigger = New-ScheduledTaskTrigger -Daily -At $time

    # 실행할 프로그램
    $action = New-ScheduledTaskAction -Execute $scriptPath

    # 설정: 평일만 실행, 배터리 상관없이 실행
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    # 등록
    Register-ScheduledTask -TaskName $name -Trigger $trigger -Action $action -Settings $settings -Description "AI 자동매매 봇 ($time)" | Out-Null

    Write-Host "  ✅ $name 등록 완료 (매일 $time)" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 등록 완료! 매일 09:30 / 13:00 / 15:00" -ForegroundColor Cyan
Write-Host " 자동으로 매매 분석이 실행됩니다." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "확인: 작업 스케줄러(taskschd.msc)에서 확인 가능" -ForegroundColor Gray
Write-Host ""
pause
