import asyncio
from backend.market_engine import market_engine
from backend.trading_engine import trading_engine
from backend.gemini_agent import gemini_agent
from backend.supabase_client import supabase_manager

async def test_suite():
    print("--- 1. Testing Market Engine & Indicators ---")
    candles = market_engine.candles_history["BTC/USDT"]["15m"]
    assert len(candles) > 0, "No candles found"
    indicators = market_engine.calculate_indicators(candles)
    print(f"BTC Price: {indicators.get('price')}, RSI: {indicators.get('rsi')}, Trend: {indicators.get('trend')}")
    assert "rsi" in indicators
    assert "ema50" in indicators

    print("\n--- 2. Testing Gemini AI Agent ---")
    sig = await gemini_agent.generate_signal("BTC/USDT", "15m")
    print(f"Generated Signal: {sig.get('signal')} ({sig.get('confidence')}%) - Bias: {sig.get('trend_bias')}")
    assert sig.get("signal") in ["BUY", "SELL", "HOLD"]

    print("\n--- 3. Testing Trading Engine Order Execution ---")
    order_res = await trading_engine.execute_order({
        "symbol": "BTC/USDT",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.2,
        "leverage": 5
    })
    assert order_res["success"] is True, f"Order failed: {order_res}"
    print(f"Executed Order ID: {order_res['order']['id']}, Margin: ${order_res['position']['margin']}")

    portfolio = trading_engine.get_portfolio_summary()
    print(f"Portfolio Equity: ${portfolio['equity']}, Positions Count: {portfolio['positions_count']}")
    assert portfolio['positions_count'] >= 1

    print("\n--- 4. Testing Supabase Manager ---")
    trades = await supabase_manager.get_trades()
    print(f"Retrieved {len(trades)} trades from Supabase manager.")
    assert len(trades) > 0

    print("\n[SUCCESS] All Backend Tests Passed Successfully!")

if __name__ == "__main__":
    asyncio.run(test_suite())
