# Gemini Revenue Engine 01 - Institutional AI Trading Terminal

A professional-grade, high-performance algorithmic trading terminal and autonomous revenue engine powered by **Google Gemini AI Studio** and **Supabase**, with a **FastAPI** Python backend and modern **Canvas & CSS** trading interface.

---

## ✨ Features

- ⚡ **Interactive High-Performance Candlestick & Volume Chart**: HTML5 Canvas engine with EMA (21/50), Bollinger Bands, crosshairs, dynamic zoom, and multi-timeframe navigation (`1m`, `5m`, `15m`, `1h`, `1D`).
- 🤖 **Gemini AI Studio Agent**: Deep technical market structure synthesis, generating institutional Buy/Sell/Hold setups with Confidence %, Entry targets, Stop Loss, Risk-Reward ratios, and trade rationales.
- 💬 **Gemini Copilot Interactive Chat**: Instant quant analysis and portfolio risk assessment directly in the terminal.
- 📊 **Real-time Order Execution & Paper Trading**: Market and Limit orders with leverage up to 50x, live position margin calculation, mark-to-market unrealized PnL, and position liquidation tracking.
- 🗄️ **Supabase Database Integration**: Seamless sync for `trades`, `positions`, `ai_signals`, and `portfolio_logs` with a built-in live database table inspector.
- 📡 **WebSocket Real-time Feed**: Low-latency ticker stream, live price updates, and trade ledger updates.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional)
Copy `.env.example` to `.env` or configure directly within the UI settings:
```bash
cp backend/.env.example backend/.env
```
Add your credentials:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

### 3. Run the Terminal
```bash
python run.py
```
Open **http://localhost:8000** in your browser.

---

## 🗃️ Supabase Database Schema

To set up the database tables in your Supabase project, execute the SQL script in `backend/supabase_schema.sql` inside the **Supabase SQL Editor**:
- `trades` - Executed and closed trades ledger
- `positions` - Active open margin positions
- `ai_signals` - Real-time AI prediction history
- `portfolio_logs` - Historical equity & balance tracking

---

## 🏗️ Architecture

```
d:/Antigravity/
├── backend/
│   ├── config.py             # Environment & settings loader
│   ├── gemini_agent.py       # Google Gemini AI Studio trading agent
│   ├── supabase_client.py    # Supabase CRUD manager & offline fallback
│   ├── market_engine.py      # Real-time OHLCV generator & indicator suite
│   ├── trading_engine.py     # Paper trading ledger & PnL calculator
│   ├── main.py               # FastAPI application & WebSocket router
│   ├── supabase_schema.sql   # Supabase SQL table migrations
│   └── .env.example          # Environment variables template
├── frontend/
│   ├── index.html            # Trading terminal layout
│   ├── styles.css            # Dark financial Bloomberg/TradingView design
│   ├── chart.js              # Canvas Candlestick & Volume chart
│   └── app.js                # State management, WebSocket, Copilot chat
├── requirements.txt          # Python dependencies
├── run.py                    # Server launch entry point
└── README.md                 # Project documentation
```
