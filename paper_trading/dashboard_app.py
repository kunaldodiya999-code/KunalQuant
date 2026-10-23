"""Read-only local dashboard for the durable paper-trading SQLite journal.

Run with: python -m paper_trading.dashboard_app
Optional environment variables: KUNAL_QUANT_DB and KUNAL_DASHBOARD_PORT.
Binds to loopback only and exposes no broker-order actions.
"""
from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from config.settings import DATABASE_PATH

HOST = "127.0.0.1"
PORT = int(os.environ.get("KUNAL_DASHBOARD_PORT", "8780"))
DB_PATH = Path(os.environ.get("KUNAL_QUANT_DB", str(DATABASE_PATH))).expanduser()

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>Kunal Quant Paper Desk</title>
<style>
body{margin:0;background:#0b1020;color:#edf2ff;font:14px system-ui;padding:24px}
main{max-width:1300px;margin:auto}h1{margin:0}.flag{color:#55d6a0;border:1px solid #287b62;border-radius:20px;padding:8px;display:inline-block;margin:14px 0}
.note,.panel,.metric{background:#131b2e;border:1px solid #27334c;border-radius:12px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric small{color:#91a0bb}.metric strong{display:block;font-size:24px;margin-top:6px}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}.scroll{overflow:auto;max-height:420px}
table{width:100%;border-collapse:collapse;font-size:12px}td,th{text-align:left;padding:8px;border-bottom:1px solid #27334c;overflow-wrap:anywhere}th{color:#91a0bb}
.muted{color:#91a0bb}.good{color:#55d6a0}.bad{color:#ff7f8a}
@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.columns{grid-template-columns:1fr}body{padding:12px}}
</style></head><body><main>
<h1>Kunal Quant <span class="muted">/ Paper Desk</span></h1>
<div class="muted">Local journal monitor · refreshes every 30 seconds</div>
<div class="flag">PAPER MODE · NO LIVE ORDERS</div>
<div class="note" id="health">Reading SQLite journal…</div>
<div class="grid" id="metrics"></div>
<div class="columns"><section class="panel"><h3>Paper sessions</h3><div class="scroll" id="sessions"></div></section>
<section class="panel"><h3>Open positions</h3><div class="scroll" id="open"></div></section></div>
<section class="panel"><h3>Recent trade events</h3><div class="scroll" id="events"></div></section>
<section class="panel"><h3>Recent signals</h3><div class="scroll" id="signals"></div></section>
<p class="muted">Read-only SQLite view. Empty tables mean no persisted records yet; this page does not claim that market data is live. Database: <span id="db"></span></p>
</main><script>
const esc=v=>String(v??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money=v=>v==null?"—":new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:2}).format(Number(v));
const date=v=>{if(v==null)return "—";let n=Number(v);let d=new Date(n<1e12?n*1000:n);return isNaN(d)?"—":d.toLocaleString("en-IN",{hour12:false})};
const table=(heads,rows)=>rows.length?"<table><thead><tr>"+heads.map(x=>"<th>"+esc(x)+"</th>").join("")+"</tr></thead><tbody>"+rows.map(r=>"<tr>"+r.map(x=>"<td>"+x+"</td>").join("")+"</tr>").join("")+"</tbody></table>":"<p class='muted'>No records yet.</p>";
async function load(){try{let response=await fetch("/api/summary",{cache:"no-store"});let d=await response.json();if(!response.ok)throw Error(d.error||"Database read failed");
document.getElementById("db").textContent=d.database;
document.getElementById("health").textContent=d.database_exists?"SQLite readable · refreshed "+new Date().toLocaleTimeString():"Database not found. Start a paper session or set KUNAL_QUANT_DB.";
let m=[["Sessions",d.metrics.sessions],["Signals recorded",d.metrics.signals],["Trades recorded",d.metrics.trades],["Realized gross P&L",money(d.metrics.realized_gross_pnl)]];
document.getElementById("metrics").innerHTML=m.map(x=>"<div class='metric'><small>"+esc(x[0])+"</small><strong>"+esc(x[1])+"</strong></div>").join("");
document.getElementById("sessions").innerHTML=table(["Session","Status","Started","Capital","Underlying"],d.sessions.map(s=>[esc(s.session_id),esc(s.status),esc(s.started_at),money(s.starting_capital),esc(s.underlying)]));
document.getElementById("open").innerHTML=table(["Symbol","Side","Entry","Qty left","Stop","Target","Gross P&L"],d.open_trades.map(t=>[esc(t.symbol),esc(t.direction),money(t.entry_price),esc(t.remaining_quantity),money(t.stop_loss),money(t.target),money(t.gross_pnl)]));
document.getElementById("events").innerHTML=table(["Time","Event","Symbol","Price","Qty","P&L","Reason"],d.events.map(e=>[esc(date(e.event_timestamp)),esc(e.event_type),esc(e.symbol),money(e.price),esc(e.quantity),money(e.pnl),esc(e.reason)]));
document.getElementById("signals").innerHTML=table(["Time","Symbol","Strategy","Direction","Status","Reason"],d.signals.map(s=>[esc(date(s.signal_timestamp)),esc(s.symbol),esc(s.strategy_id),esc(s.direction),esc(s.status),esc(s.rejection_reason||s.reason)]));
}catch(e){document.getElementById("health").textContent="Dashboard error: "+e.message;}}
load();setInterval(load,30000);
</script></body></html>"""


def _connect_readonly() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _rows(connection: sqlite3.Connection, sql: str) -> list[dict]:
    return [dict(row) for row in connection.execute(sql).fetchall()]


def read_summary() -> dict:
    result = {"database": str(DB_PATH.resolve()), "database_exists": DB_PATH.is_file(),
              "metrics": {"sessions": 0, "signals": 0, "trades": 0, "realized_gross_pnl": 0.0},
              "sessions": [], "open_trades": [], "events": [], "signals": []}
    if not DB_PATH.is_file():
        return result
    with _connect_readonly() as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"paper_sessions", "paper_signals", "paper_trades", "paper_trade_events"}
        if not required.issubset(tables):
            result["error"] = "Paper journal tables are not present; initialize the schema first."
            return result
        result["metrics"] = {
            "sessions": con.execute("SELECT COUNT(*) FROM paper_sessions").fetchone()[0],
            "signals": con.execute("SELECT COUNT(*) FROM paper_signals").fetchone()[0],
            "trades": con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0],
            "realized_gross_pnl": con.execute("SELECT COALESCE(SUM(gross_pnl),0) FROM paper_trades WHERE status='CLOSED'").fetchone()[0]}
        sessions = _rows(con, "SELECT session_id,status,started_at,starting_capital,metadata_json FROM paper_sessions ORDER BY started_at DESC LIMIT 30")
        for row in sessions:
            try:
                metadata = json.loads(row.pop("metadata_json") or "{}")
            except (ValueError, TypeError):
                metadata = {}
            row["underlying"] = metadata.get("underlying_symbol") or metadata.get("underlying_key") or "—"
        result["sessions"] = sessions
        result["open_trades"] = _rows(con, "SELECT symbol,direction,entry_price,remaining_quantity,stop_loss,target,gross_pnl FROM paper_trades WHERE status='OPEN' ORDER BY entry_timestamp DESC LIMIT 100")
        result["events"] = _rows(con, "SELECT e.event_timestamp,e.event_type,t.symbol,e.price,e.quantity,e.pnl,e.reason FROM paper_trade_events e JOIN paper_trades t ON t.trade_id=e.trade_id ORDER BY e.event_timestamp DESC,e.id DESC LIMIT 100")
        result["signals"] = _rows(con, "SELECT signal_timestamp,symbol,strategy_id,direction,status,rejection_reason,reason FROM paper_signals ORDER BY signal_timestamp DESC,id DESC LIMIT 100")
    return result


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_body(200, "text/html; charset=utf-8", PAGE.encode())
        elif path == "/api/summary":
            try:
                body = json.dumps(read_summary(), default=str).encode()
                self.send_body(200, "application/json; charset=utf-8", body)
            except (sqlite3.Error, OSError, ValueError) as exc:
                self.send_body(500, "application/json; charset=utf-8", json.dumps({"error": str(exc)}).encode())
        else:
            self.send_body(404, "text/plain; charset=utf-8", b"Not found")

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Kunal Quant Paper Desk: http://{HOST}:{PORT}")
    print(f"Read-only SQLite journal: {DB_PATH.resolve()}")
    print("Paper mode only; no broker order endpoints.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
