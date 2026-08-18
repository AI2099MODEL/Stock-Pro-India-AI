/**
 * Stock Pro India AI Trading Terminal - Main Controller
 * High-Performance Native Canvas Candlestick Engine, 5-Tab Navigation, Real Shoonya & Dhan Feeds
 */

const state = {
  activeSymbol: 'CRUDEOIL',
  activeTimeframe: '15m',
  activeTab: 'tabOverview',
  activeSignalFilter: 'ALL',
  prices: {
    'CRUDEOIL': 6432.0,
    'NATURALGAS': 194.50,
    'GOLD': 71280.0,
    'SILVER': 82450.0,
    'NIFTY 50': 24850.0,
    'BANKNIFTY': 51200.0,
    'FINNIFTY': 23450.0,
    'SENSEX': 81500.0,
    'RELIANCE': 2985.0,
    'TCS': 4195.0,
    'HDFCBANK': 1642.0,
    'INFY': 1840.0
  },
  activeTrades: [],
  realizedTrades: [],
  oracleSignals: [],
  mainChart: null,
  mcxCharts: {}
};

// ============================================================================
// NATIVE HTML5 CANVAS CANDLESTICK & VOLUME ENGINE (Zero External Dependencies)
// ============================================================================
class CanvasChartEngine {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.candles = [];
    this.hoverIndex = -1;
    this.mouseX = -1;
    this.mouseY = -1;

    this.initEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
    this.draw();
  }

  initEvents() {
    if (!this.canvas) return;
    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.mouseX = e.clientX - rect.left;
      this.mouseY = e.clientY - rect.top;
      this.calculateHover();
      this.draw();
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.hoverIndex = -1;
      this.mouseX = -1;
      this.mouseY = -1;
      this.draw();
    });
  }

  setCandles(candles) {
    this.candles = candles || [];
    this.draw();
  }

  calculateHover() {
    if (!this.candles.length || this.mouseX < 0) return;
    const paddingRight = 65;
    const plotWidth = this.width - paddingRight;
    const n = this.candles.length;
    const candleWidth = plotWidth / n;
    this.hoverIndex = Math.min(n - 1, Math.max(0, Math.floor(this.mouseX / candleWidth)));

    const c = this.candles[this.hoverIndex];
    const infoEl = document.getElementById('chartCandleInfo');
    if (infoEl && c) {
      const isUp = c.close >= c.open;
      infoEl.innerHTML = `Time: <b>${c.timeStr || '--'}</b> | O: <b>${c.open.toFixed(2)}</b> H: <b>${c.high.toFixed(2)}</b> L: <b>${c.low.toFixed(2)}</b> C: <b style="color:${isUp ? '#10B981' : '#EF4444'}">${c.close.toFixed(2)}</b> Vol: <b>${c.volume || 100}</b>`;
    }
  }

  calculateEMA(period) {
    const k = 2 / (period + 1);
    const emaValues = [];
    let prevEma = null;

    for (let i = 0; i < this.candles.length; i++) {
      const price = this.candles[i].close;
      if (prevEma === null) {
        prevEma = price;
      } else {
        prevEma = (price * k) + (prevEma * (1 - k));
      }
      emaValues.push(prevEma);
    }
    return emaValues;
  }

  draw() {
    if (!this.canvas || !this.ctx || !this.width || !this.height) return;
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.clearRect(0, 0, w, h);

    if (!this.candles.length) {
      ctx.fillStyle = '#94A3B8';
      ctx.font = '12px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('Loading live candlestick feed...', w / 2, h / 2);
      return;
    }

    const paddingRight = 65;
    const paddingBottom = 24;
    const plotWidth = w - paddingRight;
    const plotHeight = h - paddingBottom;
    const volumeHeight = plotHeight * 0.22;
    const priceHeight = plotHeight - volumeHeight;

    // Price Bounds
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVol = 0;

    for (const c of this.candles) {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if ((c.volume || 100) > maxVol) maxVol = (c.volume || 100);
    }

    const priceMargin = (maxPrice - minPrice) * 0.08 || 1;
    minPrice -= priceMargin;
    maxPrice += priceMargin;
    const priceRange = maxPrice - minPrice;

    // Background Grid
    ctx.strokeStyle = '#F1F5F9';
    ctx.lineWidth = 1;

    // Horizontal grid & Price Axis Labels
    const steps = 5;
    ctx.fillStyle = '#64748B';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';

    for (let i = 0; i <= steps; i++) {
      const y = (priceHeight / steps) * i;
      const price = maxPrice - (priceRange / steps) * i;

      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(plotWidth, y);
      ctx.stroke();

      ctx.fillText(price.toFixed(2), plotWidth + 6, y + 3);
    }

    // Vertical grid & Time Axis
    const n = this.candles.length;
    const candleSpacing = plotWidth / n;
    const candleWidth = Math.max(2, candleSpacing * 0.72);

    const timeStep = Math.max(1, Math.floor(n / 6));
    ctx.textAlign = 'center';

    for (let i = 0; i < n; i += timeStep) {
      const x = i * candleSpacing + candleSpacing / 2;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, plotHeight);
      ctx.stroke();

      const timeLabel = this.candles[i].timeStr ? this.candles[i].timeStr.split(' ')[1] || this.candles[i].timeStr : `${i}`;
      ctx.fillText(timeLabel, x, h - 6);
    }

    // Draw Volume Bars
    for (let i = 0; i < n; i++) {
      const c = this.candles[i];
      const x = i * candleSpacing + candleSpacing / 2;
      const vol = c.volume || 100;
      const vh = (vol / (maxVol || 1)) * volumeHeight;
      const y = plotHeight - vh;
      const isUp = c.close >= c.open;

      ctx.fillStyle = isUp ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)';
      ctx.fillRect(x - candleWidth / 2, y, candleWidth, vh);
    }

    // Draw Candlesticks
    for (let i = 0; i < n; i++) {
      const c = this.candles[i];
      const x = i * candleSpacing + candleSpacing / 2;
      const isUp = c.close >= c.open;

      const openY = priceHeight - ((c.open - minPrice) / priceRange) * priceHeight;
      const closeY = priceHeight - ((c.close - minPrice) / priceRange) * priceHeight;
      const highY = priceHeight - ((c.high - minPrice) / priceRange) * priceHeight;
      const lowY = priceHeight - ((c.low - minPrice) / priceRange) * priceHeight;

      const candleTop = Math.min(openY, closeY);
      const candleBottom = Math.max(openY, closeY);
      const bodyHeight = Math.max(2, candleBottom - candleTop);

      const color = isUp ? '#10B981' : '#EF4444';
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1.2;

      // Wick
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      ctx.fillRect(x - candleWidth / 2, candleTop, candleWidth, bodyHeight);
    }

    // Draw EMA 20 (Blue) & EMA 50 (Orange)
    const ema20 = this.calculateEMA(20);
    const ema50 = this.calculateEMA(50);

    const drawLine = (vals, strokeColor) => {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (let i = 0; i < vals.length; i++) {
        const x = i * candleSpacing + candleSpacing / 2;
        const y = priceHeight - ((vals[i] - minPrice) / priceRange) * priceHeight;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    };

    drawLine(ema20, '#2563EB');
    drawLine(ema50, '#F59E0B');

    // Draw Crosshair
    if (this.mouseX >= 0 && this.mouseX <= plotWidth && this.mouseY >= 0 && this.mouseY <= plotHeight) {
      ctx.strokeStyle = '#94A3B8';
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(this.mouseX, 0);
      ctx.lineTo(this.mouseX, plotHeight);
      ctx.stroke();

      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(0, this.mouseY);
      ctx.lineTo(plotWidth, this.mouseY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Current mouse price pill
      const hoveredPrice = maxPrice - (this.mouseY / priceHeight) * priceRange;
      ctx.fillStyle = '#0F172A';
      ctx.fillRect(plotWidth + 2, this.mouseY - 8, 60, 16);
      ctx.fillStyle = '#FFFFFF';
      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(hoveredPrice.toFixed(2), plotWidth + 6, this.mouseY + 4);
    }
  }
}

