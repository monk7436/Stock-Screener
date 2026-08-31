/**
 * Stock Screener Frontend Controller
 * Handles SSE live streaming, dynamic instant re-filtering, ranking calculations, Chart.js modals, and CSV export.
 */

// Application State
const state = {
  market: 'nse', // 'nse' or 'us'
  universe: 'nifty_50', // 'nifty_50', 'bank_nifty', 'nifty_100', 'nifty_500', 'sp_500_top', 'nyse_top', 'custom'
  universesData: null,
  allScanned: [],
  filtered: [],
  isScanning: false,
  eventSource: null,
  sortColumn: 'rank_score',
  sortDirection: 'desc',
  searchQuery: '',
  priceChartInstance: null,
  rsiChartInstance: null
};

// Universe definitions fallback if API offline
const DEFAULT_PRESETS = {
  nse: [
    { id: 'nifty_50', name: 'Nifty 50 (Bluechips)' },
    { id: 'bank_nifty', name: 'Bank Nifty (Banking)' },
    { id: 'nifty_100', name: 'Nifty 100 (Large Cap)' },
    { id: 'nifty_500', name: 'Nifty 500 (Broad)' },
    { id: 'custom', name: 'Custom Tickers' }
  ],
  us: [
    { id: 'sp_500_top', name: 'S&P 100 / Large Cap' },
    { id: 'nyse_top', name: 'NYSE Blue Chips' },
    { id: 'custom', name: 'Custom Tickers' }
  ]
};

// Initialize Application
document.addEventListener('DOMContentLoaded', async () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  
  initEventListeners();
  await loadUniverses();
  renderUniversePresets();
  syncSliderInputs();
});

// Load Universe Presets from API
async function loadUniverses() {
  try {
    const res = await fetch('/api/universes');
    if (res.ok) {
      state.universesData = await res.json();
    }
  } catch (e) {
    console.warn('Using default universe presets:', e);
  }
}

// Render Universe Preset Buttons
function renderUniversePresets() {
  const container = document.getElementById('universePresets');
  container.innerHTML = '';

  const presets = (state.universesData && state.universesData.markets[state.market])
    ? Object.entries(state.universesData.markets[state.market].presets).map(([id, info]) => ({ id, name: info.name, count: info.count }))
    : DEFAULT_PRESETS[state.market];

  // Add custom option if not present
  const allPresets = [...presets];
  if (!allPresets.some(p => p.id === 'custom')) {
    allPresets.push({ id: 'custom', name: 'Custom Tickers' });
  }

  allPresets.forEach(preset => {
    const btn = document.createElement('button');
    const isSelected = state.universe === preset.id;
    btn.className = `px-3 py-1.5 rounded-lg text-xs font-semibold transition border ${
      isSelected
        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm'
        : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
    }`;
    btn.innerHTML = preset.count ? `${preset.name} <span class="opacity-60 text-[10px]">(${preset.count})</span>` : preset.name;
    
    btn.addEventListener('click', () => {
      state.universe = preset.id;
      renderUniversePresets();
      
      const customWrapper = document.getElementById('customTickersWrapper');
      if (preset.id === 'custom') {
        customWrapper.classList.remove('hidden');
      } else {
        customWrapper.classList.add('hidden');
      }
      
      document.getElementById('statUniverseText').innerText = preset.name;
    });
    
    container.appendChild(btn);
  });
}

