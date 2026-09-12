# TradeViz Pro — Institutional Trade Journal & Predictive Copilot (V8 Quant Engine)

An institutional-grade, zero-manual-input trade journal and real-time execution auditor built for MetaTrader 5 (MT5) algorithmic strategies, with full interactive analytics, heatmaps, and cloud deployment ready for **Vercel**.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)
![Deployment: Vercel](https://img.shields.io/badge/Deploy-Vercel-black.svg)
![MetaTrader: MT5](https://img.shields.io/badge/MetaTrader-MT5%20API-orange.svg)

---

## ⚡ Key Highlights

- **579 Verified Benchmark Trades**: Pre-loaded with comprehensive historical trade audits across Asian, London, and New York sessions.
- **In-Flight Predictive Copilot**: Real-time position tracking with dynamic Trailing Stop recommendations (Break-Even locks from +$0.50 to +$18.00), MAE/MFE analytics, and take-profit defense alerts.
- **Calendar Performance Matrix**: Daily P&L and win rate heatmap calendar with drill-down trade breakdown per session.
- **Edge Analytics & Leak Detector**: Setup win rates, flip-depth profit factors, session edge vs drawdowns, and loss distribution.
- **Risk Guardian Matrix**: Enforces maximum daily drawdowns, consecutive loss circuit breakers, and lot size ceilings.
- **Zero-Config Cloud Deployment**: Deploy seamlessly to **Vercel** with integrated serverless API routes or run locally connected directly to your Windows MT5 terminal.

---

## 🚀 Live Cloud Deployment (Vercel)

This repository is pre-configured with `vercel.json` and serverless Python API handlers in `/api`:

1. Go to [Vercel Dashboard](https://vercel.com/new).
2. Import your GitHub repository:
   ```
   https://github.com/solai-sakthi-dasan-23/Triannosauraus.git
   ```
3. Leave Build Command and Output Directory as default (`Root Directory: ./`).
4. Click **Deploy**.
5. Your interactive institutional journal will be live instantly!

---

## 💻 Running Locally with Live MetaTrader 5

For live real-time synchronization with your active desktop MT5 terminal:

### 1. Install Dependencies
```bash
pip install fastapi uvicorn websockets pydantic MetaTrader5
```

### 2. Start the Journal Hub Server
```bash
python journal_server.py
```

### 3. Open in Browser
Open `http://localhost:8000` to access the journal and live Copilot radar.

---

## 📁 Project Structure

```
├── api/                     # Vercel Serverless Functions
│   ├── journal.py           # REST /api/journal endpoint
│   ├── health.py            # /api/health probe
│   └── mt5_status.py        # /api/mt5/status cloud mock
├── css/
│   └── journal.css          # Institutional dark-mode design system
├── js/
│   └── journal.js           # Client application engine & zero-lag router
├── uploads/
│   └── trades/              # Trade execution screenshots and chart logs
├── index.html               # Main dashboard viewport
├── journal_db.json          # Historical journal ledger (579 trades)
├── journal_server.py        # Local FastAPI + WebSocket + MT5 Bridge backend
├── vercel.json              # Vercel routing & CORS configuration
└── README.md                # Project documentation
```

---

## 🛡️ License
Released under the MIT License. Developed for institutional prop-firm and quantitative traders.
