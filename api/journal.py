import os
import json
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Look for journal_db.json in parent or current dir
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(curr_dir, "..", "journal_db.json")
        if not os.path.exists(db_path):
            db_path = os.path.join(curr_dir, "journal_db.json")
        
        trades = []
        if os.path.exists(db_path):
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    trades = data.get("history", [])
            except Exception:
                trades = []

        # Analytics compute
        total_trades = len(trades)
        wins = [t for t in trades if t.get("pnl", 0) > 0.05]
        losses = [t for t in trades if t.get("pnl", 0) < -0.05]
        win_rate = round((len(wins) / total_trades * 100), 1) if total_trades > 0 else 0
        gross_profit = round(sum(t.get("pnl", 0) for t in wins), 2)
        gross_loss = round(abs(sum(t.get("pnl", 0) for t in losses)), 2)
        net_pnl = round(gross_profit - gross_loss, 2)
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0

        daily_matrix = {}
        for t in trades:
            d = t.get("date", "Unknown")
            if d not in daily_matrix:
                daily_matrix[d] = {"date": d, "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
            daily_matrix[d]["pnl"] = round(daily_matrix[d]["pnl"] + t.get("pnl", 0), 2)
            daily_matrix[d]["trades"] += 1
            if t.get("pnl", 0) > 0.05:
                daily_matrix[d]["wins"] += 1
            elif t.get("pnl", 0) < -0.05:
                daily_matrix[d]["losses"] += 1

        payload = {
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
        self.send_header("Cache-Control", "public, max-age=60")
        self.end_headers()
        self.wfile.write(body)