// Attach DOM Event Listeners
function initEventListeners() {
  // Market Toggles
  document.getElementById('marketNseBtn').addEventListener('click', () => setMarket('nse'));
  document.getElementById('marketUsBtn').addEventListener('click', () => setMarket('us'));

  // Scan Buttons
  document.getElementById('startScanBtn').addEventListener('click', startScan);
  document.getElementById('stopScanBtn').addEventListener('click', stopScan);
  document.getElementById('resetFiltersBtn').addEventListener('click', resetFilters);
  document.getElementById('exportCsvBtn').addEventListener('click', exportToCsv);

  // Table Search
  document.getElementById('tableSearchInput').addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    applyFiltersAndRender(false);
  });

  // Table Header Sort
  document.querySelectorAll('#screenerTable th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.getAttribute('data-sort');
      if (state.sortColumn === col) {
        state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortColumn = col;
        state.sortDirection = col === 'rank' || col === 'trailing_pe' ? 'asc' : 'desc';
      }
      applyFiltersAndRender(false);
    });
  });

  // Ranking Weights Toggle Panel
  const toggleWeightsBtn = document.getElementById('toggleWeightsBtn');
  const weightsSettingsPanel = document.getElementById('weightsSettingsPanel');
  toggleWeightsBtn.addEventListener('click', () => {
    weightsSettingsPanel.classList.toggle('hidden');
  });

  // Weights Sliders
  ['volWeight', 'rsiWeight', 'peWeight'].forEach(key => {
    const slider = document.getElementById(`${key}Slider`);
    const display = document.getElementById(`${key}Display`);
    slider.addEventListener('input', (e) => {
      display.innerText = `${e.target.value}%`;
      recalculateRankScoresAndRender();
    });
  });

  // Modal Close
  document.getElementById('closeModalBtn').addEventListener('click', closeChartModal);
  document.getElementById('chartModal').addEventListener('click', (e) => {
    if (e.target.id === 'chartModal') closeChartModal();
  });
}

function setMarket(market) {
  state.market = market;
  const nseBtn = document.getElementById('marketNseBtn');
  const usBtn = document.getElementById('marketUsBtn');

  if (market === 'nse') {
    state.universe = 'nifty_50';
    nseBtn.className = 'flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 transition';
    usBtn.className = 'flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition';
  } else {
    state.universe = 'sp_500_top';
    usBtn.className = 'flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 transition';
    nseBtn.className = 'flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition';
  }

  document.getElementById('customTickersWrapper').classList.add('hidden');
  renderUniversePresets();
}

// Synchronize Sliders and Inputs + Trigger Instant Client-side Re-filtering
function syncSliderInputs() {
  // P/E Max Slider <-> Number Input
  const peSlider = document.getElementById('peMaxSlider');
  const peInput = document.getElementById('peMaxInput');
  const peDisplay = document.getElementById('peSliderDisplay');
  const peMinInput = document.getElementById('peMinInput');
  const includeNoPeCheckbox = document.getElementById('includeNoPeCheckbox');

  peSlider.addEventListener('input', (e) => {
    peInput.value = e.target.value;
    peDisplay.innerText = `≤ ${e.target.value}`;
    applyFiltersAndRender(false);
  });
  peInput.addEventListener('input', (e) => {
    peSlider.value = e.target.value;
    peDisplay.innerText = `≤ ${e.target.value}`;
    applyFiltersAndRender(false);
  });
  peMinInput.addEventListener('input', () => applyFiltersAndRender(false));
  includeNoPeCheckbox.addEventListener('change', () => applyFiltersAndRender(false));

  // Volume Min Slider <-> Number Input
  const volSlider = document.getElementById('volMinSlider');
  const volInput = document.getElementById('volMinInput');
  const volDisplay = document.getElementById('volSliderDisplay');

  volSlider.addEventListener('input', (e) => {
    volInput.value = parseFloat(e.target.value).toFixed(1);
    volDisplay.innerText = `≥ ${volInput.value}x 20d Avg`;
    applyFiltersAndRender(false);
  });
  volInput.addEventListener('input', (e) => {
    volSlider.value = e.target.value;
    volDisplay.innerText = `≥ ${e.target.value}x 20d Avg`;
    applyFiltersAndRender(false);
  });

  // RSI Min Slider <-> Number Input
  const rsiSlider = document.getElementById('rsiMinSlider');
  const rsiInput = document.getElementById('rsiMinInput');
  const rsiDisplay = document.getElementById('rsiSliderDisplay');
  const rsiMaxInput = document.getElementById('rsiMaxInput');

  rsiSlider.addEventListener('input', (e) => {
    rsiInput.value = e.target.value;
    rsiDisplay.innerText = `≥ ${e.target.value} (${e.target.value >= 50 ? 'Bullish' : 'Oversold'})`;
    applyFiltersAndRender(false);
  });
  rsiInput.addEventListener('input', (e) => {
    rsiSlider.value = e.target.value;
    rsiDisplay.innerText = `≥ ${e.target.value}`;
    applyFiltersAndRender(false);
  });
  rsiMaxInput.addEventListener('input', () => applyFiltersAndRender(false));
}

