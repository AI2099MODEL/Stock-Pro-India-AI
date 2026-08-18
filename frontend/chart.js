/**
 * Gemini Revenue Engine 01 - High-Performance Canvas Candlestick & Indicator Chart
 */
class TradingChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.candles = [];
    this.indicators = {};
    this.symbol = 'BTC/USDT';
    
    // Indicators toggles
    this.showEMA = true;
    this.showBB = true;
    this.showVolume = true;
    
    // Viewport & Scaling
    this.visibleCount = 65;
    this.offsetRight = 0;
    this.hoverPos = null;
    this.activePositions = [];
    
    this.initEvents();
    this.resize();
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
    this.render();
  }

  setData(candles, indicators = {}, activePositions = []) {
    this.candles = candles || [];
    this.indicators = indicators || {};
    this.activePositions = activePositions || [];
    this.render();
  }

  updateLiveTick(price) {
    if (!this.candles || this.candles.length === 0) return;
    const last = this.candles[this.candles.length - 1];
    last.close = price;
    last.high = Math.max(last.high, price);
    last.low = Math.min(last.low, price);
    this.render();
  }

  initEvents() {
    window.addEventListener('resize', () => this.resize());
    
    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.hoverPos = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      };
      this.render();
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.hoverPos = null;
      this.render();
    });

    // Mouse wheel zoom
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      if (e.deltaY < 0) {
        this.visibleCount = Math.max(25, this.visibleCount - 5);
      } else {
        this.visibleCount = Math.min(150, this.visibleCount + 5);
      }
      this.render();
    });
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    
    if (!ctx || !w || !h) return;

    // Clear background
    ctx.fillStyle = '#080B11';
    ctx.fillRect(0, 0, w, h);

    if (!this.candles || this.candles.length === 0) {
      ctx.fillStyle = '#64748B';
      ctx.font = '13px Inter';
      ctx.textAlign = 'center';
      ctx.fillText('Loading market data...', w / 2, h / 2);
      return;
    }

    const padRight = 65;
    const padBottom = 25;
    const chartW = w - padRight;
    const chartH = h - padBottom;
    const volumeH = chartH * 0.22;
    const priceH = chartH - volumeH;

    // Visible slice
    const total = this.candles.length;
    const count = Math.min(this.visibleCount, total);
    const startIdx = Math.max(0, total - count);
    const visibleCandles = this.candles.slice(startIdx);

    // Calculate Price Min & Max
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVol = 0;

    visibleCandles.forEach(c => {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (c.volume > maxVol) maxVol = c.volume;
    });

    const pricePadding = (maxPrice - minPrice) * 0.08 || 1;
    minPrice -= pricePadding;
    maxPrice += pricePadding;
    const priceRange = maxPrice - minPrice;

    const candleWidth = chartW / visibleCandles.length;
    const barWidth = Math.max(2, candleWidth * 0.7);

    const getY = (val) => priceH - ((val - minPrice) / priceRange) * priceH;

    // --- Draw Grid ---
    ctx.strokeStyle = '#121824';
    ctx.lineWidth = 1;

    // Horizontal Price Lines
    const gridSteps = 6;
    for (let i = 0; i <= gridSteps; i++) {
      const p = minPrice + (priceRange * (i / gridSteps));
      const y = getY(p);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartW, y);
      ctx.stroke();

      // Right Axis Label
      ctx.fillStyle = '#64748B';
      ctx.font = '10px "JetBrains Mono"';
      ctx.textAlign = 'left';
      ctx.fillText(p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }), chartW + 8, y + 3);
    }

    // --- Draw Volume Bars ---
    if (this.showVolume && maxVol > 0) {
      visibleCandles.forEach((c, idx) => {
        const x = idx * candleWidth + (candleWidth / 2);
        const isBull = c.close >= c.open;
        const vH = (c.volume / maxVol) * volumeH;
        const vY = chartH - vH;

        ctx.fillStyle = isBull ? 'rgba(0, 245, 155, 0.16)' : 'rgba(255, 69, 91, 0.16)';
        ctx.fillRect(x - barWidth / 2, vY, barWidth, vH);
      });
    }

    // --- Draw EMA lines (if available) ---
    if (this.showEMA && visibleCandles.length > 5) {
      const drawEmaLine = (period, color) => {
        const k = 2 / (period + 1);
        let ema = this.candles[0].close;
        const emaVals = [];
        this.candles.forEach(c => {
          ema = c.close * k + ema * (1 - k);
          emaVals.push(ema);
        });

        const visibleEma = emaVals.slice(startIdx);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        visibleEma.forEach((val, idx) => {
          const x = idx * candleWidth + (candleWidth / 2);
          const y = getY(val);
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      };

      drawEmaLine(21, '#38BDF8'); // Cyan 21
      drawEmaLine(50, '#FBBF24'); // Gold 50
    }

    // --- Draw Candlesticks ---
    visibleCandles.forEach((c, idx) => {
      const x = idx * candleWidth + (candleWidth / 2);
      const isBull = c.close >= c.open;
      const color = isBull ? '#00F59B' : '#FF455B';
      
      const openY = getY(c.open);
      const closeY = getY(c.close);
      const highY = getY(c.high);
      const lowY = getY(c.low);

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      ctx.fillStyle = color;
      const topY = Math.min(openY, closeY);
      const bodyH = Math.max(1.5, Math.abs(closeY - openY));
      ctx.fillRect(x - barWidth / 2, topY, barWidth, bodyH);
    });

    // --- Current Price Horizontal Marker ---
    const lastCandle = visibleCandles[visibleCandles.length - 1];
    if (lastCandle) {
      const curY = getY(lastCandle.close);
      const isUp = lastCandle.close >= lastCandle.open;
      ctx.strokeStyle = isUp ? '#00F59B' : '#FF455B';
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, curY);
      ctx.lineTo(chartW, curY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Badge on right axis
      ctx.fillStyle = isUp ? '#00F59B' : '#FF455B';
      ctx.fillRect(chartW + 2, curY - 9, padRight - 4, 18);
      ctx.fillStyle = isUp ? '#07090E' : '#FFFFFF';
      ctx.font = 'bold 10px "JetBrains Mono"';
      ctx.textAlign = 'left';
      ctx.fillText(lastCandle.close.toFixed(2), chartW + 6, curY + 4);
    }

    // --- Active Trade Overlays (Entry, Target, Trailing SL) ---
    if (this.activePositions && this.activePositions.length > 0) {
      this.activePositions.forEach(pos => {
        if (!pos) return;
        
        // 1. Entry Price Line
        if (pos.entry_price) {
          const ey = getY(pos.entry_price);
          if (ey >= 0 && ey <= priceH) {
            ctx.strokeStyle = '#38BDF8';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([5, 3]);
            ctx.beginPath();
            ctx.moveTo(0, ey);
            ctx.lineTo(chartW, ey);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = '#0284C7';
            ctx.fillRect(4, ey - 8, 120, 16);
            ctx.fillStyle = '#FFFFFF';
            ctx.font = 'bold 9px "JetBrains Mono"';
            ctx.textAlign = 'left';
            ctx.fillText(`ENTRY: ₹${pos.entry_price.toFixed(2)} (${pos.action || 'LONG'})`, 8, ey + 4);
          }
        }

        // 2. Target Price Line
        if (pos.target || pos.target_price) {
          const tp = pos.target || pos.target_price;
          const ty = getY(tp);
          if (ty >= 0 && ty <= priceH) {
            ctx.strokeStyle = '#00F59B';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 2]);
            ctx.beginPath();
            ctx.moveTo(0, ty);
            ctx.lineTo(chartW, ty);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = '#059669';
            ctx.fillRect(4, ty - 8, 110, 16);
            ctx.fillStyle = '#FFFFFF';
            ctx.font = 'bold 9px "JetBrains Mono"';
            ctx.textAlign = 'left';
            ctx.fillText(`TARGET: ₹${tp.toFixed(2)}`, 8, ty + 4);
          }
        }

        // 3. Trailing Stop Loss Line
        if (pos.trailing_stop_loss || pos.stop_loss) {
          const sl = pos.trailing_stop_loss || pos.stop_loss;
          const sy = getY(sl);
          if (sy >= 0 && sy <= priceH) {
            ctx.strokeStyle = '#FF455B';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 2]);
            ctx.beginPath();
            ctx.moveTo(0, sy);
            ctx.lineTo(chartW, sy);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = '#DC2626';
            ctx.fillRect(4, sy - 8, 125, 16);
            ctx.fillStyle = '#FFFFFF';
            ctx.font = 'bold 9px "JetBrains Mono"';
            ctx.textAlign = 'left';
            ctx.fillText(`TRAILING SL: ₹${sl.toFixed(2)}`, 8, sy + 4);
          }
        }
      });
    }

    // --- Floating Active Trade HUD Box on Canvas ---
    const matchingPos = (this.activePositions || []).find(p => p.symbol === this.symbol || p.tradingsymbol === this.symbol || this.symbol.includes(p.symbol));
    if (matchingPos) {
      const hudW = 280;
      const hudH = 50;
      const hudX = chartW - hudW - 12;
      const hudY = 12;
      const isProfit = (matchingPos.pnl || 0) >= 0;

      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      ctx.strokeStyle = isProfit ? '#00F59B' : '#FF455B';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(hudX, hudY, hudW, hudH, 6);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 11px Inter';
      ctx.textAlign = 'left';
      ctx.fillText(`⚡ ACTIVE TRADE: ${matchingPos.symbol}`, hudX + 10, hudY + 18);

      ctx.fillStyle = isProfit ? '#00F59B' : '#FF455B';
      ctx.font = 'bold 12px "JetBrains Mono"';
      ctx.textAlign = 'right';
      ctx.fillText(`${isProfit ? '+' : ''}₹${(matchingPos.pnl || 0).toFixed(2)}`, hudX + hudW - 10, hudY + 18);

      ctx.fillStyle = '#94A3B8';
      ctx.font = '10px "JetBrains Mono"';
      ctx.textAlign = 'left';
      ctx.fillText(`Qty: ${matchingPos.quantity} | Entry: ₹${matchingPos.entry_price.toFixed(2)} | SL: ₹${(matchingPos.trailing_stop_loss || matchingPos.stop_loss || 0).toFixed(2)}`, hudX + 10, hudY + 38);
    }
  }
}

