import uuid
import datetime
from typing import Dict, List, Any, Optional
from backend.config import settings
from backend.supabase_client import supabase_manager
from backend.market_engine import market_engine

class TradingEngine:
    def __init__(self):
        self.balance: float = settings.INITIAL_BALANCE
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_history: List[Dict[str, Any]] = []

    def get_portfolio_summary(self) -> Dict[str, Any]:
        total_unrealized_pnl = 0.0
        total_used_margin = 0.0
        active_positions_list = []

        for pos_id, pos in self.positions.items():
            sym = pos["symbol"]
            current_price = market_engine.prices.get(sym, pos["entry_price"])
            side = pos["side"]
            qty = pos["quantity"]
            lev = pos["leverage"]
            
            # Calculate PnL
            if side == "BUY":
                pnl = (current_price - pos["entry_price"]) * qty
            else:
                pnl = (pos["entry_price"] - current_price) * qty
                
            margin = pos["margin"]
            roe_pct = (pnl / margin * 100.0) if margin > 0 else 0.0
            
            # Liquidation Price estimate
            if side == "BUY":
                liq_price = pos["entry_price"] * (1 - (0.9 / lev))
            else:
                liq_price = pos["entry_price"] * (1 + (0.9 / lev))

            pos_copy = dict(pos)
            pos_copy["current_price"] = current_price
            pos_copy["unrealized_pnl"] = round(pnl, 2)
            pos_copy["roe_pct"] = round(roe_pct, 2)
            pos_copy["liq_price"] = round(liq_price, 2)
            
            total_unrealized_pnl += pnl
            total_used_margin += margin
            active_positions_list.append(pos_copy)

        total_equity = self.balance + total_unrealized_pnl
        free_margin = max(0.0, total_equity - total_used_margin)

        return {
            "balance": round(self.balance, 2),
            "equity": round(total_equity, 2),
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "used_margin": round(total_used_margin, 2),
            "free_margin": round(free_margin, 2),
            "positions_count": len(active_positions_list),
            "positions": active_positions_list
        }

    async def execute_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        symbol = order_data.get("symbol", "BTC/USDT")
        side = order_data.get("side", "BUY").upper()
        order_type = order_data.get("order_type", "MARKET").upper()
        quantity = float(order_data.get("quantity", 0.1))
        leverage = int(order_data.get("leverage", 1))
        stop_loss = order_data.get("stop_loss")
        take_profit = order_data.get("take_profit")
        
        current_market_price = market_engine.prices.get(symbol, 100.0)
        execution_price = float(order_data.get("price", current_market_price)) if order_type == "LIMIT" else current_market_price
        
        margin_required = (execution_price * quantity) / leverage
        summary = self.get_portfolio_summary()
        
        if margin_required > summary["free_margin"]:
            return {
                "success": False,
                "error": f"Insufficient margin: Required ${margin_required:.2f}, Free: ${summary['free_margin']:.2f}"
            }

        order_id = f"ord_{uuid.uuid4().hex[:8]}"
        pos_id = f"pos_{uuid.uuid4().hex[:8]}"
        broker_order_id = None

        # LIVE MODE: Place order on Shoonya Broker
        from backend.shoonya_service import shoonya_service
        if shoonya_service.trading_mode == "LIVE":
            if not shoonya_service.is_connected:
                return {"success": False, "error": "Live mode requires an active Shoonya session!"}
            
            sym_upper = symbol.upper().replace("/", "")
            exch_code = "MCX" if any(c in sym_upper for c in ["CRUDE", "NATURAL", "GOLD", "SILVER"]) else "NSE"
            prd_code = "M" if exch_code == "MCX" else "I"
            tran_code = "B" if side == "BUY" else "S"
            
            # Map to exact trading symbol if needed
            tsym = symbol
            for k, v in shoonya_service.INSTRUMENTS_MAP.items():
                if k in sym_upper or sym_upper in k:
                    tsym = v["tsym"]
                    break

            order_resp = shoonya_service.place_shoonya_broker_order(
                trantype=tran_code,
                prd=prd_code,
                exch=exch_code,
                tsym=tsym,
                qty=int(quantity),
                prc=execution_price if order_type == "LIMIT" else 0.0,
                prctyp="LMT" if order_type == "LIMIT" else "MKT"
            )
            if order_resp and order_resp.get("stat") == "Ok":
                broker_order_id = order_resp.get("norenordno")
                order_id = broker_order_id
            else:
                err_msg = order_resp.get("emsg", "Unknown broker rejection") if isinstance(order_resp, dict) else str(order_resp)
                return {"success": False, "error": f"Shoonya Exchange Rejection: {err_msg}"}

        # Create Position
        new_pos = {
            "id": pos_id,
            "broker_order_id": broker_order_id,
            "symbol": symbol,
            "side": side,
            "entry_price": execution_price,
            "quantity": quantity,
            "leverage": leverage,
            "margin": round(margin_required, 2),
            "stop_loss": float(stop_loss) if stop_loss else None,
            "take_profit": float(take_profit) if take_profit else None,
            "opened_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.positions[pos_id] = new_pos

        # Log Trade to memory & Supabase
        trade_record = {
            "id": order_id,
            "position_id": pos_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "price": execution_price,
            "quantity": quantity,
            "leverage": leverage,
            "pnl": 0.0,
            "status": "FILLED",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        await supabase_manager.log_trade(trade_record)
        await supabase_manager.sync_positions(list(self.positions.values()))

        return {
            "success": True,
            "order": trade_record,
            "position": new_pos
        }

    async def close_position(self, pos_id: str) -> Dict[str, Any]:
        if pos_id not in self.positions:
            return {"success": False, "error": "Position not found"}

        pos = self.positions.pop(pos_id)
        sym = pos["symbol"]
        exit_price = market_engine.prices.get(sym, pos["entry_price"])
        qty = pos["quantity"]
        side = pos["side"]
        
        if side == "BUY":
            pnl = (exit_price - pos["entry_price"]) * qty
        else:
            pnl = (pos["entry_price"] - exit_price) * qty
            
        self.balance += pnl
        
        # Log closing trade
        close_trade = {
            "id": f"close_{uuid.uuid4().hex[:8]}",
            "position_id": pos_id,
            "symbol": sym,
            "side": "SELL" if side == "BUY" else "BUY",
            "order_type": "MARKET",
            "price": exit_price,
            "quantity": qty,
            "leverage": pos["leverage"],
            "pnl": round(pnl, 2),
            "status": "CLOSED",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        await supabase_manager.log_trade(close_trade)
        await supabase_manager.sync_positions(list(self.positions.values()))

        return {
            "success": True,
            "realized_pnl": round(pnl, 2),
            "new_balance": round(self.balance, 2),
            "trade": close_trade
        }

    async def check_triggers(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """Check and auto-execute Stop-Loss and Take-Profit orders on live tick"""
        closed = []
        for pos_id, pos in list(self.positions.items()):
            if pos["symbol"] != symbol:
                continue
            
            side = pos["side"]
            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            
            should_close = False
            trigger_reason = None
            
            if side == "BUY":
                if sl and current_price <= sl:
                    should_close = True
                    trigger_reason = "STOP_LOSS_TRIGGERED"
                elif tp and current_price >= tp:
                    should_close = True
                    trigger_reason = "TAKE_PROFIT_TRIGGERED"
            elif side == "SELL":
                if sl and current_price >= sl:
                    should_close = True
                    trigger_reason = "STOP_LOSS_TRIGGERED"
                elif tp and current_price <= tp:
                    should_close = True
                    trigger_reason = "TAKE_PROFIT_TRIGGERED"
                    
            if should_close:
                res = await self.close_position(pos_id)
                if res.get("success"):
                    res["trigger_reason"] = trigger_reason
                    closed.append(res)
        return closed

trading_engine = TradingEngine()