// Start Live Screener Scan via SSE
function startScan() {
  if (state.isScanning) return;

  state.isScanning = true;
  state.allScanned = [];
  state.filtered = [];

  // Update UI State
  updateScanUI(true);
  
  const peMax = document.getElementById('peMaxInput').value;
  const peMin = document.getElementById('peMinInput').value;
  const includeNoPe = document.getElementById('includeNoPeCheckbox').checked;
  const volMin = document.getElementById('volMinInput').value;
  const rsiMin = document.getElementById('rsiMinInput').value;
  const rsiMax = document.getElementById('rsiMaxInput').value;
  const customTickers = document.getElementById('customTickersInput').value;
  const volWeight = parseFloat(document.getElementById('volWeightSlider').value) / 100.0;
  const rsiWeight = parseFloat(document.getElementById('rsiWeightSlider').value) / 100.0;
  const peWeight = parseFloat(document.getElementById('peWeightSlider').value) / 100.0;

  const params = new URLSearchParams({
    market: state.market,
    universe: state.universe,
    max_pe: peMax,
    min_pe: peMin,
    include_no_pe: includeNoPe ? 'true' : 'false',
    min_volume_ratio: volMin,
    min_rsi: rsiMin,
    max_rsi: rsiMax,
    vol_weight: volWeight,
    rsi_weight: rsiWeight,
    pe_weight: peWeight
  });

  if (state.universe === 'custom' && customTickers) {
    params.set('custom_tickers', customTickers);
  }

  // Open Server-Sent Events stream
  const url = `/api/scan/stream?${params.toString()}`;
  if (state.eventSource) {
    state.eventSource.close();
  }

  state.eventSource = new EventSource(url);

  state.eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleScanEvent(data);
    } catch (e) {
      console.error('Error parsing SSE event data:', e);
    }
  };

  state.eventSource.onerror = (err) => {
    console.error('SSE connection error:', err);
    stopScan();
    document.getElementById('statusText').innerText = 'Connection Error';
  };
}

function handleScanEvent(data) {
  if (data.type === 'start') {
    document.getElementById('progressMessage').innerText = data.message;
    document.getElementById('progressBarFill').style.width = '5%';
    document.getElementById('progressPercent').innerText = '0%';
  } else if (data.type === 'progress' || data.type === 'complete') {
    state.allScanned = data.all_scanned || [];
    
    const pct = data.total > 0 ? Math.round((data.scanned / data.total) * 100) : 100;
    document.getElementById('progressBarFill').style.width = `${pct}%`;
    document.getElementById('progressPercent').innerText = `${pct}%`;
    document.getElementById('progressMessage').innerText = data.message || `Scanned ${data.scanned}/${data.total}`;
    
    document.getElementById('statScanned').innerText = data.scanned;

    applyFiltersAndRender(true);

    if (data.type === 'complete') {
      stopScan();
      document.getElementById('statusText').innerText = `Scan Complete (${data.matched_count} matches)`;
    }
  } else if (data.type === 'error') {
    alert(`Scan error: ${data.message}`);
    stopScan();
  }
}

function stopScan() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  state.isScanning = false;
  updateScanUI(false);
}

