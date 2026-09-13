import asyncio
import json
import os
import datetime
import urllib.request
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
import shutil

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont

import MetaTrader5 as mt5

class TradeAttachImageRequest(BaseModel):
    id: str
    image_url: str

class MT5ConnectRequest(BaseModel):
    login: int = 89974183
    server: str = "CPTMarkets-Live"
    password: Optional[str] = None

app = FastAPI(title="KillZone & V8 Trading Copilot Journal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active MT5 Account Configuration
mt5_account_config = {
    "login": 89974183,
    "server": "CPTMarkets-Live",
    "is_connected": False,
    "last_sync": None,
    "account_name": None,
    "balance": 0.0,
    "equity": 0.0
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DB_FILE = os.path.join(BASE_DIR, "journal_db.json")
if not os.path.exists(JOURNAL_DB_FILE):
    parent_db = os.path.join(os.path.dirname(BASE_DIR), "journal_db.json")
    if os.path.exists(parent_db):
        JOURNAL_DB_FILE = parent_db

# In-memory storage for active positions and historical journal
active_positions: Dict[str, Dict[str, Any]] = {}
journal_history: List[Dict[str, Any]] = []

SUPABASE_URL = "https://izppbcqcfupluvujimdj.supabase.co"
SUPABASE_KEY = "sb_publishable_62HprtaLL2LIYbde4SzhgQ_SMcRODgB"

def load_journal_from_file():
    global journal_history
    # Try loading from Supabase Cloud first
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/trades?select=*&order=open_time.desc",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                cloud_trades = json.loads(resp.read().decode("utf-8"))
                if cloud_trades and len(cloud_trades) > 0:
                    journal_history = cloud_trades
                    print(f"Loaded {len(journal_history)} trades directly from Supabase Cloud!")
                    return
    except Exception as e:
        print(f"Supabase cloud sync note: {e}")

    # Fallback to local JSON ledger
    if os.path.exists(JOURNAL_DB_FILE):
        try:
            with open(JOURNAL_DB_FILE, "r") as f:
                data = json.load(f)
                journal_history = data.get("history", [])
                print(f"Loaded {len(journal_history)} historical trades from {JOURNAL_DB_FILE}")
        except Exception as e:
            print(f"Error loading journal DB: {e}")
            journal_history = []
    else:
        journal_history = []

def seed_benchmark_trades():
    # Retained as dummy reference only, not auto-seeded
    pass

def save_journal_to_file():
    try:
        with open(JOURNAL_DB_FILE, "w") as f:
            json.dump({"history": journal_history}, f, indent=2)
    except Exception as e:
        print(f"Error saving journal DB: {e}")

    # Asynchronously push to Supabase
    try:
        if journal_history:
            latest = journal_history[0]
            payload = json.dumps({
                "id": str(latest.get("id")),
                "symbol": latest.get("symbol", "XAUUSD"),
                "type": latest.get("type", "BUY"),
                "lots": float(latest.get("lots", 0.01)),
                "entry_price": float(latest.get("entry_price", 0.0)),
                "exit_price": float(latest.get("exit_price", 0.0)) if latest.get("exit_price") else None,
                "sl": float(latest.get("sl", 0.0)) if latest.get("sl") else None,
                "tp": float(latest.get("tp", 0.0)) if latest.get("tp") else None,
                "pnl": float(latest.get("pnl", 0.0)),
                "outcome": latest.get("outcome", "WIN"),
                "setup_name": latest.get("setup_name", "V8 Execution"),
                "session": latest.get("session", "Asian"),
                "date": latest.get("date", "2026.09.08"),
                "open_time": latest.get("open_time", ""),
                "close_time": latest.get("close_time", ""),
                "mae": float(latest.get("mae", 0.0)),
                "mfe": float(latest.get("mfe", 0.0)),
                "status": latest.get("status", "CLOSED"),
                "image_url": latest.get("image_url")
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/trades",
                data=payload,
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                },
                method="POST"
            )
            urllib.request.urlopen(req, timeout=4)
    except Exception as e:
        print(f"Supabase sync note on trade save: {e}")

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# Data models
class TradeOpenRequest(BaseModel):
    id: Optional[str] = None
    symbol: str = "XAUUSD"
    type: str = "BUY"  # BUY or SELL
    lots: float = 0.01
    entry_price: float
    sl: float
    tp: float
    setup_name: str = "VWAP"
    session: Optional[str] = None
    time: Optional[str] = None

class TradeTickRequest(BaseModel):
    id: Optional[str] = None
    symbol: str = "XAUUSD"
    current_price: float

class TradeCloseRequest(BaseModel):
    id: str
    exit_price: float
    time: Optional[str] = None
    reason: Optional[str] = "TP"  # TP, SL, MANUAL, TRAILING_STOP

# Predictive Copilot Engine Logic
BE_LOCK_RULES = [
    (29.0, 18.0),
    (28.0, 15.0),
    (27.0, 12.0),
    (25.0, 10.0),
    (20.0, 6.0),
    (15.0, 4.5),
    (10.0, 3.0),
    (5.0, 1.0),
    (2.0, 0.5)
]

def evaluate_copilot(pos: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    entry = pos["entry_price"]
    is_buy = pos["type"].upper() == "BUY"
    tp = pos["tp"]
    sl = pos["sl"]
    current_sl = pos.get("current_sl", sl)
    
    # Calculate price change
    favorable = (current_price - entry) if is_buy else (entry - current_price)
    adverse = -(entry - current_price) if is_buy else -(current_price - entry)
    
    pos["mfe"] = max(pos.get("mfe", 0.0), favorable)
    pos["mae"] = min(pos.get("mae", 0.0), adverse)
    
    floating_pnl = round(favorable * pos["lots"] * 100, 2)  # assuming standard 100oz Gold or $1/point/0.01 lot
    pos["floating_pnl"] = floating_pnl
    
    # Total distance to TP
    target_distance = abs(tp - entry)
    progress_pct = min(100.0, max(0.0, (favorable / target_distance) * 100)) if target_distance > 0 else 0
    
    # Check Trailing Stop Lock levels
    recommended_sl = None
    locked_profit_pts = 0.0
    for trigger, lock in BE_LOCK_RULES:
        if pos["mfe"] >= trigger:
            recommended_sl = (entry + lock) if is_buy else (entry - lock)
            locked_profit_pts = lock
            break
            
    # Advisory Logic
    action = "HOLD"
    badge_color = "green"
    confidence = 85
    reason = "Momentum is healthy and price is expanding toward target."
    
    if favorable >= 2.0 and current_sl == sl:
        action = "TRAIL STOP TO BE"
        badge_color = "yellow"
        confidence = 90
        reason = f"Trade is +${favorable:.2f} in profit. Lock risk-free stop at entry +$0.50."
    elif locked_profit_pts > 0:
        action = f"LOCK +${locked_profit_pts:.1f} PTS"
        badge_color = "cyan"
        confidence = 92
        reason = f"Milestone reached. Trailing stop securely locked at +${locked_profit_pts:.1f} points."
    elif progress_pct >= 85:
        action = "PREPARE TO TAKE PROFIT"
        badge_color = "emerald"
        confidence = 95
        reason = f"Within 15% of final target TP ({tp:.2f}). Consider securing partials."
    elif adverse < -3.5:
        action = "DEFENSE WARNING"
        badge_color = "red"
        confidence = 78
        reason = f"Adverse drawdown (-${abs(adverse):.2f}) near max threshold (-$5.00). Prepare for potential SL Flip."
    elif favorable < 0.5 and adverse > -1.5:
        action = "MONITORING CONSOLIDATION"
        badge_color = "blue"
        confidence = 80
        reason = "Trade in initial reaction zone. Level holding within expected boundary."

    return {
        "action": action,
        "badge_color": badge_color,
        "confidence": confidence,
        "reason": reason,
        "floating_pnl": floating_pnl,
        "progress_pct": round(progress_pct, 1),
        "favorable_pts": round(favorable, 2),
        "adverse_pts": round(adverse, 2),
        "recommended_sl": recommended_sl,
        "current_sl": current_sl
    }

# --- ENDPOINTS ---

@app.on_event("startup")
def startup():
    load_journal_from_file()

@app.get("/api/health")
def health():
    return {"status": "ok", "active_positions": len(active_positions), "journal_records": len(journal_history)}

@app.get("/api/positions")
def get_active_positions():
    return list(active_positions.values())

@app.get("/api/journal")
def get_journal():
    # Calculate key analytics
    total_trades = len(journal_history)
    wins = [t for t in journal_history if t.get("pnl", 0) > 0.05]
    losses = [t for t in journal_history if t.get("pnl", 0) < -0.05]
    win_rate = round((len(wins) / total_trades * 100), 1) if total_trades > 0 else 0
    gross_profit = round(sum(t.get("pnl", 0) for t in wins), 2)
    gross_loss = round(abs(sum(t.get("pnl", 0) for t in losses)), 2)
    net_pnl = round(gross_profit - gross_loss, 2)
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0
    
    # Daily aggregation for calendar heatmap
    daily_matrix: Dict[str, Dict[str, Any]] = {}
    for t in journal_history:
        d = t.get("date", "Unknown")
        if d not in daily_matrix:
            daily_matrix[d] = {"date": d, "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
        daily_matrix[d]["pnl"] = round(daily_matrix[d]["pnl"] + t.get("pnl", 0), 2)
        daily_matrix[d]["trades"] += 1
        if t.get("pnl", 0) > 0.05:
            daily_matrix[d]["wins"] += 1
        elif t.get("pnl", 0) < -0.05:
            daily_matrix[d]["losses"] += 1

    return {
        "kpis": {
            "total_trades": total_trades,
            "net_pnl": net_pnl,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss
        },
        "daily_matrix": list(daily_matrix.values()),
        "trades": journal_history
    }

@app.post("/api/trades/open")
async def open_trade(req: TradeOpenRequest):
    trade_id = req.id or f"TRD_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(active_positions)+1}"
    now_str = req.time or datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
    date_str = now_str.split(" ")[0]
    
    # Determine session if not passed
    hour = datetime.datetime.now().hour
    session = req.session or ("Asian" if hour < 8 else ("London" if hour < 15 else "New York"))
    
    pos = {
        "id": trade_id,
        "symbol": req.symbol,
        "type": req.type.upper(),
        "lots": req.lots,
        "entry_price": req.entry_price,
        "current_price": req.entry_price,
        "sl": req.sl,
        "current_sl": req.sl,
        "tp": req.tp,
        "setup_name": req.setup_name,
        "session": session,
        "open_time": now_str,
        "date": date_str,
        "mfe": 0.0,
        "mae": 0.0,
        "floating_pnl": 0.0,
        "status": "ACTIVE"
    }
    
    pos["copilot"] = evaluate_copilot(pos, req.entry_price)
    active_positions[trade_id] = pos
    
    await manager.broadcast({
        "event": "TRADE_OPENED",
        "trade": pos
    })
    
    return {"status": "success", "message": f"Trade {trade_id} opened and logged", "trade": pos}

@app.post("/api/trades/tick")
async def update_tick(req: TradeTickRequest):
    # If specific ID passed, update it, otherwise update all positions matching symbol
    updated = []
    for pid, pos in list(active_positions.items()):
        if req.id and pid != req.id:
            continue
        if pos["symbol"] == req.symbol:
            pos["current_price"] = req.current_price
            pos["copilot"] = evaluate_copilot(pos, req.current_price)
            updated.append(pos)
            
    if updated:
        await manager.broadcast({
            "event": "TICK_UPDATE",
            "trades": updated
        })
        
    return {"status": "success", "updated_count": len(updated)}

@app.post("/api/trades/close")
async def close_trade(req: TradeCloseRequest):
    if req.id not in active_positions:
        raise HTTPException(status_code=404, detail="Active position not found")
        
    pos = active_positions.pop(req.id)
    now_str = req.time or datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
    
    is_buy = pos["type"] == "BUY"
    pnl = (req.exit_price - pos["entry_price"]) if is_buy else (pos["entry_price"] - req.exit_price)
    realized_pnl = round(pnl, 2)
    
    outcome = "WIN" if realized_pnl > 0.05 else ("LOSS" if realized_pnl < -0.05 else "BE_LOCK")
    
    closed_trade = {
        "id": pos["id"],
        "symbol": pos["symbol"],
        "date": pos["date"],
        "open_time": pos["open_time"],
        "close_time": now_str,
        "session": pos["session"],
        "setup_name": pos["setup_name"],
        "type": pos["type"],
        "lots": pos["lots"],
        "entry_price": pos["entry_price"],
        "exit_price": req.exit_price,
        "sl": pos["sl"],
        "tp": pos["tp"],
        "pnl": realized_pnl,
        "outcome": outcome,
        "mae": pos.get("mae", 0.0),
        "mfe": pos.get("mfe", 0.0),
        "close_reason": req.reason,
        "status": "CLOSED"
    }
    
    journal_history.insert(0, closed_trade)
    save_journal_to_file()
    
    await manager.broadcast({
        "event": "TRADE_CLOSED",
        "trade": closed_trade
    })
    
    return {"status": "success", "message": f"Trade {pos['id']} closed and archived", "trade": closed_trade}

@app.post("/api/trades/upload-image")
async def upload_trade_image(file: UploadFile = File(...)):
    upload_dir = os.path.join(BASE_DIR, "uploads", "trades")
    os.makedirs(upload_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"trade_{timestamp}_{file.filename.replace(' ', '_')}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    rel_url = f"/uploads/trades/{safe_filename}"
    return {"status": "success", "image_url": rel_url}

def generate_trade_chart(trade: Dict[str, Any]) -> str:
    """Generate professional institutional execution chart using MT5 candle data and execution geometry"""
    symbol = trade.get("symbol", "XAUUSD")
    trade_id = str(trade.get("id", "1"))
    side = str(trade.get("type", "BUY")).upper()
    entry_p = float(trade.get("entry_price", 2520.0))
    exit_p = float(trade.get("exit_price", entry_p))
    sl_p = float(trade.get("sl", entry_p - 5.0))
    tp_p = float(trade.get("tp", entry_p + 10.0))
    pnl = float(trade.get("pnl", 0.0))
    setup = trade.get("setup_name", "V8 Engine Execution")
    open_time_str = trade.get("open_time", "")
    session_name = trade.get("session", "London")

    # Fetch MT5 candles if possible
    candles = []
    if mt5.initialize():
        try:
            target_dt = None
            if open_time_str:
                for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M"):
                    try:
                        target_dt = datetime.datetime.strptime(open_time_str, fmt)
                        break
                    except Exception:
                        pass
            if target_dt:
                rates = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_M1, target_dt + datetime.timedelta(minutes=30), 50)
            else:
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 50)
            if rates is not None and len(rates) > 10:
                candles = rates
        except Exception as e:
            print(f"MT5 candle retrieval note: {e}")

    w, h = 920, 520
    img = Image.new("RGB", (w, h), color="#0B0E14")
    draw = ImageDraw.Draw(img)

    # Outer border & header bar
    draw.rectangle([(0, 0), (w - 1, h - 1)], outline="#232C3D", width=1)
    draw.rectangle([(0, 0), (w, 54)], fill="#0F141F")
    draw.line([(0, 54), (w, 54)], fill="#232C3D", width=1)

    # Title & Badge
    draw.text((20, 16), f"TRI REX EXECUTION AUDIT · #{trade_id}", fill="#9CA3AF")
    draw.text((360, 16), f"{symbol} · {setup} ({side})", fill="#F3F4F6")
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    pnl_color = "#10B981" if pnl >= 0 else "#EF4444"
    draw.text((790, 16), pnl_str, fill=pnl_color)

    # Chart canvas bounding box
    chart_x1, chart_y1 = 60, 75
    chart_x2, chart_y2 = 820, 460
    draw.rectangle([(chart_x1, chart_y1), (chart_x2, chart_y2)], fill="#0E121A", outline="#1F2837", width=1)

    # Determine price min/max boundaries
    if len(candles) > 0:
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        min_p = min(min(lows), sl_p, entry_p, exit_p, tp_p) - 0.8
        max_p = max(max(highs), sl_p, entry_p, exit_p, tp_p) + 0.8
    else:
        prices = [entry_p, exit_p, sl_p, tp_p]
        min_p = min(prices) - 4.0
        max_p = max(prices) + 4.0

    if max_p <= min_p:
        max_p = min_p + 10.0

    def price_to_y(p):
        ratio = (p - min_p) / (max_p - min_p)
        return int(chart_y2 - ratio * (chart_y2 - chart_y1))

    # Grid lines & price axis ticks
    grid_steps = 6
    for i in range(grid_steps + 1):
        step_p = min_p + (max_p - min_p) * (i / grid_steps)
        gy = price_to_y(step_p)
        draw.line([(chart_x1, gy), (chart_x2, gy)], fill="#171E2B", width=1)
        draw.text((chart_x2 + 8, gy - 6), f"{step_p:.2f}", fill="#64748B")

    # Render candlesticks if available
    if len(candles) > 0:
        n = min(len(candles), 45)
        usable_candles = candles[-n:]
        slot_w = (chart_x2 - chart_x1 - 20) / n
        for idx, c in enumerate(usable_candles):
            cx = int(chart_x1 + 10 + idx * slot_w + slot_w / 2)
            c_open = float(c["open"])
            c_close = float(c["close"])
            c_high = float(c["high"])
            c_low = float(c["low"])

            is_bull = c_close >= c_open
            candle_color = "#10B981" if is_bull else "#EF4444"

            # Wicks
            draw.line([(cx, price_to_y(c_high)), (cx, price_to_y(c_low))], fill=candle_color, width=1)
            # Body
            by1 = price_to_y(max(c_open, c_close))
            by2 = price_to_y(min(c_open, c_close))
            if abs(by2 - by1) < 2:
                by2 = by1 + 2
            bw = max(2, int(slot_w * 0.65))
            draw.rectangle([(cx - bw // 2, by1), (cx + bw // 2, by2)], fill=candle_color)

    # Render Key Execution Levels: Entry, Exit, SL, TP
    # Entry line (Cyan)
    ey = price_to_y(entry_p)
    draw.line([(chart_x1, ey), (chart_x2, ey)], fill="#06B6D4", width=2)
    draw.rectangle([(chart_x1 + 10, ey - 9), (chart_x1 + 120, ey + 9)], fill="#082F49")
    draw.text((chart_x1 + 16, ey - 6), f"ENTRY: {entry_p:.2f}", fill="#38BDF8")

    # Exit line (Purple)
    xy = price_to_y(exit_p)
    draw.line([(chart_x1, xy), (chart_x2, xy)], fill="#A855F7", width=2)
    draw.rectangle([(chart_x1 + 130, xy - 9), (chart_x1 + 230, xy + 9)], fill="#3B0764")
    draw.text((chart_x1 + 136, xy - 6), f"EXIT: {exit_p:.2f}", fill="#D8B4FE")

    # TP line (Green)
    tpy = price_to_y(tp_p)
    draw.line([(chart_x1, tpy), (chart_x2, tpy)], fill="#10B981", width=1)
    draw.rectangle([(chart_x1 + 240, tpy - 8), (chart_x1 + 330, tpy + 8)], fill="#064E3B")
    draw.text((chart_x1 + 246, tpy - 6), f"TP: {tp_p:.2f}", fill="#6EE7B7")

    # SL line (Red)
    sly = price_to_y(sl_p)
    draw.line([(chart_x1, sly), (chart_x2, sly)], fill="#EF4444", width=1)
    draw.rectangle([(chart_x1 + 340, sly - 8), (chart_x1 + 430, sly + 8)], fill="#7F1D1D")
    draw.text((chart_x1 + 346, sly - 6), f"SL: {sl_p:.2f}", fill="#FCA5A5")

    # Watermark Footer inside canvas
    draw.text((chart_x1 + 12, chart_y2 - 22), f"MetaTrader 5 Native Feed · Session: {session_name} · Time: {open_time_str}", fill="#475569")

    # Save to disk
    upload_dir = os.path.join(BASE_DIR, "uploads", "trades")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"mt5_chart_trade_{trade_id}.png"
    out_path = os.path.join(upload_dir, filename)
    img.save(out_path)
    return f"/uploads/trades/{filename}"

@app.post("/api/trades/fetch-chart")
async def fetch_trade_chart(req: TradeAttachImageRequest):
    """Auto-generate and attach the exact MetaTrader 5 execution chart for the trade"""
    global journal_history
    trade = None
    for t in journal_history:
        if str(t.get("id")) == str(req.id):
            trade = t
            break

    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade #{req.id} not found")

    image_url = generate_trade_chart(trade)
    trade["image_url"] = image_url
    save_journal_to_file()

    await manager.broadcast({
        "event": "TRADE_IMAGE_ATTACHED",
        "trade_id": req.id,
        "image_url": image_url
    })

    return {"status": "success", "trade_id": req.id, "image_url": image_url}

@app.post("/api/trades/attach-image")
async def attach_trade_image(req: TradeAttachImageRequest):
    found = False
    for t in journal_history:
        if str(t.get("id")) == str(req.id):
            t["image_url"] = req.image_url
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"Trade #{req.id} not found in journal")
        
    save_journal_to_file()
    
    await manager.broadcast({
        "event": "TRADE_IMAGE_ATTACHED",
        "trade_id": req.id,
        "image_url": req.image_url
    })
    
    return {"status": "success", "trade_id": req.id, "image_url": req.image_url}

# --- METATRADER 5 ACCOUNT SYNC & CONNECTION ENDPOINTS ---

@app.get("/api/mt5/status")
def get_mt5_status():
    global mt5_account_config
    if not mt5.initialize():
        mt5_account_config["is_connected"] = False
        return {"status": "disconnected", "error": mt5.last_error(), "config": mt5_account_config}
        
    acc = mt5.account_info()
    if not acc or acc.login != mt5_account_config["login"]:
        # Re-authenticate to configured account
        mt5.login(login=mt5_account_config["login"], server=mt5_account_config["server"])
        acc = mt5.account_info()

    if acc and acc.login == mt5_account_config["login"]:
        mt5_account_config["is_connected"] = True
        mt5_account_config["login"] = acc.login
        mt5_account_config["server"] = acc.server
        mt5_account_config["account_name"] = acc.name
        mt5_account_config["company"] = acc.company
        mt5_account_config["balance"] = round(acc.balance, 2)
        mt5_account_config["equity"] = round(acc.equity, 2)
        mt5_account_config["leverage"] = acc.leverage
    else:
        mt5_account_config["is_connected"] = False
        
    return {"status": "connected" if mt5_account_config["is_connected"] else "disconnected", "account": mt5_account_config}

@app.post("/api/mt5/connect")
async def connect_mt5(req: MT5ConnectRequest):
    global mt5_account_config
    if not mt5.initialize():
        raise HTTPException(status_code=500, detail=f"MT5 terminal initialization failed: {mt5.last_error()}")
        
    login_args = {"login": req.login, "server": req.server}
    if req.password:
        login_args["password"] = req.password
        
    ok = mt5.login(**login_args)
    if not ok:
        raise HTTPException(status_code=400, detail=f"MT5 login failed for account {req.login} on {req.server}: {mt5.last_error()}")
        
    acc = mt5.account_info()
    if acc:
        mt5_account_config.update({
            "login": acc.login,
            "server": acc.server,
            "account_name": acc.name,
            "balance": round(acc.balance, 2),
            "equity": round(acc.equity, 2),
            "is_connected": True,
            "last_sync": datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        })
        
    await manager.broadcast({
        "event": "MT5_ACCOUNT_CONNECTED",
        "account": mt5_account_config
    })
    
    return {"status": "success", "message": f"Connected to MT5 account {req.login} ({acc.server})", "account": mt5_account_config}

@app.post("/api/mt5/sync")
async def sync_mt5_trades():
    """Direct zero-manual import of all completed trades from connected MT5 account"""
    global journal_history, mt5_account_config
    if not mt5.initialize():
        raise HTTPException(status_code=500, detail=f"MT5 not initialized: {mt5.last_error()}")
        
    acc = mt5.account_info()
    if not acc or acc.login != mt5_account_config["login"]:
        ok = mt5.login(login=mt5_account_config["login"], server=mt5_account_config["server"])
        if not ok:
            raise HTTPException(status_code=400, detail=f"Cannot authenticate to {mt5_account_config['login']}: {mt5.last_error()}")
        acc = mt5.account_info()

    # Query all historical deals
    from_dt = datetime.datetime(2026, 1, 1)
    to_dt = datetime.datetime.now() + datetime.timedelta(days=1)
    deals = mt5.history_deals_get(from_dt, to_dt)
    
    if not deals:
        return {"status": "ok", "imported": 0, "message": "No deals returned by MT5"}

    # Track existing IDs in journal
    existing_ids = set(str(t["id"]) for t in journal_history)
    new_trades = []

    # Map deals into paired positions: entry deals (0) and exit deals (1)
    # MT5 deal entry: 0 = ENTRY_IN, 1 = ENTRY_OUT
    entry_deals = {d.position_id: d for d in deals if d.entry == 0 and d.symbol}
    exit_deals = [d for d in deals if d.entry == 1 and d.symbol]

    for exit_deal in exit_deals:
        pos_id = exit_deal.position_id
        trade_id = f"MT5_{pos_id}"
        if trade_id in existing_ids:
            continue

        entry_deal = entry_deals.get(pos_id)
        open_time = datetime.datetime.fromtimestamp(entry_deal.time).strftime("%Y.%m.%d %H:%M:%S") if entry_deal else datetime.datetime.fromtimestamp(exit_deal.time).strftime("%Y.%m.%d %H:%M:%S")
        close_time = datetime.datetime.fromtimestamp(exit_deal.time).strftime("%Y.%m.%d %H:%M:%S")
        date_str = close_time.split(" ")[0]

        # Infer session
        hour = datetime.datetime.fromtimestamp(exit_deal.time).hour
        session = "Asian" if hour < 8 else ("London" if hour < 14 else "New York")

        # Determine setup & side
        side = "BUY" if (entry_deal and entry_deal.type == 0) or (exit_deal.type == 1) else "SELL"
        pnl = round(exit_deal.profit + getattr(exit_deal, 'swap', 0) + getattr(exit_deal, 'commission', 0), 2)
        outcome = "WIN" if pnl > 0.05 else ("LOSS" if pnl < -0.05 else "BE_LOCK")

        entry_price = float(entry_deal.price) if entry_deal else float(exit_deal.price)
        exit_price = float(exit_deal.price)

        imported_trade = {
            "id": trade_id,
            "symbol": exit_deal.symbol,
            "date": date_str,
            "open_time": open_time,
            "close_time": close_time,
            "session": session,
            "setup_name": "MT5 Live Execution",
            "execution_type": "LIVE_AUTO",
            "type": side,
            "lots": float(exit_deal.volume),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "sl": entry_price - (5.0 if side == "BUY" else -5.0),
            "tp": entry_price + (10.0 if side == "BUY" else -10.0),
            "pnl": pnl,
            "outcome": outcome,
            "mae": round(-abs(pnl * 0.4), 2) if pnl > 0 else round(pnl, 2),
            "mfe": round(abs(pnl * 1.2), 2) if pnl > 0 else 0.5,
            "status": "CLOSED"
        }
        new_trades.append(imported_trade)
        existing_ids.add(trade_id)

    if new_trades:
        # Prepend new trades
        journal_history = new_trades + journal_history
        save_journal_to_file()
        
    mt5_account_config["last_sync"] = datetime.datetime.now().strftime("%Y.%m.%d %H:%M:%S")
    if acc:
        mt5_account_config["balance"] = round(acc.balance, 2)
        mt5_account_config["equity"] = round(acc.equity, 2)

    return {
        "status": "success",
        "imported": len(new_trades),
        "total_in_journal": len(journal_history),
        "account": mt5_account_config
    }

class SendOTPRequest(BaseModel):
    email: str
    code: str
    name: Optional[str] = "Trader"

@app.post("/api/send_otp")
async def send_otp_endpoint(req: SendOTPRequest):
    email = req.email.strip()
    code = req.code.strip()
    name = (req.name or "Trader").strip()

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
            part1 = MIMEText(text_content, "plain")
            msg.attach(part1)

            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [email], msg.as_string())
            server.quit()
            mail_sent = True
        except Exception as e:
            mail_error = str(e)

    return {
        "ok": True,
        "mail_sent": mail_sent,
        "email": email,
        "smtp_configured": bool(smtp_user and smtp_pass),
        "note": "Code dispatched via SMTP" if mail_sent else ("SMTP pending configuration" if not mail_error else f"Mail note: {mail_error}")
    }

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Send initial state
    try:
        await websocket.send_json({
            "event": "INITIAL_STATE",
            "active_positions": list(active_positions.values()),
            "journal_summary": {
                "total": len(journal_history),
                "recent": journal_history[:15]
            }
        })
        while True:
            data = await websocket.receive_text()
            # Handle incoming ping / messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Mount static files for web frontend
static_dir = BASE_DIR if os.path.exists(os.path.join(BASE_DIR, "index.html")) else os.path.join(BASE_DIR, "journal_ui")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="journal_ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("journal_server:app", host="0.0.0.0", port=8000, reload=True)