// ============================================================================
// APP INITIALIZATION & CONTROLLERS
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
  // 1. Tab Navigation
  initTabNavigation();

  // 2. Timeframe Switchers
  initTimeframeButtons();

  // 3. Native Canvas Chart
  state.mainChart = new CanvasChartEngine('mainChartCanvas');

  // 4. Shoonya Quick Feeder
  initQuickShoonyaTokenFeeder();

  // 5. Dhan Live API Connect
  initDhanBrokerControls();

  // 5b. Dedicated Broker Login & Connectivity Gateway
  initBrokerLoginGateway();

  // 6. Fast Order Ticket
  initOrderTicket();

  // 7. Oracle Signal Filter Sub-Tabs
  initSignalFilterTabs();

  // Initial Data Loads
  loadMainCandleChart(state.activeSymbol, state.activeTimeframe);
  fetchMarketOverview();
  fetchActiveTrades();
  fetchRealizedLedger();
  fetchOracleSignals();
  fetchShoonyaStatus();

  // 1.5s High-Performance Polling Loop
  setInterval(() => {
    fetchMarketOverview();
    fetchActiveTrades();
    if (state.activeTab === 'tabDhan') {
      fetchDhanHoldings();
    }
  }, 1500);

  // 10s Chart & Signals Refresh
  setInterval(() => {
    if (state.activeTab === 'tabOverview') {
      loadMainCandleChart(state.activeSymbol, state.activeTimeframe);
    } else if (state.activeTab === 'tabOracle') {
      fetchOracleSignals();
    } else if (state.activeTab === 'tabDhan') {
      fetchDhanAiRecommendations();
      fetchDhanFunds();
    }
  }, 10000);
});

// --- Tab Navigation ---
function initTabNavigation() {
  const buttons = document.querySelectorAll('.nav-link-btn');
  buttons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.nav-link-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-view-container').forEach(v => v.classList.remove('active'));

      e.currentTarget.classList.add('active');
      const targetId = e.currentTarget.dataset.tab;
      const targetView = document.getElementById(targetId);
      if (targetView) targetView.classList.add('active');
      state.activeTab = targetId;

      if (targetId === 'tabOverview') {
        if (state.mainChart) state.mainChart.resize();
        loadMainCandleChart(state.activeSymbol, state.activeTimeframe);
      } else if (targetId === 'tabDhan') {
        fetchDhanHoldings();
        fetchDhanFunds();
        fetchDhanAiRecommendations();
      } else if (targetId === 'tabMcx') {
        loadMcxGridCharts();
      } else if (targetId === 'tabOracle') {
        fetchOracleSignals();
      } else if (targetId === 'tabLedger') {
        fetchRealizedLedger();
      }
    });
  });
}

// --- Timeframe Buttons ---
function initTimeframeButtons() {
  document.querySelectorAll('.tf-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      state.activeTimeframe = e.target.dataset.tf;
      loadMainCandleChart(state.activeSymbol, state.activeTimeframe);
    });
  });
}

