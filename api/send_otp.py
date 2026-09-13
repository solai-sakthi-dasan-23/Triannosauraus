import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            payload = json.loads(post_data)
        except Exception:
            payload = {}

        email = payload.get("email", "").strip()
        code = payload.get("code", "").strip()
        name = payload.get("name", "Trader").strip()

        if not email or "@" not in email or not code:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Invalid email or OTP code"}).encode("utf-8"))
            return

        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", os.environ.get("GMAIL_USER", ""))
        smtp_pass = os.environ.get("SMTP_PASS", os.environ.get("GMAIL_PASS", ""))
        from_email = os.environ.get("SMTP_FROM", smtp_user or "security@triannosaraustraders.com")

        mail_sent = False
        mail_error = None

        if smtp_user and smtp_pass:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"Tri Rex Security Code: {code} - Verify Terminal Access"
                msg["From"] = f"Tri Rex Security <{from_email}>"
                msg["To"] = email

                text_content = f"Hello {name},\n\nYour institutional security verification code for Tri Rex Terminal is: {code}\n\nPlease enter this 6-digit confirmation code into the portal to complete your registration. This code expires in 10 minutes.\n\nTriannosaraus Traders - Born to Conquer"

                html_content = f"""<!DOCTYPE html>
<html>
<body style="background:#0b0f19; font-family:sans-serif; color:#f1f5f9; padding:20px;">
  <div style="background:#131b2e; max-width:500px; margin:0 auto; border:1px solid #ff5500; border-radius:12px; padding:32px;">
    <h2 style="color:#ff5500; margin:0 0 8px 0; letter-spacing:2px;">TRI <span style="color:#00e5ff;">REX</span> TERMINAL</h2>
    <p style="font-size:13px; color:#94a3b8; margin-top:0;">Institutional Access Verification</p>
    <p style="color:#cbd5e1; font-size:14px;">Hello <strong>{name}</strong>,</p>
    <p style="color:#94a3b8; font-size:13px; line-height:1.6;">Use the 6-digit one-time security code below to complete your registration:</p>
    <div style="background:rgba(0, 229, 255, 0.08); border:2px dashed #00e5ff; border-radius:8px; padding:18px; text-align:center; margin:24px 0;">
      <span style="font-size:32px; font-weight:800; letter-spacing:6px; color:#00e5ff; font-family:monospace;">{code}</span>
    </div>
    <p style="color:#94a3b8; font-size:12px;">This code expires in 10 minutes. Do not share this code with anyone.</p>
    <div style="margin-top:24px; padding-top:16px; border-top:1px solid #1e293b; font-size:11px; color:#64748b;">
      Triannosaraus Traders &bull; Born to Conquer
    </div>
  </div>
</body>
</html>"""

                part1 = MIMEText(text_content, "plain")
                part2 = MIMEText(html_content, "html")
                msg.attach(part1)
                msg.attach(part2)

                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [email], msg.as_string())
                server.quit()
                mail_sent = True
            except Exception as e:
                mail_error = str(e)

        response_payload = {
            "ok": True,
            "mail_sent": mail_sent,
            "email": email,
            "smtp_configured": bool(smtp_user and smtp_pass),
            "note": "Code dispatched via SMTP" if mail_sent else ("SMTP pending environment config" if not mail_error else f"Mail note: {mail_error}")
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(response_payload).encode("utf-8"))