function updateScanUI(scanning) {
  const startBtn = document.getElementById('startScanBtn');
  const stopBtn = document.getElementById('stopScanBtn');
  const progressCard = document.getElementById('scanProgressCard');
  const radar = document.getElementById('statusRadar');
  const statusText = document.getElementById('statusText');

  if (scanning) {
    startBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    stopBtn.classList.add('flex');
    progressCard.classList.remove('hidden');
    radar.className = 'pulse-radar active';
    statusText.innerText = 'Scanning Live...';
  } else {
    startBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    stopBtn.classList.remove('flex');
    radar.className = 'pulse-radar idle';
  }
}

// Dynamic Client-side Filter & Ranking Engine
function applyFiltersAndRender(isFromStream = false) {
  const peMax = parseFloat(document.getElementById('peMaxInput').value) || 20.0;
  const peMin = parseFloat(document.getElementById('peMinInput').value) || 0.0;
  const includeNoPe = document.getElementById('includeNoPeCheckbox').checked;
  const volMin = parseFloat(document.getElementById('volMinInput').value) || 2.0;
  const rsiMin = parseFloat(document.getElementById('rsiMinInput').value) || 50.0;
  const rsiMax = parseFloat(document.getElementById('rsiMaxInput').value) || 100.0;

  // Filter all currently scanned stocks
  state.filtered = state.allScanned.filter(stock => {
    // Volume Filter
    if (stock.volume_ratio < volMin) return false;

    // RSI Filter
    if (stock.rsi === null || stock.rsi === undefined) return false;
    if (stock.rsi < rsiMin || stock.rsi > rsiMax) return false;

    // P/E Filter
    if (stock.trailing_pe === null || stock.trailing_pe <= 0) {
      if (!includeNoPe) return false;
    } else {
      if (stock.trailing_pe < peMin || stock.trailing_pe > peMax) return false;
    }

    // Search Query
    if (state.searchQuery) {
      const sym = (stock.symbol || '').toLowerCase();
      const name = (stock.name || '').toLowerCase();
      if (!sym.includes(state.searchQuery) && !name.includes(state.searchQuery)) {
        return false;
      }
    }

    return true;
  });

  // Sort Filtered Results
  sortFilteredResults();

  // Update Top KPIs
  updateKpiMetrics();

  // Render Table Rows
  renderTable();
}

function recalculateRankScoresAndRender() {
  const volWeight = parseFloat(document.getElementById('volWeightSlider').value) / 100.0;
  const rsiWeight = parseFloat(document.getElementById('rsiWeightSlider').value) / 100.0;
  const peWeight = parseFloat(document.getElementById('peWeightSlider').value) / 100.0;

  // Recalculate rank_score on each stock
  state.allScanned.forEach(stock => {
    // Vol Score (0-100)
    const volScore = stock.volume_ratio <= 0 ? 0 : Math.min(Math.max((stock.volume_ratio / 4.0) * 100, 0), 100);
    
    // RSI Score (0-100)
    let rsiScore = 50;
    if (stock.rsi !== null && stock.rsi !== undefined) {
      if (stock.rsi < 30) rsiScore = Math.max((stock.rsi / 30) * 25, 0);
      else if (stock.rsi < 50) rsiScore = 25 + ((stock.rsi - 30) / 20) * 25;
      else if (stock.rsi <= 80) rsiScore = 50 + ((stock.rsi - 50) / 30) * 50;
      else rsiScore = Math.max(100 - (stock.rsi - 80) * 2, 70);
    }

    // PE Score (0-100)
    let peScore = 30;
    if (stock.trailing_pe !== null && stock.trailing_pe > 0) {
      if (stock.trailing_pe <= 10) peScore = 100 - (stock.trailing_pe / 10) * 10;
      else if (stock.trailing_pe <= 20) peScore = 90 - ((stock.trailing_pe - 10) / 10) * 30;
      else if (stock.trailing_pe <= 40) peScore = 60 - ((stock.trailing_pe - 20) / 20) * 40;
      else peScore = Math.max(20 - ((stock.trailing_pe - 40) / 40) * 20, 0);
    }

    stock.rank_score = Math.round(((volScore * volWeight) + (rsiScore * rsiWeight) + (peScore * peWeight)) * 10) / 10;
  });

  applyFiltersAndRender(false);
}