// --- Native Candlestick Fetch & Render ---
async function loadMainCandleChart(symbol, timeframe = '15m') {
  try {
    const res = await fetch(`/api/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
    if (res.ok) {
      const data = await res.json();
      const rawCandles = data.candles || [];
      if (rawCandles.length > 0) {
        const formatted = rawCandles.map(c => {
          let timeStr = c.time || c.datetime || '';
          if (!timeStr && c.timestamp) {
            const dt = new Date(c.timestamp * 1000);
            timeStr = dt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
          }
          return {
            open: parseFloat(c.open),
            high: parseFloat(c.high),
            low: parseFloat(c.low),
            close: parseFloat(c.close),
            volume: parseFloat(c.volume || 100),
            timeStr: timeStr
          };
        });

        if (state.mainChart) {
          state.mainChart.setCandles(formatted);
        }
      }
    }
  } catch (e) {
    console.warn('Candle fetch error:', e);
  }
}

// --- MCX 4-Quadrant Live Grid ---
function loadMcxGridCharts() {
  const configs = [
    { id: 'mcxCanvasCrude', sym: 'CRUDEOIL', priceId: 'mcxGridPriceCrude' },
    { id: 'mcxCanvasGold', sym: 'GOLD', priceId: 'mcxGridPriceGold' },
    { id: 'mcxCanvasSilver', sym: 'SILVER', priceId: 'mcxGridPriceSilver' },
    { id: 'mcxCanvasNatgas', sym: 'NATURALGAS', priceId: 'mcxGridPriceNatgas' }
  ];

  configs.forEach(async c => {
    if (!state.mcxCharts[c.id]) {
      state.mcxCharts[c.id] = new CanvasChartEngine(c.id);
    }
    const engine = state.mcxCharts[c.id];
    engine.resize();

    try {
      const res = await fetch(`/api/market/candles?symbol=${c.sym}&timeframe=15m`);
      if (res.ok) {
        const data = await res.json();
        const raw = data.candles || [];
        const formatted = raw.map(candle => ({
          open: parseFloat(candle.open),
          high: parseFloat(candle.high),
          low: parseFloat(candle.low),
          close: parseFloat(candle.close),
          volume: parseFloat(candle.volume || 100),
          timeStr: candle.time || ''
        }));
        engine.setCandles(formatted);

        if (formatted.length > 0) {
          const last = formatted[formatted.length - 1];
          const el = document.getElementById(c.priceId);
          if (el) el.innerText = `₹${last.close.toLocaleString(undefined, {minimumFractionDigits:2})}`;
        }
      }
    } catch (e) {}
  });
}

function switchSymbol(symbol) {
  state.activeSymbol = symbol;
  
  const titleEl = document.getElementById('chartActiveSymbolTitle');
  if (titleEl) titleEl.innerText = `${symbol}`;

  const sel = document.getElementById('ticketSelectSymbol');
  if (sel) sel.value = symbol;

  document.querySelectorAll('.ticker-chip').forEach(c => {
    c.classList.toggle('active', c.innerText.includes(symbol));
  });

  loadMainCandleChart(symbol, state.activeTimeframe);
}

// --- Market Overview & Ticker Ribbon ---
async function fetchMarketOverview() {
  try {
    const res = await fetch('/api/market/overview');
    if (!res.ok) return;
    const quotes = await res.json();
    if (!Array.isArray(quotes)) return;

    const ribbon = document.getElementById('tickerRibbon');
    if (!ribbon) return;

    quotes.forEach(q => {
      state.prices[q.symbol] = q.price;
      const chipId = `chip_${q.symbol.replace(/[^a-zA-Z0-9]/g, '_')}`;
      let chip = document.getElementById(chipId);
      const isUp = q.change_pct >= 0;

      if (!chip) {
        chip = document.createElement('div');
        chip.id = chipId;
        chip.className = `ticker-chip ${q.symbol === state.activeSymbol ? 'active' : ''}`;
        chip.addEventListener('click', () => switchSymbol(q.symbol));
        ribbon.appendChild(chip);
      }

      chip.innerHTML = `
        <span style="color:#0F172A;">${q.symbol}</span>
        <span class="${isUp ? 'val-green' : 'val-red'}">₹${q.price.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
        <span class="${isUp ? 'val-green' : 'val-red'}" style="font-size:10px;">${isUp ? '+' : ''}${q.change_pct}%</span>
      `;
    });

    const activePrice = state.prices[state.activeSymbol];
    const liveCmpEl = document.getElementById('chartLiveCmpDisplay');
    if (liveCmpEl && activePrice) {
      liveCmpEl.innerText = `₹${activePrice.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    }
  } catch (e) {}
}

// --- Active Open Trades & PnL Bar ---
async function fetchActiveTrades() {
  try {
    const res = await fetch('/api/shoonya/positions');
    if (!res.ok) return;
    const data = await res.json();
    const trades = data.positions || [];
    state.activeTrades = trades;

    const tbody = document.getElementById('activeTradesTableBody');
    const countBadge = document.getElementById('activeTradesCountBadge');
    const heroOpenPnl = document.getElementById('heroUnrealizedPnl');
    const heroDeployed = document.getElementById('heroDeployedCapital');

    let totalOpenPnl = 0.0;
    let totalDeployed = 0.0;

    if (trades.length === 0) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:20px;">⚡ Bot Idle • Scanning Breakouts...</td></tr>`;
      if (countBadge) countBadge.innerText = '0 Open';
      if (heroOpenPnl) { heroOpenPnl.innerText = '₹0.00'; heroOpenPnl.className = 'kpi-val-mini'; }
      if (heroDeployed) heroDeployed.innerText = '₹0.00';
      return;
    }

    if (countBadge) countBadge.innerText = `${trades.length} Open`;

    if (tbody) {
      tbody.innerHTML = trades.map(t => {
        const pnl = t.pnl || 0.0;
        totalOpenPnl += pnl;
        totalDeployed += (t.invested_amount || (t.entry_price * t.quantity));
        const isUp = pnl >= 0;

        return `
          <tr>
            <td><b style="color:#0F172A;">${t.symbol}</b></td>
            <td><span class="${t.action.includes('BUY') ? 'val-green' : 'val-red'}"><b>${t.action}</b></span></td>
            <td>${t.quantity}</td>
            <td>₹${t.entry_price.toFixed(2)}</td>
            <td style="font-weight:700; color:${isUp ? '#10B981' : '#EF4444'};">₹${t.cmp.toFixed(2)}</td>
            <td class="${isUp ? 'val-green' : 'val-red'}" style="font-weight:800;">${isUp ? '+' : ''}₹${pnl.toFixed(2)}</td>
            <td>
              <button style="background:#EF4444; color:#FFF; border:none; padding:3px 8px; border-radius:4px; font-weight:700; font-size:10px; cursor:pointer;" onclick="closeTrade('${t.id}')">
                Square Off
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    if (heroOpenPnl) {
      const isUp = totalOpenPnl >= 0;
      heroOpenPnl.innerText = `${isUp ? '+' : ''}₹${totalOpenPnl.toFixed(2)}`;
      heroOpenPnl.className = `kpi-val-mini ${isUp ? 'val-green' : 'val-red'}`;
    }

    if (heroDeployed) {
      heroDeployed.innerText = `₹${totalDeployed.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    }
  } catch (e) {}
}

async function closeTrade(tradeId) {
  try {
    const res = await fetch('/api/shoonya/close-trade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trade_id: tradeId, reason: 'MANUAL_SQUARE_OFF' })
    });
    const data = await res.json();
    if (data.success) {
      fetchActiveTrades();
      fetchRealizedLedger();
    }
  } catch (e) {
    alert('Failed to close trade: ' + e.message);
  }
}

// --- 1-Click Fast Order Execution Ticket ---
function initOrderTicket() {
  const btnBuy = document.getElementById('btnExecuteBuy');
  const btnSell = document.getElementById('btnExecuteSell');
  
  if (btnBuy) btnBuy.addEventListener('click', () => executeManualOrder('BUY'));
  if (btnSell) btnSell.addEventListener('click', () => executeManualOrder('SELL'));
}

async function executeManualOrder(action) {
  const symbol = document.getElementById('ticketSelectSymbol').value;
  const qty = parseInt(document.getElementById('ticketInputQty').value) || 1;
  const target = parseFloat(document.getElementById('ticketInputTarget').value) || null;
  const sl = parseFloat(document.getElementById('ticketInputSL').value) || null;

  try {
    const res = await fetch('/api/shoonya/execute-signal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        signal_data: {
          symbol: symbol,
          action: action,
          quantity: qty,
          target_price: target,
          stop_loss: sl,
          source_table: 'MANUAL_TICKET'
        }
      })
    });
    const data = await res.json();
    if (data.success) {
      alert(`✅ Order Placed: ${action} ${qty} Lot(s) of ${symbol}`);
      fetchActiveTrades();
    } else {
      alert('❌ Order Notice: ' + (data.error || 'Check margin/connection'));
    }
  } catch (e) {
    alert('Order Error: ' + e.message);
  }
}

