import http.server
import json
import logging
import os
import threading
from urllib.parse import urlparse

DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

masters = {}
lock = threading.Lock()

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard - Farm de Workers</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}
  h1{margin-bottom:24px;font-size:24px;color:#38bdf8}
  h1 small{font-size:14px;color:#64748b;font-weight:400}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:20px}
  .card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
  .card h2{font-size:18px;margin-bottom:12px;color:#94a3b8}
  .card h2 span{color:#38bdf8}
  .stat-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #0f172a;font-size:14px}
  .stat-row:last-child{border:0}
  .label{color:#94a3b8}
  .value{font-weight:600}
  .ok{color:#22c55e}
  .warn{color:#eab308}
  .danger{color:#ef4444}
  .badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;background:#334155;color:#e2e8f0}
  .badge-out{background:#3b82f6;color:#fff}
  .badge-in{background:#a855f7;color:#fff}
  .bar{height:8px;background:#334155;border-radius:999px;margin:4px 0 8px;overflow:hidden}
  .bar-fill{height:100%;border-radius:999px;transition:width .5s}
  .bar-ok{background:#22c55e}
  .bar-warn{background:#eab308}
  .bar-danger{background:#ef4444}
  .flex{display:flex;gap:6px;flex-wrap:wrap}
  .timestamp{text-align:center;margin-top:16px;color:#64748b;font-size:13px}
  .empty{text-align:center;padding:60px;color:#64748b}
  .empty p{font-size:18px;margin-bottom:8px}
  .legend{display:flex;gap:16px;justify-content:center;margin-bottom:20px;font-size:13px}
  .legend-item{display:flex;align-items:center;gap:4px}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
</style>
</head>
<body>
<h1>Dashboard <small>Farm de Workers Distribuída</small></h1>
<div id="masters" class="grid"></div>
<div class="timestamp" id="timestamp"></div>
<script>
async function fetchStatus(){try{const r=await fetch('/api/status');const data=await r.json();render(data)}catch(e){console.error(e)}}
function render(data){const c=document.getElementById('masters');const m=data.masters||{};const k=Object.keys(m);
if(!k.length){c.innerHTML='<div class="empty"><p>Aguardando reports dos masters...</p><span>Configure o supervisor com DASHBOARD_URL=http://localhost:5000</span></div>';document.getElementById('timestamp').textContent='';return}
let html='';
for(const[u,info]of Object.entries(m)){const p=info.performance||{};const f=p.farm_state||{};const w=f.workers||{};const t=f.tasks||{};const sys=p.system||{};const mem=sys.memory||{};const cfg=p.config_thresholds||{};const cpu=sys.cpu||{}
const loadPct=cfg.max_task?Math.round((t.tasks_pending/cfg.max_task)*100):0;const lc=loadPct>80?'danger':loadPct>50?'warn':'ok'
html+='<div class="card">';
html+='<h2>'+(info.hostname||u)+' <span>('+u+')</span></h2>'
html+='<div class="stat-row"><span class="label">Workers ativos</span><span class="value">'+(w.workers_alive||0)+' / '+(w.total_registered||0)+'</span></div>'
html+='<div class="stat-row"><span class="label">Emprestados <span style="color:#3b82f6">&#8594;</span></span><span class="value badge badge-out">'+(w.workers_borrowed||0)+'</span></div>'
html+='<div class="stat-row"><span class="label">Recebidos <span style="color:#a855f7">&#8592;</span></span><span class="value badge badge-in">'+(w.workers_received||0)+'</span></div>'
html+='<div class="stat-row"><span class="label">Idle</span><span class="value ok">'+(w.workers_idle||0)+'</span></div>'
html+='<div class="stat-row"><span class="label">Tasks pendentes</span><span class="value '+lc+'">'+(t.tasks_pending||0)+' / '+(cfg.max_task||'?')+'</span></div>'
if(loadPct>0)html+='<div class="bar"><div class="bar-fill bar-'+lc+'" style="width:'+Math.min(loadPct,100)+'%"></div></div>'
html+='<div class="stat-row"><span class="label">Running / Completed</span><span class="value">'+(t.tasks_running||0)+' / '+(t.tasks_completed||0)+'</span></div>'
html+='<div class="stat-row"><span class="label">Failed</span><span class="value danger">'+(t.tasks_failed||0)+'</span></div>'
if(w.borrowed_workers&&w.borrowed_workers.length){html+='<div class="stat-row"><span class="label">Movimentação</span><span class="value flex">'
for(const bw of w.borrowed_workers){const cls=bw.direction==='out'?'badge-out':'badge-in';const d=bw.direction==='out'?'\u2192':'\u2190'
html+='<span class="badge '+cls+'">'+d+' '+(bw.peer_uuid||'?')+'</span>'}
html+='</span></div>'}
html+='<div class="stat-row"><span class="label">CPU / RAM</span><span class="value">'+(cpu.usage_percent||0)+'% / '+(mem.percent_used||0)+'%</span></div>'
html+='<div class="stat-row" style="font-size:12px;color:#475569;border:0"><span>Ultimo report</span><span>'+(info.timestamp||'')+'</span></div>'
html+='</div>'}
c.innerHTML=html;document.getElementById('timestamp').textContent='Atualizado: '+new Date().toLocaleTimeString()}
setInterval(fetchStatus,3000);fetchStatus();
</script>
</body>
</html>"""


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with lock:
                data = {"masters": dict(masters), "count": len(masters)}
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/api/report", "/report"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                report = json.loads(body)
                uuid = report.get("server_uuid")
                if uuid:
                    with lock:
                        masters[uuid] = report
                    tasks = report.get("performance", {}).get("farm_state", {}).get("tasks", {})
                    logging.info(
                        "report from %s: pending=%s running=%s completed=%s",
                        uuid,
                        tasks.get("tasks_pending"),
                        tasks.get("tasks_running"),
                        tasks.get("tasks_completed"),
                    )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "invalid json"}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        logging.info("http: %s - %s", self.client_address[0], format % args)


def run_dashboard():
    server = http.server.HTTPServer((DASHBOARD_HOST, DASHBOARD_PORT), DashboardHandler)
    logging.info("dashboard em http://%s:%s", DASHBOARD_HOST, DASHBOARD_PORT)
    server.serve_forever()


if __name__ == "__main__":
    run_dashboard()