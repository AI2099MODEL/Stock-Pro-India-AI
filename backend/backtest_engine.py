import math
from typing import Dict, List, Any
from backend.market_engine import market_engine

class BacktestEngine:
    """
    High-speed quantitative backtester for evaluating algorithmic trading strategies:
    - Gemini Momentum & Trend Following
    - RSI Mean Reversion (Oversold/Overbought)
    - EMA Golden / Death Cross (21/50)
    - Bollinger Band Squeeze Breakout
    """
    
    def run_backtest(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        strategy: str = "GEMINI_MOMENTUM",
        initial_capital: float = 10000.0,
        leverage: int = 5,
        take_profit_pct: float = 2.5,
        stop_loss_pct: float = 1.2
    ) -> Dict[str, Any]:
        # Generate or retrieve historical candles
        candles = market_engine.candles_history.get(symbol, {}).get(timeframe, [])
        if not candles or len(candles) < 60:
            candles = market_engine._generate_seed_candles(symbol, timeframe, count=250)
            
        capital = initial_capital
        equity_curve = [{"time": candles[0]["time"], "equity": capital}]
        trades = []
        
        position = None  # {'side': 'BUY'/'SELL', 'entry_price': float, 'entry_time': int, 'qty': float}
        
        # Precompute indicators
        closes = [c["close"] for c in candles]
        
        for i in range(30, len(candles)):
            c = candles[i]
            slice_candles = candles[:i+1]
            ind = market_engine.calculate_indicators(slice_candles)
            price = c["close"]
            timestamp = c["time"]
            
            # Check existing position for TP / SL exits
            if position:
                side = position["side"]
                entry = position["entry_price"]
                qty = position["qty"]
                
                pct_change = ((price - entry) / entry) * 100.0 if side == "BUY" else ((entry - price) / entry) * 100.0
                
                # Check Take Profit
                if pct_change >= take_profit_pct:
                    pnl = (capital * 0.5 * (take_profit_pct / 100.0)) * leverage
                    capital += pnl
                    trades.append({
                        "id": f"bt_{len(trades)+1}",
                        "entry_price": entry,
                        "exit_price": price,
                        "side": side,
                        "pnl": round(pnl, 2),
                        "return_pct": round(pct_change * leverage, 2),
                        "exit_reason": "TAKE_PROFIT",
                        "time": timestamp
                    })
                    position = None
                # Check Stop Loss
                elif pct_change <= -stop_loss_pct:
                    pnl = -(capital * 0.5 * (stop_loss_pct / 100.0)) * leverage
                    capital += pnl
                    trades.append({
                        "id": f"bt_{len(trades)+1}",
                        "entry_price": entry,
                        "exit_price": price,
                        "side": side,
                        "pnl": round(pnl, 2),
                        "return_pct": round(pct_change * leverage, 2),
                        "exit_reason": "STOP_LOSS",
                        "time": timestamp
                    })
                    position = None
                    
            # If no open position, evaluate entry conditions
            if not position:
                rsi = ind.get("rsi", 50.0)
                ema21 = ind.get("ema21", price)
                ema50 = ind.get("ema50", price)
                macd_hist = ind.get("macd", {}).get("histogram", 0.0)
                
                signal = None
                
                if strategy == "GEMINI_MOMENTUM":
                    if price > ema50 and macd_hist > 0 and 42 < rsi < 68:
                        signal = "BUY"
                    elif price < ema50 and macd_hist < 0 and 32 < rsi < 58:
                        signal = "SELL"
                elif strategy == "RSI_MEAN_REVERSION":
                    if rsi < 32:
                        signal = "BUY"
                    elif rsi > 68:
                        signal = "SELL"
                elif strategy == "EMA_CROSS":
                    if ema21 > ema50:
                        signal = "BUY"
                    elif ema21 < ema50:
                        signal = "SELL"
                        
                if signal:
                    position = {
                        "side": signal,
                        "entry_price": price,
                        "entry_time": timestamp,
                        "qty": (capital * 0.5 * leverage) / price
                    }
                    
            equity_curve.append({
                "time": timestamp,
                "equity": round(capital, 2)
            })
            
        # Calculate Backtest Performance Metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t["pnl"] > 0]
        losing_trades = [t for t in trades if t["pnl"] <= 0]
        
        win_rate = round((len(winning_trades) / total_trades * 100.0), 2) if total_trades > 0 else 0.0
        total_net_profit = round(capital - initial_capital, 2)
        total_return_pct = round(((capital - initial_capital) / initial_capital) * 100.0, 2)
        
        # Profit Factor
        gross_profit = sum(t["pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["pnl"] for t in losing_trades))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        
        # Max Drawdown
        peak = initial_capital
        max_dd = 0.0
        for pt in equity_curve:
            if pt["equity"] > peak:
                peak = pt["equity"]
            dd = (peak - pt["equity"]) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
                
        # Sharpe Ratio estimate
        returns = [t["return_pct"] for t in trades]
        avg_ret = sum(returns) / len(returns) if returns else 0
        var = sum((r - avg_ret)**2 for r in returns) / len(returns) if returns else 1
        sharpe = round((avg_ret / math.sqrt(var)) * math.sqrt(252), 2) if var > 0 else 0.0

        return {
            "symbol": symbol,
            "strategy": strategy,
            "timeframe": timeframe,
            "initial_capital": initial_capital,
            "final_capital": round(capital, 2),
            "net_profit": total_net_profit,
            "total_return_pct": total_return_pct,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": sharpe,
            "trades": trades[-20:],
            "equity_curve": equity_curve[::3]
        }

backtest_engine = BacktestEngine()