// --- Oracle 5-Table Signals Watchlist Stream ---
function initSignalFilterTabs() {
  document.querySelectorAll('.sub-tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      state.activeSignalFilter = e.target.dataset.filter;
      renderOracleSignalsTable();
    });
  });
}

async function fetchOracleSignals() {
  try {
    const res = await fetch('/api/shoonya/scan-signals');
    if (!res.ok) return;
    const signals = await res.json();
    state.oracleSignals = signals || [];
    renderOracleSignalsTable();
  } catch (e) {}
}

function renderOracleSignalsTable() {
  const tbody = document.getElementById('oracleSignalsTableBody');
  if (!tbody) return;

  const filter = state.activeSignalFilter;
  let filtered = state.oracleSignals;

  if (filter === 'INDEX') {
    filtered = filtered.filter(s => ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'].some(idx => (s.symbol || '').includes(idx)) || (s.source_table || '').includes('index'));
  } else if (filter === 'MCX') {
    filtered = filtered.filter(s => ['CRUDE', 'GOLD', 'SILVER', 'NATURAL'].some(c => (s.symbol || '').includes(c)) || (s.source_table || '').includes('mcx'));
  } else if (filter === 'INTRADAY') {
    filtered = filtered.filter(s => (s.source_table || '').includes('intraday'));
  } else if (filter === 'BTST') {
    filtered = filtered.filter(s => (s.source_table || '').includes('btst') || (s.source_table || '').includes('weekly'));
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-dim); padding:24px;">Scanning Oracle Signal Tables... No active breakout triggers in this category right now.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(s => {
    return `
      <tr>
        <td><span style="font-size:10px; background:#EFF6FF; color:#2563EB; padding:2px 6px; border-radius:4px; font-weight:700;">${s.source_table || 'BREAKOUT'}</span></td>
        <td><b>${s.symbol}</b></td>
        <td><span class="${(s.action || '').includes('BUY') ? 'val-green' : 'val-red'}"><b>${s.action || 'BUY'}</b></span></td>
        <td>₹${(s.spot_price || s.cmp || 0).toFixed(2)}</td>
        <td style="color:#10B981;">₹${(s.target_price || 0).toFixed(2)}</td>
        <td style="color:#EF4444;">₹${(s.stop_loss || 0).toFixed(2)}</td>
        <td>${s.strategy || 'Momentum Breakout'}</td>
        <td>
          <button style="background:#2563EB; color:#FFF; border:none; padding:4px 10px; border-radius:4px; font-weight:700; font-size:10px; cursor:pointer;" onclick="executeOracleSignal('${s.symbol}', '${s.action || 'BUY'}')">
            ⚡ Execute
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function executeOracleSignal(symbol, action) {
  try {
    const res = await fetch('/api/shoonya/execute-signal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        signal_data: {
          symbol: symbol,
          action: action,
          quantity: 1,
          source_table: 'ORACLE_STREAM'
        }
      })
    });
    const data = await res.json();
    if (data.success) {
      alert(`✅ Executed Signal: ${action} ${symbol}`);
      fetchActiveTrades();
    }
  } catch (e) {
    alert('Execution Error: ' + e.message);
  }
}

// --- Realized Trade Ledger ---
async function fetchRealizedLedger() {
  try {
    const res = await fetch('/api/shoonya/profit-log');
    if (!res.ok) return;
    const trades = await res.json();
    const tbody = document.getElementById('tradeLedgerTableBody');
    const heroRealized = document.getElementById('heroRealizedPnl');

    if (!Array.isArray(trades) || trades.length === 0) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-dim); padding:24px;">No realized trades logged yet. Baseline realized PnL is ₹0.00.</td></tr>`;
      if (heroRealized) heroRealized.innerText = '+₹0.00';
      return;
    }

    let netPnl = 0.0;
    if (tbody) {
      tbody.innerHTML = trades.map(t => {
        netPnl += (t.net_pnl || 0.0);
        const isUp = (t.net_pnl || 0) >= 0;
        return `
          <tr>
            <td>${t.trade_id || t.id || '--'}</td>
            <td><b>${t.symbol}</b></td>
            <td>${t.quantity}</td>
            <td>₹${(t.entry_price || 0).toFixed(2)}</td>
            <td>₹${(t.exit_price || 0).toFixed(2)}</td>
            <td>₹${(t.gross_pnl || 0).toFixed(2)}</td>
            <td style="color:var(--text-dim);">₹${(t.brokerage || 0).toFixed(2)}</td>
            <td class="${isUp ? 'val-green' : 'val-red'}" style="font-weight:800;">${isUp ? '+' : ''}₹${(t.net_pnl || 0).toFixed(2)}</td>
            <td><span style="font-size:10px; padding:2px 6px; border-radius:4px; background:#F1F5F9;">${t.exit_reason || 'CLOSED'}</span></td>
            <td style="color:var(--text-dim); font-size:10px;">${t.timestamp || '--'}</td>
          </tr>
        `;
      }).join('');
    }

    if (heroRealized) {
      const isUp = netPnl >= 0;
      heroRealized.innerText = `${isUp ? '+' : ''}₹${netPnl.toFixed(2)}`;
      heroRealized.className = `kpi-val-mini ${isUp ? 'val-green' : 'val-red'}`;
    }
  } catch (e) {}
}

