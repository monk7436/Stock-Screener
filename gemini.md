# Stock Screener (NSE & NYSE / US Markets)

## Project Overview
A high-performance, real-time stock screener built with Python and Yahoo Finance (`yfinance`). The tool filters, ranks, and visualizes equities across Indian markets (Nifty 50, Nifty 100, Nifty 500) and US markets (S&P 500, NYSE, NASDAQ) based on key fundamental and technical metrics:
- **P/E Ratio** (Trailing & Forward P/E)
- **Volume Spike** (Current Volume / 20-Day Average Volume Ratio)
- **RSI** (14-Period Relative Strength Index)
- **Price & Momentum Indicators** (52-Week Range, SMA 20/50/200, % Change)

---

## Architecture

```
Stock Screener
├── backend/
│   ├── app.py                 # FastAPI Web Server & API Endpoints
│   ├── screener.py            # Core Screening Engine & Rank Calculator
│   ├── data_fetcher.py        # yfinance Batch Ingestion & Rate-Limit Cache Engine
│   ├── indicators.py          # Technical Analysis (RSI, Moving Averages, Volume Ratios)
│   └── universes/             # Curated & Dynamic Ticker Universes
│       ├── nse_nifty500.json  # Nifty 500 / Nifty 50 / Nifty 100
│       └── us_nyse_sp500.json # S&P 500 / NYSE Top Equities
├── frontend/
│   ├── index.html             # Sleek Dark-Themed Dashboard UI
│   ├── app.js                 # Dynamic UI Controller, Filter Sliders, Real-time Data Grid
│   └── style.css              # Custom styling, Glassmorphism & Visual indicators
├── gemini.md                  # Project context & architecture documentation
├── requirements.txt           # Python package dependencies
└── run.py                     # One-click launcher script
```

---

## Screening Indicators & Methodology

1. **Price-to-Earnings (P/E) Ratio**:
   - Fetched via `yfinance.Ticker.info` (`trailingPE` / `forwardPE`).
   - Default filter: $P/E \le 20$ (with interactive min/max slider controls).
   - Handles negative / non-profitable companies gracefully with selectable filters.

2. **Volume Spike Ratio**:
   - Calculated as:
     $$\text{Volume Ratio} = \frac{\text{Current Daily Volume}}{\text{20-Day Rolling Average Volume}}$$
   - Default filter: $\text{Volume Ratio} \ge 2.0\times$ (adjustable via slider).

3. **Relative Strength Index (RSI - 14 Days)**:
   - Computed on 14-period closing prices using standard Wilder's Smoothing:
     $$RSI = 100 - \left( \frac{100}{1 + RS} \right)$$
     where $RS = \frac{\text{Average Gain over 14 days}}{\text{Average Loss over 14 days}}$.
   - Default filter: $RSI \ge 50$ (adjustable min/max 0–100 range).

4. **Multi-Factor Ranking Algorithm**:
   - Computes a composite ranking score based on Volume Spike momentum, RSI strength, and valuation to present top ranked opportunities.

---

## Rate Limiting & Performance Strategy
- **Bulk Batch Fetching**: Utilizes `yfinance.download(tickers, period='1mo', interval='1d', threads=True)` in chunked batches (e.g. 50–100 tickers/batch) to minimize HTTP overhead.
- **In-Memory & SQLite/Disk TTL Caching**: Historical candle data and fundamentals cached with configurable TTL (5–15 minutes) to avoid repeated API hits.
- **Asynchronous / Streaming Progress**: Background worker streams progress to the UI via Server-Sent Events (SSE) or WebSocket so users see real-time scanning progress without browser timeouts.
- **Adaptive Throttling & Jitter**: Inter-batch delays prevent 429 Rate Limit responses from Yahoo Finance endpoints.

---

## Server & Port Configuration
- **Default Application Port**: `http://localhost:8000` (or fallback `http://localhost:8501` if requested).
- **FastAPI / Uvicorn** engine provides lightweight, high-concurrency API performance.