// --- Free Live Real-time TradingView Widget Integration ---
function getTradingViewSymbol(symbol) {
  const clean = (symbol || '').toUpperCase().trim();
  if (clean.includes('CRUDEOIL')) return 'MCX:CRUDEOIL1!';
  if (clean.includes('NATURALGAS')) return 'MCX:NATURALGAS1!';
  if (clean.includes('GOLD')) return 'MCX:GOLD1!';
  if (clean.includes('SILVER')) return 'MCX:SILVER1!';
  if (clean.includes('NIFTY')) return 'NSE:NIFTY';
  if (clean.includes('BANKNIFTY')) return 'NSE:BANKNIFTY';
  if (clean.includes('RELIANCE')) return 'BSE:RELIANCE';
  if (clean.includes('TCS')) return 'BSE:TCS';
  if (clean.includes('HDFCBANK')) return 'BSE:HDFCBANK';
  if (clean.includes('BTC')) return 'BINANCE:BTCUSDT';
  if (clean.includes('ETH')) return 'BINANCE:ETHUSDT';
  return `MCX:${clean}1!`;
}

function loadTradingViewWidget(symbol, timeframe = '15m') {
  const container = document.getElementById('tradingviewWidgetContainer');
  if (!container) return;

  if (typeof TradingView === 'undefined') {
    setTimeout(() => loadTradingViewWidget(symbol, timeframe), 500);
    return;
  }

  container.innerHTML = '';
  const tvSymbol = getTradingViewSymbol(symbol);
  let interval = '15';
  if (timeframe === '1m') interval = '1';
  else if (timeframe === '5m') interval = '5';
  else if (timeframe === '15m') interval = '15';
  else if (timeframe === '1h') interval = '60';
  else if (timeframe === '1D') interval = 'D';

  try {
    new TradingView.widget({
      "autosize": true,
      "symbol": tvSymbol,
      "interval": interval,
      "timezone": "Asia/Kolkata",
      "theme": "light",
      "style": "1",
      "locale": "in",
      "toolbar_bg": "#FFFFFF",
      "enable_publishing": false,
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tradingviewWidgetContainer",
      "studies": [
        "MASimple@tv-basicstudies",
        "RSI@tv-basicstudies"
      ]
    });
  } catch (e) {
    console.warn('TradingView widget load notice:', e);
  }
}