function initDhanBrokerControls() {
  const btnConnect = document.getElementById('btnConnectDhanApi');
  const inputClientId = document.getElementById('inputDhanClientId');
  const inputToken = document.getElementById('inputDhanAccessToken');
  const msgEl = document.getElementById('dhanConnectionStatusMsg');
  const btnBuy = document.getElementById('btnDhanFastBuy');
  const btnSell = document.getElementById('btnDhanFastSell');
  const btnAiAnalysis = document.getElementById('btnRunCustomAiScripAnalysis');

  // Auto-restore stored Dhan credentials from localStorage
  const savedClientId = localStorage.getItem('dhan_client_id') || '';
  const savedToken = localStorage.getItem('dhan_access_token') || '';
  if (savedClientId && inputClientId) inputClientId.value = savedClientId;
  if (savedToken && inputToken) inputToken.value = savedToken;

  if (btnConnect) {
    btnConnect.addEventListener('click', async () => {
      const clientId = (inputClientId ? inputClientId.value : '').trim();
      const token = (inputToken ? inputToken.value : '').trim();

      if (!clientId || !token) {
        if (msgEl) msgEl.innerHTML = '<span style="color:#EF4444;">Please provide both Dhan Client ID and Access Token.</span>';
        return;
      }

      btnConnect.innerText = 'Connecting...';
      try {
        const res = await fetch('/api/dhan/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: clientId, access_token: token })
        });
        const data = await res.json();
        if (data.connected) {
          localStorage.setItem('dhan_client_id', clientId);
          localStorage.setItem('dhan_access_token', token);
          if (msgEl) msgEl.innerHTML = `<span style="color:#10B981; font-weight:700;">✅ Connected to Dhan Live Account (Client: ${clientId})</span>`;
          updateDhanConnectionBadge(true, clientId);
          fetchDhanHoldings();
          fetchDhanFunds();
          fetchDhanAiRecommendations();
        } else {
          if (msgEl) msgEl.innerHTML = `<span style="color:#EF4444; font-weight:700;">❌ Connection Notice: ${data.error || 'Invalid or Expired Token'}</span>`;
          updateDhanConnectionBadge(false);
        }
      } catch (e) {
        if (msgEl) msgEl.innerHTML = `<span style="color:#EF4444;">❌ Error: ${e.message}</span>`;
      } finally {
        btnConnect.innerText = '⚡ Connect Dhan Live';
      }
    });
  }

  if (btnBuy) btnBuy.addEventListener('click', () => executeDhanOrder('BUY'));
  if (btnSell) btnSell.addEventListener('click', () => executeDhanOrder('SELL'));

  if (btnAiAnalysis) {
    btnAiAnalysis.addEventListener('click', () => {
      const scrip = (document.getElementById('inputCustomAiScrip').value || 'BSE').trim();
      runCustomAiStockAnalysis(scrip);
    });
  }

  // Load live data
  fetchDhanHoldings();
  fetchDhanAiRecommendations();
  fetchDhanFunds();
}

function updateDhanConnectionBadge(isConnected, clientId = '') {
  const badge = document.getElementById('dhanLiveConnectionBadge');
  const dot = document.getElementById('dhanLiveDot');
  const text = document.getElementById('dhanLiveStatusText');
  const topBadge = document.getElementById('statusDhanBadge');
  const topDot = document.getElementById('dhanDot');
  const topText = document.getElementById('dhanStatusText');
  const gatewayBadge = document.getElementById('gatewayDhanBadge');

  const savedId = clientId || localStorage.getItem('dhan_client_id') || '';
  const maskedId = savedId ? (savedId.length > 4 ? savedId.substring(0, 3) + '****' : 'Active') : 'Active';

  if (isConnected) {
    if (badge) {
      badge.style.background = 'rgba(16, 185, 129, 0.15)';
      badge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      badge.style.color = '#10B981';
    }
    if (dot) dot.style.background = '#10B981';
    if (text) text.innerText = `Dhan Live: Active (${maskedId})`;

    if (topText) topText.innerText = `Dhan: Live (${maskedId})`;
    if (topDot) topDot.style.background = '#10B981';
    if (topBadge) {
      topBadge.style.color = '#10B981';
      topBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      topBadge.style.background = 'rgba(16, 185, 129, 0.15)';
    }
    if (gatewayBadge) {
      gatewayBadge.innerText = '● Live Connected';
      gatewayBadge.style.color = '#10B981';
    }
  } else {
    if (badge) {
      badge.style.background = 'rgba(59, 130, 246, 0.15)';
      badge.style.borderColor = 'rgba(59, 130, 246, 0.3)';
      badge.style.color = '#3B82F6';
    }
    if (dot) dot.style.background = '#3B82F6';
    if (text) text.innerText = 'Dhan: Ready to Connect';

    if (topText) topText.innerText = 'Dhan: Ready';
    if (topDot) topDot.style.background = '#64748B';
    if (topBadge) {
      topBadge.style.color = '#94A3B8';
      topBadge.style.borderColor = 'rgba(148, 163, 184, 0.2)';
      topBadge.style.background = 'rgba(148, 163, 184, 0.08)';
    }
    if (gatewayBadge) {
      gatewayBadge.innerText = '● Ready';
      gatewayBadge.style.color = '#64748B';
    }
  }
}

function getDhanAuthHeaders() {
  const cid = localStorage.getItem('dhan_client_id') || '';
  const tok = localStorage.getItem('dhan_access_token') || '';
  const headers = { 'Content-Type': 'application/json' };
  if (cid) headers['x-dhan-client-id'] = cid;
  if (tok) headers['x-dhan-access-token'] = tok;
  return headers;
}

