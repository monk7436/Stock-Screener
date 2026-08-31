# 📈 Multi-Factor Stock Screener (NSE & NYSE)

A real-time stock screener built with Python, FastAPI, and Yahoo Finance (`yfinance`). Filters and ranks equities across Indian markets (Nifty 50, Bank Nifty, Nifty 100, Nifty 500) and US markets (S&P 500, NYSE) with live streaming progress and interactive UI controls.

![Stock Screener UI](frontend/index.html)

---

## ✨ Features

- 🇮🇳 **Indian Markets (NSE)**: Nifty 50, Bank Nifty, Nifty 100, Nifty 500.
- 🇺🇸 **US Markets**: S&P 100 / Large Cap Leaders, NYSE Blue Chips.
- 🎯 **Interactive Indicators & Sliders**:
  - **P/E Ratio** ($\le 20.0$ default, $5 - 100$ slider + loss-making toggle).
  - **Volume Spike Ratio** ($\ge 2.0\times$ default, $0.5\times - 8.0\times+$ vs 20-day rolling baseline).
  - **14-Period RSI** ($\ge 50.0$ default, $0 - 100$ slider).
- ⚡ **Real-Time Client Re-filtering**: Instantly filters results client-side as you drag sliders without waiting for re-scans.
- 📊 **Multi-Factor Ranking Algorithm**:
  $$\text{Rank Score} = (\text{Volume Spike} \times 45\%) + (\text{RSI} \times 35\%) + (\text{Valuation / Low PE} \times 20\%)$$
- 📈 **Interactive Chart Modal**: Candlestick/line chart with historical volume and 14-period RSI indicator.
- 📥 **One-Click CSV Export**: Download filtered and ranked screening data.
- 🛡️ **Rate-Limit Resilient**: Multi-threaded batch downloading and in-memory TTL caching.

---

## 🚀 Quick Start (Local)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/YOUR_USERNAME/stock-screener.git
cd stock-screener
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python run.py
```
Open **`http://localhost:8000`** in your browser.

---

## ☁️ Deployment (Render)

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`

---

## 📄 License
MIT License
