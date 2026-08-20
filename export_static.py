# -*- coding: utf-8 -*-
"""
export_static.py — 生成固定静态网页「通杀一码.html」
=====================================================
读 cache/backtest.json, 输出一个完全自包含的单文件 HTML:
数据内嵌 JSON, 双击即开, 不依赖 Flask 服务, 可传到手机浏览。

用法:
  python export_static.py           # 默认读缓存生成
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_JSON = os.path.join(BASE_DIR, "cache", "backtest.json")
OUT_HTML = os.environ.get("OUT_HTML") or os.path.join(BASE_DIR, "通杀一码.html")

# 内置样式 (不再依赖 static/index.html)
CSS_TEXT = """
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{background:#f2f4f7;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1f2937;padding-bottom:40px}
.wrap{max-width:480px;margin:0 auto;padding:0 10px}
.topbar{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-bottom:1px solid #e5e7eb;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.topbar .t{font-size:17px;font-weight:700;letter-spacing:.5px}
.topbar .t b{color:#2563eb}
.topbar .sub{font-size:11px;color:#9ca3af;margin-top:2px}
.btns{display:flex;gap:6px;flex-shrink:0}
.btn{border:none;border-radius:8px;padding:7px 12px;font-size:13px;font-weight:600;cursor:pointer;color:#fff;background:#2563eb;transition:opacity .15s}
.btn:active{opacity:.75}
.btn.gray{background:#6b7280}
.btn.green{background:#059669}
.btn:disabled{opacity:.5}
.notice{display:none;background:#fef3c7;border:1px solid #f59e0b;color:#92400e;border-radius:8px;padding:9px 12px;font-size:12.5px;margin:10px 0;line-height:1.5}
.notice.show{display:block}
.card{background:#fff;border-radius:14px;box-shadow:0 1px 3px rgba(0,0,0,.06);padding:14px 14px;margin-top:10px}
.card h3{font-size:13px;color:#6b7280;font-weight:600;margin-bottom:8px;letter-spacing:.3px}
.balls{display:flex;align-items:center;justify-content:center;gap:12px;padding:4px 0}
.ball{width:52px;height:52px;border-radius:50%;background:linear-gradient(145deg,#fff,#eef2f7);border:2px solid #d1d5db;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;color:#111827;box-shadow:inset 0 2px 4px rgba(0,0,0,.06)}
.ball.r{background:linear-gradient(145deg,#ff6b6b,#dc2626);border-color:#b91c1c;color:#fff}
.ball.b{background:linear-gradient(145deg,#60a5fa,#2563eb);border-color:#1d4ed8;color:#fff}
.issue-tag{text-align:center;font-size:12px;color:#6b7280;margin-top:6px}
.kill-box{text-align:center;padding:6px 0 2px}
.kill-label{font-size:13px;color:#6b7280;letter-spacing:2px}
.kill-num{font-size:96px;font-weight:900;line-height:1.15;background:linear-gradient(180deg,#dc2626,#991b1b);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.kill-info{font-size:12.5px;color:#374151;margin-top:4px}
.kill-info .f{font-weight:700;color:#2563eb}
.kill-meta{font-size:11.5px;color:#9ca3af;margin-top:6px;line-height:1.6}
.stat-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center}
.stat{background:#f9fafb;border-radius:10px;padding:9px 4px}
.stat .v{font-size:19px;font-weight:800}
.stat .k{font-size:11px;color:#6b7280;margin-top:2px}
.stat.hl{background:#eff6ff}
.stat.hl .v{color:#2563eb}
.v.g{color:#059669}.v.r{color:#dc2626}
.compare{display:flex;justify-content:space-between;font-size:11.5px;color:#6b7280;margin-top:9px;padding:0 2px}
.bar{height:6px;border-radius:3px;background:#e5e7eb;margin-top:5px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:3px;background:#2563eb}
.bar i.green{background:#059669}
.tbl-scroll{max-height:52vh;overflow-y:auto;border-radius:10px;border:1px solid #eef0f3}
table{width:100%;border-collapse:collapse;font-size:12.5px}
thead th{position:sticky;top:0;background:#f3f4f6;color:#4b5563;font-weight:600;padding:8px 6px;text-align:center;border-bottom:1px solid #e5e7eb;z-index:2;white-space:nowrap}
tbody td{padding:7px 6px;text-align:center;border-bottom:1px solid #f3f4f6}
tbody tr:active{background:#f9fafb}
td.iss{color:#6b7280;font-family:ui-monospace,Consolas,monospace;font-size:11.5px}
td.num{font-weight:700;letter-spacing:1px}
td.kill{font-weight:800;font-size:15px}
td.kill.hit{color:#059669}
td.kill.miss{color:#dc2626}
td.res{font-size:15px}
td.fname{font-size:11px;color:#6b7280;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
td.frate{font-size:11px;color:#9ca3af}
td.t3{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#9ca3af}
td.t3 b{color:#dc2626;font-weight:800;font-size:13px}
.miss-row td{background:#fef2f2}
.lb-item{display:flex;align-items:center;gap:8px;padding:8px 4px;border-bottom:1px solid #f3f4f6;font-size:12.5px}
.lb-item:last-child{border-bottom:none}
.lb-rank{width:22px;height:22px;border-radius:50%;background:#f3f4f6;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#6b7280;flex-shrink:0}
.lb-rank.top3{background:#fef3c7;color:#b45309}
.lb-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lb-fam{font-size:10px;background:#eff6ff;color:#2563eb;border-radius:4px;padding:1px 5px;flex-shrink:0}
.lb-rate{font-weight:700;color:#2563eb;flex-shrink:0}
.lb-picked{font-size:10.5px;color:#9ca3af;flex-shrink:0}
details{border-top:1px solid #f3f4f6;margin-top:10px}
details summary{cursor:pointer;font-size:13px;font-weight:600;color:#374151;padding:10px 2px;list-style:none;display:flex;align-items:center;justify-content:space-between}
details summary::after{content:"▾";color:#9ca3af;font-size:12px}
details[open] summary::after{content:"▴"}
.paste-box{display:none;margin-top:10px}
.paste-box.show{display:block}
textarea{width:100%;height:70px;border:1px solid #d1d5db;border-radius:8px;padding:8px;font-size:12.5px;resize:vertical;font-family:ui-monospace,Consolas,monospace}
textarea:focus{outline:none;border-color:#2563eb}
.paste-row{display:flex;gap:8px;margin-top:8px}
.paste-row .btn{flex:1}
.footer{margin-top:16px;padding:12px;background:#fff;border-radius:12px;font-size:11px;color:#9ca3af;line-height:1.7}
.footer b{color:#6b7280}
.loading{text-align:center;padding:40px 0;color:#9ca3af;font-size:13px}
.spinner{width:28px;height:28px;border:3px solid #e5e7eb;border-top-color:#2563eb;border-radius:50%;margin:0 auto 10px;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
"""


def load_data():
    if not os.path.exists(CACHE_JSON):
        raise RuntimeError("未找到 cache/backtest.json, 请先运行 core.py 或启动服务计算一次")
    with open(CACHE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


BODY_TEMPLATE = """
  <div class="card">
    <div class="kill-box">
      <div class="kill-label" id="killLabel">下期通杀</div>
      <div class="kill-num" id="killNum">-</div>
      <div class="kill-info">公式: <span class="f" id="killFormula">-</span></div>
      <div class="kill-meta" id="killMeta"></div>
    </div>
  </div>

  <div class="card">
    <h3>🏆 最新开奖</h3>
    <div class="balls" id="balls"><div class="ball">-</div><div class="ball">-</div><div class="ball">-</div></div>
    <div class="issue-tag" id="lastIssue"></div>
  </div>

  <div class="card">
    <h3>📊 近200期回测汇总 <span style="color:#9ca3af;font-weight:400">(Hedge加权投票 walk-forward)</span></h3>
    <div class="stat-grid">
      <div class="stat hl"><div class="v" id="stRate">-</div><div class="k">回测命中率</div></div>
      <div class="stat"><div class="v" id="stHit">-</div><div class="k">命中/总数</div></div>
      <div class="stat"><div class="v" id="stHist">-</div><div class="k">Hedge千期</div></div>
      <div class="stat"><div class="v" id="stMaxWin">-</div><div class="k">最大连中</div></div>
      <div class="stat"><div class="v r" id="stMaxLose">-</div><div class="k">最大连错</div></div>
      <div class="stat"><div class="v g" id="stCur">-</div><div class="k">当前状态</div></div>
    </div>
    <div class="compare">
      <span>理论基线 72.9%</span>
      <span id="poolNote"></span>
    </div>
    <div class="bar"><i class="green" id="barBase" style="width:0%"></i></div>
  </div>

  <div class="card">
    <h3>📋 逐期真实预测记录 <span style="color:#9ca3af;font-weight:400">(近期在上 · 含Top3票码)</span></h3>
    <div class="tbl-scroll">
      <table>
        <thead><tr><th>期号</th><th>开奖</th><th>票码Top3</th><th>杀码</th><th>结果</th><th>首席专家</th></tr></thead>
        <tbody id="tbBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <details>
      <summary>🏅 算法榜单 Top50</summary>
      <div id="lbBody"><div class="loading" style="padding:16px">加载中...</div></div>
    </details>
  </div>

  <div class="footer">
    <b>说明</b><br>
    ① 通杀一码 = 杀掉一个数字，下期百/十/个三位都不出现即命中，理论随机基线 <b>72.9%</b>。<br>
    ② 公式池 <b id="fc">-</b> 个暴力穷举算法，主机制 <b>Hedge 加权投票</b>（学习自「杀和尾」项目）：每期取近90期命中率 Top12 公式为专家，按命中率加权投票，票王 = 通杀码。逐期真实回测（严格只用历史）。<br>
    ③ <b>重要对比</b>：Hedge 回测命中率为真实样本外成绩；「固定公式」高分是从数千公式挑最大值的<b>选择偏差假象</b>（该公式全史仅约74%）。200期二项波动 ±3.1pp，<b>不构成任何购彩建议</b>。<br>
    ④ <b>固定快照</b>：本页为数据快照（生成于 <span id="genTime">-</span>），数据更新后请重新导出。
  </div>
"""


def build_html(data, css):
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>福彩3D · 通杀一码 (固定快照)</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <div class="t">福彩3D · <b>通杀一码</b></div>
      <div class="sub" id="dataInfo">数据加载中...</div>
    </div>
  </div>
{BODY_TEMPLATE}
</div>
<script>
window.__DATA__ = {payload};
</script>
<script>
var DATA = window.__DATA__;
var $ = function(id){{ return document.getElementById(id); }};
function fmtPct(x){{ return (x*100).toFixed(1)+"%"; }}
function render(d){{
  DATA = d;
  var n = d.next, s = d.summary;
  $("dataInfo").textContent = "数据至 " + d.data_last_issue + " 期 · 共 " + d.data_count + " 期 · 公式池 " + d.formula_count + " (固定快照)";
  $("fc").textContent = d.formula_count;
  var num = d.rows[0].num;
  $("balls").innerHTML = '<div class="ball b">'+num[0]+'</div><div class="ball r">'+num[1]+'</div><div class="ball b">'+num[2]+'</div>';
  $("lastIssue").textContent = "第 " + d.data_last_issue + " 期开奖";
  $("killLabel").textContent = n.target_issue + " 期 通杀一码";
  $("killNum").textContent = n.kill;
  $("killFormula").textContent = n.formula_name + " (" + n.n_experts + "专家投票)";
  $("killMeta").innerHTML = "首席专家近90期命中率 <b>" + fmtPct(n.win_rate_200) + "</b> · 基线 72.9%<br>Top3票码: " + n.top3_vote.join(" / ") +
    "<br>参考: " + n.refs.map(function(r){{ return r.name + "→" + r.kill; }}).join(" · ");
  $("stRate").textContent = fmtPct(s.rate);
  $("stRate").style.color = s.rate >= s.baseline ? "#2563eb" : "#dc2626";
  $("stHit").textContent = s.hit + "/" + s.total;
  $("stHist").textContent = fmtPct(s.hedge1000);
  $("stMaxWin").textContent = s.max_win;
  $("stMaxLose").textContent = s.max_lose;
  if(s.cur_lose > 0){{ $("stCur").textContent = "连错"+s.cur_lose; $("stCur").style.color = "#dc2626"; }}
  else {{ $("stCur").textContent = "连中"+s.cur_win; $("stCur").style.color = "#059669"; }}
  $("poolNote").textContent = "Hedge千期 " + fmtPct(s.hedge1000) + " · 动态Top1 " + fmtPct(s.dyn_rate) + " · 固定公式(偏差) " + fmtPct(s.fixed_rate);
  $("barBase").style.width = Math.min(100, (s.baseline*100)) + "%";
  var html = "";
  d.rows.forEach(function(r){{
    var cls = r.hit ? "hit" : "miss";
    var t3 = (r.top3 || [r.kill]).map(function(c, i){{ return i === 0 ? '<b>' + c + '</b>' : c; }}).join("·");
    html += '<tr class="' + (r.hit ? "" : "miss-row") + '">' +
      '<td class="iss">' + r.issue + '</td>' +
      '<td class="num">' + r.num + '</td>' +
      '<td class="t3">' + t3 + '</td>' +
      '<td class="kill ' + cls + '">' + r.kill + '</td>' +
      '<td class="res">' + (r.hit ? "✅" : "❌") + '</td>' +
      '<td class="fname" title="' + r.fname + ' [' + r.fid + ']">' + r.fname + '</td></tr>';
  }});
  $("tbBody").innerHTML = html;
  var lb = "";
  d.leaderboard.forEach(function(f, i){{
    var rank = i < 3 ? '<div class="lb-rank top3">' + (i+1) + '</div>' : '<div class="lb-rank">' + (i+1) + '</div>';
    lb += '<div class="lb-item">' + rank +
      '<span class="lb-name">' + f.fname + '</span>' +
      '<span class="lb-fam">' + f.fam + '</span>' +
      '<span class="lb-rate">' + fmtPct(f.rate200) + '</span>' +
      '<span class="lb-picked">史' + fmtPct(f.hist) + '</span></div>';
  }});
  $("lbBody").innerHTML = lb || "无数据";
  $("genTime").textContent = d.generated_at;
}}
render(DATA);
</script>
</body>
</html>
"""


def main():
    data = load_data()
    css = CSS_TEXT
    html = build_html(data, css)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    s = data["summary"]
    n = data["next"]
    print(f"已生成固定网页: {OUT_HTML}")
    print(f"数据至 {data['data_last_issue']} 期 | 公式池 {data['formula_count']} 个")
    print(f"机制: {n['formula_name']} | 回测 {s['hit']}/{s['total']} = {s['rate']*100:.2f}%")
    print(f"下一期 {n['target_issue']} 杀 {n['kill']}")
    print("双击打开即可浏览, 或传到手机查看。")


if __name__ == "__main__":
    main()
