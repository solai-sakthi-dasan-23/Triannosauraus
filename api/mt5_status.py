import json
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Cloud representation of MT5 Account
        account = {
            "login": 89974183,
            "server": "CPTMarkets-Live",
            "is_connected": True,
            "account_name": "Solai Sakthi Dasan",
            "company": "CPT Markets (Pty) Ltd",
            "balance": 4.51,
            "equity": 4.51,
            "leverage": 1000,
            "mode": "Cloud Audit & Historical Analysis"
        }
        body = json.dumps({"status": "connected", "account": account}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
