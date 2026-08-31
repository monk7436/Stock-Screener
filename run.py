"""
Stock Screener Launcher
Verifies environment, finds available port (8000 -> 8501 fallback), and starts the server with browser auto-open.
"""

import sys
import socket
import webbrowser
import threading
import time
import uvicorn


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def find_available_port(preferred_ports=(8000, 8501, 8080, 5000)) -> int:
    for p in preferred_ports:
        if not is_port_in_use(p):
            return p
    # Fallback to ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def open_browser_delayed(url: str, delay: float = 1.5):
    time.sleep(delay)
    print(f"\n🚀 Opening Stock Screener in your browser: {url}\n")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Notice: Could not automatically open browser: {e}")


def main():
    print("=" * 60)
    print("      REAL-TIME STOCK SCREENER (NSE & NYSE)      ")
    print("=" * 60)
    
    port = find_available_port()
    host = "127.0.0.1"
    url = f"http://{host}:{port}"
    
    print(f"[*] Starting FastAPI Server on {url}...")
    print(f"[*] Multi-factor indicators: P/E < 20, Volume Spike > 2x, RSI > 50")
    print(f"[*] Markets supported: Indian NSE (Nifty 50, Bank Nifty, Nifty 100, Nifty 500) & US NYSE / S&P")
    print("=" * 60)

    # Launch browser after a brief delay
    threading.Thread(target=open_browser_delayed, args=(url,), daemon=True).start()

    # Run Uvicorn server
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        log_level="info",
        reload=False
    )


if __name__ == "__main__":
    main()