function sortFilteredResults() {
  const col = state.sortColumn;
  const dir = state.sortDirection === 'asc' ? 1 : -1;

  state.filtered.sort((a, b) => {
    let valA = a[col];
    let valB = b[col];

    if (valA === null || valA === undefined) valA = dir === 1 ? Infinity : -Infinity;
    if (valB === null || valB === undefined) valB = dir === 1 ? Infinity : -Infinity;

    if (typeof valA === 'string') {
      return dir * valA.localeCompare(valB);
    }
    return dir * (valA - valB);
  });

  // Assign fresh integer ranks
  state.filtered.forEach((item, index) => {
    item.rank = index + 1;
  });
}

function updateKpiMetrics() {
  const totalScanned = state.allScanned.length;
  const matchCount = state.filtered.length;

  document.getElementById('statScanned').innerText = totalScanned;
  document.getElementById('statMatches').innerText = matchCount;
  document.getElementById('tableMatchCountBadge').innerText = `${matchCount} matched`;

  const hitRate = totalScanned > 0 ? Math.round((matchCount / totalScanned) * 100) : 0;
  document.getElementById('statMatchRate').innerText = `${hitRate}% hit rate`;

  if (matchCount > 0) {
    const avgVol = (state.filtered.reduce((sum, s) => sum + (s.volume_ratio || 0), 0) / matchCount).toFixed(2);
    document.getElementById('statAvgVol').innerText = `${avgVol}x`;

    const topStock = state.filtered[0];
    document.getElementById('statTopRanked').innerText = topStock.symbol;
    document.getElementById('statTopScore').innerText = `Score: ${topStock.rank_score}`;
  } else {
    document.getElementById('statAvgVol').innerText = '0.0x';
    document.getElementById('statTopRanked').innerText = '---';
    document.getElementById('statTopScore').innerText = 'Score: --';
  }
}