async function executeDhanOrder(action, customSymbol = null, customQty = null) {
  const symbol = (customSymbol || document.getElementById('dhanOrderSymbol').value || 'BSE').trim().toUpperCase();
  const qty = parseInt(customQty || document.getElementById('dhanOrderQty').value) || 1;
  const orderType = document.getElementById('dhanOrderType') ? document.getElementById('dhanOrderType').value : 'MARKET';
  const product = document.getElementById('dhanOrderProduct') ? document.getElementById('dhanOrderProduct').value : 'CNC';

  try {
    const res = await fetch('/api/dhan/place-order', {
      method: 'POST',
      headers: getDhanAuthHeaders(),
      body: JSON.stringify({
        symbol: symbol,
        transaction_type: action,
        quantity: qty,
        order_type: orderType,
        product_type: product
      })
    });
    const data = await res.json();
    if (data.success) {
      alert(`✅ Dhan Order Placed Successfully!\n\nSymbol: ${symbol}\nAction: ${action}\nQty: ${qty}\nBroker Mode: ${data.broker}`);
      fetchDhanHoldings();
      fetchDhanFunds();
    } else {
      alert(`❌ Dhan Order Failed: ${data.error || 'Check parameters'}`);
    }
  } catch (e) {
    alert(`Order execution error: ${e.message}`);
  }
}

