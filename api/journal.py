import os
import json
import urllib.request
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = "https://izppbcqcfupluvujimdj.supabase.co"
SUPABASE_KEY = "sb_publishable_62HprtaLL2LIYbde4SzhgQ_SMcRODgB"

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        trades = []
        
        # 1. Fetch live from Supabase Database
        try:
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/trades?select=*&order=open_time.desc",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                }
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status == 200:
                    trades = json.loads(response.read().decode("utf-8"))
        except Exception as err:
            print("Supabase fetch failed, falling back to local file:", err)
            trades = []

        # 2. Local fallback if Supabase network times out
        if not trades:
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(curr_dir, "..", "journal_db.json")
            if not os.path.exists(db_path):
                db_path = os.path.join(curr_dir, "journal_db.json")
            if os.path.exists(db_path):
                try:
                    with open(db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        trades = data.get("history", [])
                except Exception:
                    trades = []

        # Analytics compute
        total_trades = len(trades)
        wins = [t for t in trades if float(t.get("pnl", 0)) > 0.05]
        losses = [t for t in trades if float(t.get("pnl", 0)) < -0.05]
        win_rate = round((len(wins) / total_trades * 100), 1) if total_trades > 0 else 0
        gross_profit = round(sum(float(t.get("pnl", 0)) for t in wins), 2)
        gross_loss = round(abs(sum(float(t.get("pnl", 0)) for t in losses)), 2)
        net_pnl = round(gross_profit - gross_loss, 2)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0

        daily_matrix = {}
        for t in trades:
            d = t.get("date", "Unknown")
            if d not in daily_matrix:
                daily_matrix[d] = {"date": d, "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
            daily_matrix[d]["pnl"] = round(daily_matrix[d]["pnl"] + float(t.get("pnl", 0)), 2)
            daily_matrix[d]["trades"] += 1
            if float(t.get("pnl", 0)) > 0.05:
                daily_matrix[d]["wins"] += 1
            elif float(t.get("pnl", 0)) < -0.05:
                daily_matrix[d]["losses"] += 1

        payload = {
            "source": "supabase",
            "kpis": {
                "total_trades": total_trades,
                "net_pnl": net_pnl,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "gross_profit": gross_profit,
                "gross_loss": gross_loss
            },
            "daily_matrix": list(daily_matrix.values()),
            "trades": trades
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=30")
        self.end_headers()
        self.wfile.write(body)