// Render Data Table HTML
function renderTable() {
  const tbody = document.getElementById('tableBody');
  
  if (state.filtered.length === 0) {
    tbody.innerHTML = `
      <tr id="emptyRow">
        <td colspan="10" class="text-center py-12 text-slate-500">
          <div class="flex flex-col items-center justify-center space-y-2">
            <i data-lucide="filter-x" class="w-8 h-8 text-slate-600 mb-1"></i>
            <p class="text-sm font-medium text-slate-400">No stocks match your current filter parameters.</p>
            <p class="text-xs text-slate-500">Try relaxing the P/E maximum or lowering the Volume Spike threshold.</p>
          </div>
        </td>
      </tr>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  const rowsHtml = state.filtered.map(stock => {
    const currSym = stock.currency === 'INR' ? '₹' : '$';
    const isGain = (stock.change_1d_pct || 0) >= 0;
    const changeClass = isGain ? 'text-emerald-400' : 'text-rose-400';
    const changeSign = isGain ? '+' : '';

    // Rank Badge
    let rankBadge = `<span class="font-mono text-slate-400 font-bold">${stock.rank}</span>`;
    if (stock.rank === 1) rankBadge = `<span class="badge badge-rank-1">🥇 #1</span>`;
    else if (stock.rank === 2) rankBadge = `<span class="badge badge-rank-2">🥈 #2</span>`;
    else if (stock.rank === 3) rankBadge = `<span class="badge badge-rank-3">🥉 #3</span>`;

    // PE Badge
    const peVal = stock.trailing_pe !== null && stock.trailing_pe !== undefined
      ? `${stock.trailing_pe.toFixed(1)}`
      : '<span class="text-slate-500 italic text-xs">N/A</span>';

    // RSI Color Gauge
    const rsiVal = stock.rsi !== null && stock.rsi !== undefined ? stock.rsi.toFixed(1) : '--';
    let rsiColor = '#10b981'; // Green
    if (stock.rsi >= 70) rsiColor = '#f59e0b'; // Overbought Orange
    else if (stock.rsi <= 35) rsiColor = '#06b6d4'; // Cyan oversold
    const rsiPercent = stock.rsi ? Math.min(Math.max(stock.rsi, 0), 100) : 50;

    // Volume Spike Badge
    const volRatioFormatted = (stock.volume_ratio || 0).toFixed(2);
    let volBadgeClass = 'badge-cyan';
    if (stock.volume_ratio >= 3.0) volBadgeClass = 'badge-green';
    else if (stock.volume_ratio < 1.5) volBadgeClass = 'badge-orange';

    return `
      <tr class="hover:bg-slate-800/50 transition">
        <td class="text-center font-semibold">${rankBadge}</td>
        <td>
          <span class="font-mono font-bold text-white tracking-wide">${stock.symbol}</span>
        </td>
        <td>
          <div class="font-medium text-slate-200 text-xs">${stock.name || stock.symbol}</div>
          <div class="text-[11px] text-slate-500">${stock.sector || 'General'}</div>
        </td>
        <td class="text-right font-mono font-semibold text-slate-100">
          ${currSym}${Number(stock.current_price).toLocaleString()}
        </td>
        <td class="text-right font-mono text-xs font-semibold ${changeClass}">
          ${changeSign}${stock.change_1d_pct}%
        </td>
        <td class="text-right font-mono text-xs font-bold text-cyan-400">
          ${peVal}
        </td>
        <td class="text-right">
          <span class="badge ${volBadgeClass} font-mono">
            ⚡ ${volRatioFormatted}x
          </span>
        </td>
        <td class="text-center">
          <div class="inline-flex flex-col items-center">
            <span class="font-mono text-xs font-bold" style="color: ${rsiColor}">${rsiVal}</span>
            <div class="rsi-bar-container mt-1">
              <div class="rsi-bar-fill" style="width: ${rsiPercent}%; background-color: ${rsiColor}"></div>
            </div>
          </div>
        </td>
        <td class="text-right font-mono font-bold text-amber-400">
          ${stock.rank_score}
        </td>
        <td class="text-center">
          <button onclick="openChartModal('${stock.symbol}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-500/20 hover:text-cyan-400 text-slate-300 text-xs font-medium border border-slate-700 transition inline-flex items-center space-x-1">
            <i data-lucide="line-chart" class="w-3.5 h-3.5"></i>
            <span>Chart</span>
          </button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.innerHTML = rowsHtml;
  if (window.lucide) lucide.createIcons();
}

// Reset Filters to Standard Defaults
function resetFilters() {
  document.getElementById('peMaxSlider').value = 20;
  document.getElementById('peMaxInput').value = 20;
  document.getElementById('peSliderDisplay').innerText = '≤ 20';
  document.getElementById('peMinInput').value = 0;
  document.getElementById('includeNoPeCheckbox').checked = false;

  document.getElementById('volMinSlider').value = 2.0;
  document.getElementById('volMinInput').value = '2.0';
  document.getElementById('volSliderDisplay').innerText = '≥ 2.0x 20d Avg';

  document.getElementById('rsiMinSlider').value = 50;
  document.getElementById('rsiMinInput').value = 50;
  document.getElementById('rsiSliderDisplay').innerText = '≥ 50 (Bullish)';
  document.getElementById('rsiMaxInput').value = 100;

  document.getElementById('volWeightSlider').value = 45;
  document.getElementById('volWeightDisplay').innerText = '45%';
  document.getElementById('rsiWeightSlider').value = 35;
  document.getElementById('rsiWeightDisplay').innerText = '35%';
  document.getElementById('peWeightSlider').value = 20;
  document.getElementById('peWeightDisplay').innerText = '20%';

  document.getElementById('tableSearchInput').value = '';
  state.searchQuery = '';

  recalculateRankScoresAndRender();
}

// Open Interactive Candlestick / RSI Chart Modal
async function openChartModal(symbol) {
  const modal = document.getElementById('chartModal');
  modal.classList.remove('hidden');

  document.getElementById('modalStockSymbol').innerText = symbol;
  document.getElementById('modalStockName').innerText = 'Loading historical data...';

  try {
    const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/chart?period=6mo&interval=1d`);
    if (!res.ok) throw new Error('Chart data unavailable');

    const data = await res.json();
    const currSym = data.currency === 'INR' ? '₹' : '$';

    document.getElementById('modalStockName').innerText = data.name || symbol;
    document.getElementById('modalStockSector').innerText = data.fundamentals?.sector || 'General';

    const latest = data.candle_data[data.candle_data.length - 1] || {};
    document.getElementById('modalPrice').innerText = `${currSym}${latest.close || '--'}`;
    document.getElementById('modalPe').innerText = data.fundamentals?.trailing_pe ? `${data.fundamentals.trailing_pe.toFixed(1)}` : 'N/A';
    document.getElementById('modalVolRatio').innerText = `${latest.volume ? (latest.volume / 1000).toFixed(0) + 'k' : '--'}`;
    document.getElementById('modalRsi').innerText = latest.rsi ? latest.rsi.toFixed(1) : '--';

    renderModalCharts(data.candle_data, currSym);
  } catch (err) {
    document.getElementById('modalStockName').innerText = `Error: ${err.message}`;
  }
}

