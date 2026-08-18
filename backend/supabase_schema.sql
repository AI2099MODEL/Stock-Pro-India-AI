-- =================================================================
-- Gemini Revenue Engine 01 - Supabase Database Schema
-- Run this script in your Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql
-- =================================================================

-- 1. Trades Table (Executed & Filled Orders)
CREATE TABLE IF NOT EXISTS public.trades (
    id TEXT PRIMARY KEY,
    position_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
    price NUMERIC(14, 4) NOT NULL,
    quantity NUMERIC(14, 6) NOT NULL,
    leverage INTEGER DEFAULT 1,
    pnl NUMERIC(14, 2) DEFAULT 0.00,
    status TEXT NOT NULL DEFAULT 'FILLED',
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 2. Positions Table (Active Open Margin Positions)
CREATE TABLE IF NOT EXISTS public.positions (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    entry_price NUMERIC(14, 4) NOT NULL,
    quantity NUMERIC(14, 6) NOT NULL,
    leverage INTEGER DEFAULT 1,
    margin NUMERIC(14, 2) NOT NULL,
    stop_loss NUMERIC(14, 4),
    take_profit NUMERIC(14, 4),
    opened_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 3. AI Signals Table (Gemini AI Studio Generated Predictions)
CREATE TABLE IF NOT EXISTS public.ai_signals (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'HOLD')),
    confidence INTEGER NOT NULL,
    entry_price NUMERIC(14, 4) NOT NULL,
    target_1 NUMERIC(14, 4),
    target_2 NUMERIC(14, 4),
    stop_loss NUMERIC(14, 4),
    risk_reward_ratio TEXT,
    trend_bias TEXT,
    reasoning TEXT,
    indicators JSONB,
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- 4. Portfolio Logs Table (Historical Equity Snapshots)
CREATE TABLE IF NOT EXISTS public.portfolio_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    total_equity NUMERIC(14, 2) NOT NULL,
    available_margin NUMERIC(14, 2) NOT NULL,
    realized_pnl NUMERIC(14, 2) DEFAULT 0.00,
    win_rate NUMERIC(5, 2)
);

-- Enable Row Level Security (RLS) & Public Access Policies for rapid development
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous read access" ON public.trades FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert access" ON public.trades FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow anonymous read access" ON public.positions FOR SELECT USING (true);
CREATE POLICY "Allow anonymous all access" ON public.positions FOR ALL USING (true);

CREATE POLICY "Allow anonymous read access" ON public.ai_signals FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert access" ON public.ai_signals FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow anonymous read access" ON public.portfolio_logs FOR SELECT USING (true);
CREATE POLICY "Allow anonymous insert access" ON public.portfolio_logs FOR INSERT WITH CHECK (true);