async function fetchDhanFunds() {
  try {
    const res = await fetch('/api/dhan/funds', { headers: getDhanAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    const el = document.getElementById('dhanKpiAvailMargin');
    if (el) el.innerText = `₹${(data.avail_margin || 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
  } catch (e) {}
}

async function fetchDhanHoldings() {
  const tbody = document.getElementById('dhanHoldingsTableBody');
  const badge = document.getElementById('dhanPortfolioNetWorthBadge');
  const kpiNetWorth = document.getElementById('dhanKpiNetWorth');
  const kpiInvested = document.getElementById('dhanKpiInvested');
  const kpiTotalPnl = document.getElementById('dhanKpiTotalPnl');
  const kpiTotalPnlPct = document.getElementById('dhanKpiTotalPnlPct');
  const kpiDayPnl = document.getElementById('dhanKpiDayPnl');

  if (!tbody) return;

  try {
    const res = await fetch('/api/portfolio/dhan', { headers: getDhanAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();

    updateDhanConnectionBadge(data.connected);

    if (!data.holdings || data.holdings.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:32px; font-size:12px;">${data.message || 'No live Dhan holdings found. Enter your Client ID & Access Token above.'}</td></tr>`;
      if (badge) badge.innerText = '';
      if (kpiNetWorth) kpiNetWorth.innerText = '₹0.00';
      if (kpiInvested) kpiInvested.innerText = '₹0.00';
      if (kpiTotalPnl) { kpiTotalPnl.innerText = '₹0.00'; kpiTotalPnl.style.color = '#64748B'; }
      if (kpiTotalPnlPct) { kpiTotalPnlPct.innerText = '0.00%'; kpiTotalPnlPct.style.color = '#64748B'; }
      if (kpiDayPnl) kpiDayPnl.innerText = '₹0.00';
      return;
    }

    if (kpiNetWorth) kpiNetWorth.innerText = `₹${data.net_worth.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    if (kpiInvested) kpiInvested.innerText = `₹${data.invested_value.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    
    if (kpiTotalPnl) {
      const isUp = data.total_pnl >= 0;
      kpiTotalPnl.innerText = `${isUp ? '+' : ''}₹${data.total_pnl.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
      kpiTotalPnl.style.color = isUp ? '#10B981' : '#EF4444';
    }
    if (kpiTotalPnlPct) {
      const isUp = data.total_pnl_pct >= 0;
      kpiTotalPnlPct.innerText = `${isUp ? '+' : ''}${data.total_pnl_pct.toFixed(2)}% Overall`;
      kpiTotalPnlPct.style.color = isUp ? '#10B981' : '#EF4444';
    }
    if (kpiDayPnl) {
      const isUp = data.day_pnl >= 0;
      kpiDayPnl.innerText = `${isUp ? '+' : ''}₹${data.day_pnl.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    }

    if (badge) {
      badge.innerText = `Total Valuation: ₹${data.net_worth.toLocaleString(undefined, {minimumFractionDigits:2})}`;
    }

    tbody.innerHTML = data.holdings.map(h => {
      const isUp = (h.pnl || 0) >= 0;
      return `
        <tr>
          <td><b style="color:#0F172A;">${h.symbol}</b></td>
          <td>${h.name}</td>
          <td><b>${h.qty}</b></td>
          <td>₹${h.avg_price.toFixed(2)}</td>
          <td style="font-weight:700; color:${isUp ? '#10B981' : '#EF4444'};">₹${h.cmp.toFixed(2)}</td>
          <td class="${isUp ? 'val-green' : 'val-red'}" style="font-weight:800;">${isUp ? '+' : ''}₹${h.pnl.toFixed(2)}</td>
          <td class="${isUp ? 'val-green' : 'val-red'}" style="font-weight:700;">${isUp ? '+' : ''}${h.pnl_pct.toFixed(2)}%</td>
          <td>
            <div style="display:flex; gap:4px;">
              <button style="background:#10B981; color:#FFF; border:none; padding:3px 8px; border-radius:4px; font-weight:700; font-size:10px; cursor:pointer;" onclick="executeDhanOrder('BUY', '${h.symbol}', 5)">
                + Buy More
              </button>
              <button style="background:#EF4444; color:#FFF; border:none; padding:3px 8px; border-radius:4px; font-weight:700; font-size:10px; cursor:pointer;" onclick="executeDhanOrder('SELL', '${h.symbol}', ${h.qty})">
                Exit
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {}
}

// --- AI Stock Recommendations & Future Outlook for Portfolio Shares ---
async function fetchDhanAiRecommendations() {
  const container = document.getElementById('dhanAiRecommendationsList');
  if (!container) return;

  try {
    const res = await fetch('/api/dhan/ai-recommendations', { headers: getDhanAuthHeaders() });
    if (!res.ok) return;
    const recs = await res.json();
    if (!Array.isArray(recs) || recs.length === 0) {
      container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; padding: 28px 16px; color: var(--text-muted); background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 8px; font-size: 11px;">📊 No Dhan portfolio holdings found to analyze. Connect your active Dhan live account to generate AI recommendations for your shares.</div>`;
      return;
    }

    container.innerHTML = recs.map(r => {
      const isSell = r.action === 'EXIT' || r.action === 'SELL_PARTIAL';
      const badgeBg = isSell ? '#FEF2F2' : '#ECFDF5';
      const badgeColor = isSell ? '#EF4444' : '#10B981';
      const badgeBorder = isSell ? '#FECACA' : '#A7F3D0';

      return `
        <div style="background:#FFFFFF; border:1px solid var(--border-card); border-radius:8px; padding:14px; display:flex; flex-direction:column; justify-content:space-between; gap:10px; box-shadow:var(--shadow-sm);">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
              <div>
                <div style="font-size:14px; font-weight:800; color:#0F172A; font-family:var(--font-mono);">${r.symbol}</div>
                <div style="font-size:10px; color:var(--text-muted);">${r.name} • ${r.qty_held || 1} shares held</div>
              </div>
              <span style="background:${badgeBg}; color:${badgeColor}; border:1px solid ${badgeBorder}; font-size:10px; font-weight:800; padding:2px 8px; border-radius:12px;">
                ${r.rating}
              </span>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-top:10px; font-size:11px; background:#F8FAFC; padding:8px; border-radius:6px;">
              <div>
                <span style="color:var(--text-muted); font-size:9px; font-weight:700;">LIVE CMP:</span>
                <b style="color:#0F172A; font-family:var(--font-mono);">₹${Number(r.cmp).toFixed(2)}</b>
              </div>
              <div>
                <span style="color:var(--text-muted); font-size:9px; font-weight:700;">BUY AVG:</span>
                <b style="color:#64748B; font-family:var(--font-mono);">₹${Number(r.avg_buy_price || r.cmp).toFixed(2)}</b>
              </div>
              <div>
                <span style="color:var(--text-muted); font-size:9px; font-weight:700;">TARGET:</span>
                <b style="color:#10B981; font-family:var(--font-mono);">₹${Number(r.target_1).toFixed(2)} - ₹${Number(r.target_2).toFixed(2)}</b>
              </div>
              <div>
                <span style="color:var(--text-muted); font-size:9px; font-weight:700;">STOP LOSS:</span>
                <b style="color:#EF4444; font-family:var(--font-mono);">₹${Number(r.stop_loss).toFixed(2)}</b>
              </div>
            </div>

            <div style="font-size:10px; color:#475569; margin-top:8px; line-height:1.4;">
              <b>AI Advisory & Technical Catalyst:</b> ${r.catalyst}
            </div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #F1F5F9; padding-top:8px;">
            <span style="font-size:9px; font-weight:700; color:#2563EB;">Score: ${r.technical_score}</span>
            <div style="display:flex; gap:6px;">
              <button style="background:#10B981; color:#FFF; border:none; padding:5px 10px; border-radius:4px; font-size:10px; font-weight:800; cursor:pointer;" onclick="executeDhanOrder('BUY', '${r.symbol}', 5)">
                + Buy / Add
              </button>
              <button style="background:#EF4444; color:#FFF; border:none; padding:5px 10px; border-radius:4px; font-size:10px; font-weight:800; cursor:pointer;" onclick="executeDhanOrder('SELL', '${r.symbol}', ${r.qty_held || 1})">
                Exit
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {}
}

async function runCustomAiStockAnalysis(symbol) {
  const resultCard = document.getElementById('aiScripAnalysisResultCard');
  if (!resultCard) return;

  resultCard.style.display = 'block';
  resultCard.innerHTML = `<div style="text-align:center; padding:16px; color:var(--text-muted); font-size:11px;">🤖 Running Gemini AI Multi-Factor Analysis for <b>${symbol}</b>...</div>`;

  try {
    const res = await fetch('/api/dhan/analyze-stock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: symbol })
    });
    const data = await res.json();

    resultCard.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; border-bottom:1px solid var(--border-subtle); padding-bottom:10px; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px; font-weight:800; color:#0F172A; font-family:var(--font-mono);">${data.symbol}</span>
          <span style="background:#ECFDF5; color:#10B981; font-weight:800; font-size:10px; padding:2px 8px; border-radius:10px;">${data.rating}</span>
          <span style="font-size:13px; font-weight:800; color:#0F172A; font-family:var(--font-mono);">Live CMP: ₹${data.cmp}</span>
        </div>
        <button style="background:#10B981; color:#FFF; border:none; padding:6px 14px; border-radius:4px; font-size:11px; font-weight:800; cursor:pointer;" onclick="executeDhanOrder('BUY', '${data.symbol}', 10)">
          ⚡ Place Buy Order on Dhan
        </button>
      </div>

      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom:10px; font-size:11px;">
        <div style="background:#F8FAFC; padding:8px; border-radius:6px;">
          <div style="color:var(--text-muted); font-size:9px; font-weight:700;">ACCUMULATION ZONE</div>
          <div style="font-weight:800; color:#2563EB;">${data.buy_range}</div>
        </div>
        <div style="background:#F8FAFC; padding:8px; border-radius:6px;">
          <div style="color:var(--text-muted); font-size:9px; font-weight:700;">TARGET 1 (SWING)</div>
          <div style="font-weight:800; color:#10B981;">₹${data.target_1}</div>
        </div>
        <div style="background:#F8FAFC; padding:8px; border-radius:6px;">
          <div style="color:var(--text-muted); font-size:9px; font-weight:700;">TARGET 2 (POSITIONAL)</div>
          <div style="font-weight:800; color:#10B981;">₹${data.target_2}</div>
        </div>
        <div style="background:#F8FAFC; padding:8px; border-radius:6px;">
          <div style="color:var(--text-muted); font-size:9px; font-weight:700;">PROTECTION STOP LOSS</div>
          <div style="font-weight:800; color:#EF4444;">₹${data.stop_loss}</div>
        </div>
      </div>

      <div style="font-size:11px; line-height:1.5; color:#334155; background:#EFF6FF; border-left:3px solid #2563EB; padding:8px 12px; border-radius:4px;">
        <b>AI Future Verdict & Technical Outlook:</b> ${data.ai_verdict}
      </div>
    `;
  } catch (e) {
    resultCard.innerHTML = `<div style="color:#EF4444; font-size:11px;">Analysis error: ${e.message}</div>`;
  }
}

// --- Shoonya Single-Line Token Feeder ---
function initQuickShoonyaTokenFeeder() {
  const btn = document.getElementById('btnQuickFeedToken');
  const input = document.getElementById('inputQuickShoonyaToken');
  const feedback = document.getElementById('tokenFeedFeedback');
  if (!btn || !input) return;

  btn.addEventListener('click', async () => {
    const val = input.value.trim();
    if (!val) {
      alert('Please paste Shoonya Access Token (64-char hex) or Auth code.');
      return;
    }

    btn.innerText = 'Connecting...';
    try {
      const res = await fetch('/api/shoonya/feed-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token_or_url: val })
      });
      const data = await res.json();
      if (data.success) {
        if (feedback) feedback.innerText = '✅ Synced!';
        alert('✅ ' + (data.message || 'Shoonya Connected Successfully!'));
        input.value = '';
        fetchShoonyaStatus();
      } else {
        alert('Notice: ' + (data.error || 'Check token expiration'));
      }
    } catch (e) {
      alert('❌ Error: ' + e.message);
    } finally {
      btn.innerText = '⚡ Sync Shoonya';
    }
  });
}

async function fetchShoonyaStatus() {
  try {
    const res = await fetch('/api/shoonya/status');
    if (!res.ok) return;
    const data = await res.json();
    const badgeText = document.getElementById('shoonyaStatusText');
    const topBadge = document.getElementById('statusShoonyaBadge');
    const topDot = document.getElementById('shoonyaDot');
    const gatewayBadge = document.getElementById('gatewayShoonyaBadge');

    if (badgeText) {
      const maskedUid = data.uid ? (data.uid.length > 4 ? data.uid.substring(0, 3) + '****' : 'Live') : 'Live';
      badgeText.innerText = data.is_connected ? `Shoonya: Live (${maskedUid})` : 'Shoonya: Ready';
    }
    if (topDot) {
      topDot.style.background = data.is_connected ? '#10B981' : '#64748B';
    }
    if (topBadge) {
      topBadge.style.color = data.is_connected ? '#10B981' : '#94A3B8';
      topBadge.style.borderColor = data.is_connected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(148, 163, 184, 0.2)';
      topBadge.style.background = data.is_connected ? 'rgba(16, 185, 129, 0.15)' : 'rgba(148, 163, 184, 0.08)';
    }
    if (gatewayBadge) {
      gatewayBadge.innerText = data.is_connected ? '● Live Connected' : '● Ready';
      gatewayBadge.style.color = data.is_connected ? '#10B981' : '#64748B';
    }
  } catch (e) {}
}

// --- Broker Login & Connectivity Gateway ---
function initBrokerLoginGateway() {
  const btnShoonya = document.getElementById('btnGatewaySyncShoonya');
  const inputShoonya = document.getElementById('gatewayInputShoonyaToken');
  const msgShoonya = document.getElementById('gatewayShoonyaMsg');

  const btnDhan = document.getElementById('btnGatewaySyncDhan');
  const inputDhanId = document.getElementById('gatewayInputDhanClientId');
  const inputDhanTok = document.getElementById('gatewayInputDhanToken');
  const msgDhan = document.getElementById('gatewayDhanMsg');
  const gatewayDhanBadge = document.getElementById('gatewayDhanBadge');

  // Load saved Dhan credentials
  const savedDhanId = localStorage.getItem('dhan_client_id') || '';
  const savedDhanTok = localStorage.getItem('dhan_access_token') || '';
  if (inputDhanId && savedDhanId) inputDhanId.value = savedDhanId;
  if (inputDhanTok && savedDhanTok) inputDhanTok.value = savedDhanTok;

  if (btnShoonya && inputShoonya) {
    btnShoonya.addEventListener('click', async () => {
      const val = inputShoonya.value.trim();
      if (!val) {
        if (msgShoonya) msgShoonya.innerHTML = '<span style="color:#EF4444;">Please paste Shoonya token or auth code.</span>';
        return;
      }
      btnShoonya.innerText = 'Verifying with VPS & Supabase...';
      try {
        const res = await fetch('/api/shoonya/feed-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token_or_url: val })
        });
        const data = await res.json();
        if (data.success) {
          if (msgShoonya) msgShoonya.innerHTML = `<span style="color:#10B981; font-weight:700;">✅ ${data.message || 'Shoonya Connected!'}</span>`;
          inputShoonya.value = '';
          fetchShoonyaStatus();
        } else {
          if (msgShoonya) msgShoonya.innerHTML = `<span style="color:#EF4444;">❌ ${data.error || 'Authentication error'}</span>`;
        }
      } catch (e) {
        if (msgShoonya) msgShoonya.innerHTML = `<span style="color:#EF4444;">❌ Error: ${e.message}</span>`;
      } finally {
        btnShoonya.innerText = '⚡ Sync & Verify Shoonya Session';
      }
    });
  }

  if (btnDhan && inputDhanId && inputDhanTok) {
    btnDhan.addEventListener('click', async () => {
      const clientId = inputDhanId.value.trim();
      const token = inputDhanTok.value.trim();
      if (!clientId || !token) {
        if (msgDhan) msgDhan.innerHTML = '<span style="color:#EF4444;">Please provide both Dhan Client ID and Access Token.</span>';
        return;
      }
      btnDhan.innerText = 'Linking & Saving...';
      try {
        const res = await fetch('/api/dhan/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: clientId, access_token: token })
        });
        const data = await res.json();
        if (data.connected) {
          localStorage.setItem('dhan_client_id', clientId);
          localStorage.setItem('dhan_access_token', token);
          if (msgDhan) msgDhan.innerHTML = `<span style="color:#10B981; font-weight:700;">✅ Dhan Live Account Linked & Saved!</span>`;
          if (gatewayDhanBadge) {
            gatewayDhanBadge.innerText = '● Live Connected';
            gatewayDhanBadge.style.color = '#10B981';
            gatewayDhanBadge.style.background = '#ECFDF5';
          }
          fetchDhanHoldings();
          fetchDhanFunds();
          fetchDhanAiRecommendations();
        } else {
          if (msgDhan) msgDhan.innerHTML = `<span style="color:#EF4444;">❌ Notice: ${data.error || 'Invalid token'}</span>`;
        }
      } catch (e) {
        if (msgDhan) msgDhan.innerHTML = `<span style="color:#EF4444;">❌ Error: ${e.message}</span>`;
      } finally {
        btnDhan.innerText = '⚡ Link & Save Dhan Live Account';
      }
    });
  }
}
