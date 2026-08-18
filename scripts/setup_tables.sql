
CREATE TABLE IF NOT EXISTS intraday_signals (
    id bigint generated always as identity primary key,
    symbol text not null,
    strategy text not null,
    signal text not null,
    price numeric,
    stop_loss numeric,
    target numeric,
    trailing_stop_loss numeric,
    status text default 'OPEN',
    details jsonb,
    trade_date date not null,
    signal_time timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (symbol, strategy, trade_date)
);

CREATE TABLE IF NOT EXISTS btst_signals (
    id bigint generated always as identity primary key,
    symbol text not null,
    strategy text not null,
    signal text not null,
    price numeric,
    stop_loss numeric,
    target numeric,
    trailing_stop_loss numeric,
    status text default 'OPEN',
    details jsonb,
    trade_date date not null,
    signal_time timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (symbol, strategy, trade_date)
);

CREATE TABLE IF NOT EXISTS weekly_momentum_signals (
    id bigint generated always as identity primary key,
    symbol text not null,
    strategy text not null,
    signal text not null,
    price numeric,
    stop_loss numeric,
    target numeric,
    trailing_stop_loss numeric,
    status text default 'OPEN',
    details jsonb,
    trade_date date not null,
    signal_time timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (symbol, strategy, trade_date)
);

CREATE TABLE IF NOT EXISTS stock_options_signals (
    id bigint generated always as identity primary key,
    underlying_symbol text not null,
    underlying_signal text not null,
    underlying_score int,
    tradable boolean not null,
    reason text,
    option_symbol text,
    token text,
    strike numeric,
    option_type text,
    expiry text,
    ltp numeric,
    vwap numeric,
    ema9 numeric,
    ema21 numeric,
    lot_size int,
    money_required numeric,
    target_price numeric,
    trail_sl numeric,
    trade_date date not null,
    signal_time timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (underlying_symbol, trade_date)
);
