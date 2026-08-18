# Stock Pro Local - Institutional Algorithmic Trading Terminal

A high-performance, connectivity-first local trading terminal and autonomous revenue engine powered by **Shoonya (Finvasia)**, **Dhan HQ v2**, **Google Gemini AI**, and **Supabase**.

---

## 🚀 Quick Start

### 1. Configure Environment Variables
Copy `backend/.env.example` to `backend/.env` (or root `.env`):
```bash
cp backend/.env.example backend/.env
```
Fill in your broker credentials and Supabase keys:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-supabase-service-key
SHOONYA_USER_ID=your-user-id
SHOONYA_PASSWORD=your-password
SHOONYA_TOTP_SECRET=your-totp-secret
SHOONYA_VENDOR_CODE=your-vendor-code
SHOONYA_API_SECRET=your-api-secret
SHOONYA_IMEI=your-device-imei
DHAN_CLIENT_ID=your-dhan-client-id
DHAN_ACCESS_TOKEN=your-dhan-access-token
```

### 2. Connectivity Self-Test
Run the single diagnostic script to verify database and broker sessions before launching:
```bash
python backend/check_connections.py
```

### 3. Run the Terminal
Single-command launcher starts both the API server and UI on localhost:
```bash
start_terminal.bat
```
*(Or manually: `python run.py`)*

Open **http://127.0.0.1:8000** in your browser.
API Swagger Docs: **http://127.0.0.1:8000/docs**

---

## 🏗️ Architecture & Modules

- **`backend/brokers/shoonya.py`**: Safe wrapper for Shoonya NorenApi / REST API (`login`, `get_positions`, `get_holdings`, `get_ltp`, `place_order`, `test_connection`).
- **`backend/brokers/dhan.py`**: Safe wrapper for Dhan HQ API v2 (`get_holdings`, `get_positions`, `get_fund_limits`, `get_order_book`, `test_connection`).
- **`backend/routes/dhan_portfolio.py`**: Real-time consolidated portfolio aggregator with 15s background in-memory cache.
- **`backend/signal_writer.py`**: Schema-validated writer for all 7 signal tables (`intraday_signals`, `mcx_intraday_signals`, `btst_signals`, `weekly_momentum_signals`, `stock_options_signals`, `index_breakout_signals`, `breakouts`).
- **`backend/scanner.py`**: Asynchronous breakout/breakdown scanner loop targeting active watchlist symbols (MCX + Index + Equities).
- **`backend/routes/signals.py`**: Multi-table signal stream endpoints & status summary strip.
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