function renderModalCharts(candleData, currSym) {
  const dates = candleData.map(d => d.date);
  const closes = candleData.map(d => d.close);
  const rsis = candleData.map(d => d.rsi);

  // Price Chart
  const ctxPrice = document.getElementById('stockPriceChart').getContext('2d');
  if (state.priceChartInstance) state.priceChartInstance.destroy();

  state.priceChartInstance = new Chart(ctxPrice, {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'Close Price',
          data: closes,
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.1)',
          borderWidth: 2,
          fill: true,
          pointRadius: 0,
          tension: 0.1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `Price: ${currSym}${ctx.parsed.y}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(55, 65, 81, 0.3)' },
          ticks: { color: '#9ca3af', font: { size: 10 }, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: 'rgba(55, 65, 81, 0.3)' },
          ticks: { color: '#9ca3af', font: { size: 10 } }
        }
      }
    }
  });

  // RSI Chart
  const ctxRsi = document.getElementById('stockRsiChart').getContext('2d');
  if (state.rsiChartInstance) state.rsiChartInstance.destroy();

  state.rsiChartInstance = new Chart(ctxRsi, {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'RSI (14)',
          data: rsis,
          borderColor: '#a78bfa',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { display: false }
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: 'rgba(55, 65, 81, 0.3)' },
          ticks: {
            stepSize: 30,
            color: '#9ca3af',
            font: { size: 9 },
            callback: (v) => `${v}`
          }
        }
      }
    }
  });
}

function closeChartModal() {
  document.getElementById('chartModal').classList.add('hidden');
}

// Export Filtered Results to CSV
function exportToCsv() {
  if (state.filtered.length === 0) {
    alert('No stocks available to export. Run a scan first.');
    return;
  }

  const headers = ['Rank', 'Symbol', 'Name', 'Sector', 'Price', '1D_Change_Pct', 'PE_Ratio', 'Volume_Spike_Ratio', 'RSI_14', 'Rank_Score', 'Current_Volume', 'Avg_Volume_20D'];
  const rows = state.filtered.map(s => [
    s.rank,
    s.symbol,
    `"${(s.name || '').replace(/"/g, '""')}"`,
    `"${(s.sector || '').replace(/"/g, '""')}"`,
    s.current_price,
    s.change_1d_pct,
    s.trailing_pe !== null ? s.trailing_pe : '',
    s.volume_ratio,
    s.rsi !== null ? s.rsi : '',
    s.rank_score,
    s.current_volume,
    s.avg_volume_20d
  ]);

  const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = `stock_screener_${state.market}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// Make openChartModal accessible globally
window.openChartModal = openChartModal;
