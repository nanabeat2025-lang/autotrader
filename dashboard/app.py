"""
Flask 웹 대시보드 v2
- AI 정확도 추적 패널 추가
- 신뢰도별 성과 차트
- 쿨다운 목록 표시
"""
from flask import Flask, jsonify, render_template_string
import json
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

POSITION_PATH  = Path("data/positions.json")
TRADE_LOG_PATH = Path("data/trade_log.json")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 자동매매 대시보드 v2</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}
  .header{background:#161b22;padding:16px 28px;border-bottom:1px solid #30363d;
          display:flex;align-items:center;gap:10px}
  .header h1{font-size:1.2rem;font-weight:700}
  .badge{background:#238636;color:#fff;padding:2px 10px;border-radius:20px;font-size:.72rem}
  .badge.mock{background:#9e6a03}
  .clock{margin-left:auto;font-size:.8rem;color:#8b949e}
  .wrap{max-width:1200px;margin:24px auto;padding:0 20px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px}
  .card .lbl{font-size:.75rem;color:#8b949e;margin-bottom:4px}
  .card .val{font-size:1.5rem;font-weight:700}
  .green{color:#3fb950} .red{color:#f85149} .yellow{color:#d29922}
  .sec{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:20px}
  .sec-title{font-size:.95rem;font-weight:600;margin-bottom:14px;color:#e6edf3}
  table{width:100%;border-collapse:collapse}
  th{background:#21262d;padding:9px 12px;text-align:left;font-size:.76rem;color:#8b949e;border-bottom:1px solid #30363d}
  td{padding:9px 12px;border-bottom:1px solid #21262d;font-size:.85rem}
  tr:hover td{background:#1c2128}
  .pill{padding:2px 9px;border-radius:20px;font-size:.72rem;font-weight:600}
  .buy{background:#1a4731;color:#3fb950}
  .sell{background:#3d1c1c;color:#f85149}
  .hold{background:#1c2128;color:#8b949e}
  .two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .chart-wrap{position:relative;height:220px}
  @media(max-width:640px){.two-col{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="header">
  <span>🤖</span>
  <h1>AI 자동매매 대시보드 v2</h1>
  <span class="badge" id="mode-badge">Gemini</span>
  <span class="clock" id="clock"></span>
</div>
<div class="wrap">

  <!-- 요약 카드 -->
  <div class="grid">
    <div class="card"><div class="lbl">보유 종목</div><div class="val" id="s-count">-</div></div>
    <div class="card"><div class="lbl">총 투자금</div><div class="val" id="s-invested">-</div></div>
    <div class="card"><div class="lbl">총 평가 손익</div><div class="val" id="s-pnl">-</div></div>
    <div class="card"><div class="lbl">AI 승률</div><div class="val" id="s-winrate">-</div></div>
    <div class="card"><div class="lbl">AI 평균 손익</div><div class="val" id="s-avgpnl">-</div></div>
    <div class="card"><div class="lbl">오늘 매매</div><div class="val" id="s-today">-</div></div>
  </div>

  <!-- 보유 종목 -->
  <div class="sec">
    <div class="sec-title">📈 보유 종목</div>
    <table>
      <thead><tr><th>종목</th><th>유형</th><th>매수가</th><th>현재가</th><th>수량</th><th>평가금액</th><th>수익률</th><th>매수일</th></tr></thead>
      <tbody id="pos-tbody"></tbody>
    </table>
  </div>

  <!-- AI 성과 + 쿨다운 -->
  <div class="two-col">
    <div class="sec">
      <div class="sec-title">🤖 신뢰도별 AI 성과</div>
      <div class="chart-wrap"><canvas id="conf-chart"></canvas></div>
    </div>
    <div class="sec">
      <div class="sec-title">⏳ 쿨다운 목록</div>
      <table>
        <thead><tr><th>종목코드</th><th>남은 기간</th></tr></thead>
        <tbody id="cd-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- 매매 이력 -->
  <div class="sec">
    <div class="sec-title">📋 최근 매매 이력</div>
    <table>
      <thead><tr><th>시간</th><th>종목</th><th>구분</th><th>가격</th><th>수량</th><th>손익</th><th>쿨다운</th><th>사유</th></tr></thead>
      <tbody id="trades-tbody"></tbody>
    </table>
  </div>

  <!-- AI 최근 예측 -->
  <div class="sec">
    <div class="sec-title">🔬 AI 최근 예측 결과</div>
    <table>
      <thead><tr><th>종목</th><th>신뢰도</th><th>목표가</th><th>실제 손익</th><th>목표 도달</th><th>결과</th><th>매수일</th></tr></thead>
      <tbody id="ai-tbody"></tbody>
    </table>
  </div>

</div>
<script>
function fmt(n){return Number(n).toLocaleString('ko-KR')}
let confChart=null;

async function loadAll(){
  const [pos,trades,ai,cd]=await Promise.all([
    fetch('/api/positions').then(r=>r.json()),
    fetch('/api/trades').then(r=>r.json()),
    fetch('/api/ai-stats').then(r=>r.json()),
    fetch('/api/cooldown').then(r=>r.json()),
  ]);

  // 요약 카드
  document.getElementById('s-count').textContent=pos.length+'개';
  const inv=pos.reduce((s,p)=>s+p.buy_price*p.qty,0);
  const pnl=pos.reduce((s,p)=>s+(p.current_price-p.buy_price)*p.qty,0);
  document.getElementById('s-invested').textContent=fmt(Math.round(inv))+'원';
  const pnlEl=document.getElementById('s-pnl');
  pnlEl.textContent=(pnl>=0?'+':'')+fmt(Math.round(pnl))+'원';
  pnlEl.className='val '+(pnl>=0?'green':'red');
  document.getElementById('s-winrate').textContent=ai.total?ai.win_rate+'%':'N/A';
  const avgEl=document.getElementById('s-avgpnl');
  avgEl.textContent=ai.total?(ai.avg_pnl>=0?'+':'')+ai.avg_pnl+'%':'N/A';
  if(ai.total) avgEl.className='val '+(ai.avg_pnl>=0?'green':'red');
  const today=new Date().toISOString().slice(0,10);
  document.getElementById('s-today').textContent=trades.filter(t=>t.time.startsWith(today)).length+'건';

  // 보유 종목
  const pt=document.getElementById('pos-tbody');
  pt.innerHTML=pos.length===0
    ?'<tr><td colspan="8" style="text-align:center;color:#8b949e">보유 종목 없음</td></tr>'
    :pos.map(p=>{
      const r=((p.current_price-p.buy_price)/p.buy_price*100).toFixed(2);
      const a=Math.round((p.current_price-p.buy_price)*p.qty);
      const ev=Math.round(p.current_price*p.qty);
      const cls=r>=0?'green':'red';
      return`<tr>
        <td><b>${p.name}</b><br><small style="color:#8b949e">${p.ticker}</small></td>
        <td><span class="pill ${p.stock_type==='ETF'?'hold':'buy'}">${p.stock_type||'STOCK'}</span></td>
        <td>${fmt(p.buy_price)}원</td><td>${fmt(p.current_price)}원</td>
        <td>${p.qty}주</td><td>${fmt(ev)}원</td>
        <td class="${cls}">${r>=0?'+':''}${r}%<br><small>(${a>=0?'+':''}${fmt(a)}원)</small></td>
        <td style="font-size:.76rem;color:#8b949e">${p.bought_at||'-'}</td>
      </tr>`;
    }).join('');

  // 신뢰도별 차트
  const bc=ai.by_confidence||{};
  const labels=Object.keys(bc);
  const wrs=labels.map(k=>bc[k].win_rate);
  const avgs=labels.map(k=>bc[k].avg_pnl);
  if(confChart) confChart.destroy();
  const ctx=document.getElementById('conf-chart').getContext('2d');
  confChart=new Chart(ctx,{
    type:'bar',
    data:{
      labels:labels.map(l=>l+'%'),
      datasets:[
        {label:'승률(%)',data:wrs,backgroundColor:'rgba(63,185,80,.7)',yAxisID:'y'},
        {label:'평균손익(%)',data:avgs,backgroundColor:'rgba(255,187,51,.7)',yAxisID:'y2'},
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{legend:{labels:{color:'#e6edf3',font:{size:11}}}},
      scales:{
        x:{ticks:{color:'#8b949e'},grid:{color:'#21262d'}},
        y:{ticks:{color:'#8b949e'},grid:{color:'#21262d'},title:{display:true,text:'승률(%)',color:'#8b949e'}},
        y2:{position:'right',ticks:{color:'#8b949e'},grid:{display:false},title:{display:true,text:'평균손익(%)',color:'#8b949e'}},
      }
    }
  });

  // 쿨다운
  const ct=document.getElementById('cd-tbody');
  const cdList=Object.entries(cd);
  ct.innerHTML=cdList.length===0
    ?'<tr><td colspan="2" style="text-align:center;color:#8b949e">없음</td></tr>'
    :cdList.map(([t,d])=>`<tr><td><code>${t}</code></td><td class="yellow">${d}일 남음</td></tr>`).join('');

  // 매매 이력
  const tt=document.getElementById('trades-tbody');
  tt.innerHTML=[...trades].reverse().slice(0,15).map(t=>{
    const pc=t.action==='BUY'?'buy':t.action==='SELL'?'sell':'hold';
    const pnl=t.pnl_amount!=null?`${t.pnl_amount>=0?'+':''}${fmt(t.pnl_amount)}원 (${t.pnl_rate||''})`:'-';
    const cls=t.pnl_amount>0?'green':t.pnl_amount<0?'red':'';
    const cd=t.action==='SELL'?(t.cooldown_applied?'⏳ 적용':'✅ 없음'):'-';
    return`<tr>
      <td style="font-size:.76rem">${t.time}</td>
      <td><b>${t.name}</b><br><small style="color:#8b949e">${t.ticker}</small></td>
      <td><span class="pill ${pc}">${t.action}</span></td>
      <td>${fmt(t.price)}원</td><td>${t.qty}주</td>
      <td class="${cls}">${pnl}</td><td>${cd}</td>
      <td style="font-size:.72rem;color:#8b949e;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.reason||''}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="8" style="text-align:center;color:#8b949e">이력 없음</td></tr>';

  // AI 예측 결과
  const at=document.getElementById('ai-tbody');
  const recent=ai.recent||[];
  at.innerHTML=recent.map(r=>{
    const res=r.result==='WIN'?'🟢 WIN':r.result==='LOSS'?'🔴 LOSS':'🔵 OPEN';
    const pnl=r.actual_pnl_rate!=null?`${(r.actual_pnl_rate*100).toFixed(2)}%`:'-';
    const pnlCls=r.actual_pnl_rate>0?'green':r.actual_pnl_rate<0?'red':'';
    return`<tr>
      <td><b>${r.name}</b><br><small style="color:#8b949e">${r.ticker}</small></td>
      <td>${r.ai_confidence}%</td>
      <td>${r.ai_target?fmt(r.ai_target)+'원':'-'}</td>
      <td class="${pnlCls}">${pnl}</td>
      <td>${r.target_reached===true?'✅':r.target_reached===false?'❌':'-'}</td>
      <td>${res}</td>
      <td style="font-size:.76rem;color:#8b949e">${r.buy_date||''}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" style="text-align:center;color:#8b949e">데이터 없음</td></tr>';
}

setInterval(()=>{document.getElementById('clock').textContent=new Date().toLocaleString('ko-KR')},1000);
loadAll();
setInterval(loadAll,30000);
</script>
</body>
</html>
"""


def _read(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/positions")
def api_positions():
    positions = _read(POSITION_PATH, {})
    result = []
    for ticker, pos in positions.items():
        result.append({
            "ticker":        ticker,
            "name":          pos.get("name", ticker),
            "stock_type":    pos.get("stock_type", pos.get("ai_prediction", {}).get("type", "STOCK")),
            "qty":           pos.get("qty", 0),
            "buy_price":     pos.get("buy_price", 0),
            "current_price": pos.get("buy_price", 0),  # 실 운영 시 KIS API 연결
            "target_price":  pos.get("target_price", 0),
            "bought_at":     pos.get("bought_at", ""),
        })
    return jsonify(result)


@app.route("/api/trades")
def api_trades():
    return jsonify(_read(TRADE_LOG_PATH, []))


@app.route("/api/ai-stats")
def api_ai_stats():
    from core.ai_tracker import get_stats
    return jsonify(get_stats())


@app.route("/api/cooldown")
def api_cooldown():
    from core.trader import get_all_cooldowns
    return jsonify(get_all_cooldowns())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
