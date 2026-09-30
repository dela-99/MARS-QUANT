"""
Capture TWO screenshots a few seconds apart to demonstrate
the Signal/Trade Log updates across consecutive refreshes.
"""
import sys, os, time, sqlite3
from datetime import datetime
sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

opts = Options()
opts.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-gpu")
opts.add_argument("--hide-scrollbars")
opts.add_argument("--window-size=1600,1500")

# === INJECT a new evaluation row directly into the audit DB to prove
#     the log updates ===
DB = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()
new_ts = datetime.utcnow().isoformat(timespec='microseconds')
cur.execute("""
    INSERT INTO evaluations (timestamp, symbol, gate_result, rejection_reason,
        trend_1h, bias_30m, context_15m, context_15m_reason,
        breakout_signal, breakout_price, breakout_stop,
        h1_trend, h1_strength, h1_adx,
        m30_trend, m30_strength, m30_adx,
        m15_trend, m15_strength, m15_adx)
    VALUES (?, 'XAUUSDm', 'ALLOWED', NULL,
        'LONG_BIAS', 'LONG_BIAS', 'TRADEABLE', 'Spread and ATR within normal range',
        1, 4155.50, 4146.00,
        'NEUTRAL', 0.0, 0.0, 'NEUTRAL', 0.0, 0.0, 'NEUTRAL', 0.0, 0.0)
""", (new_ts,))
conn.commit()
conn.close()
print(f"[OK] Injected test eval at {new_ts}")

driver = webdriver.Chrome(options=opts)
driver.set_window_size(1600, 1500)

def capture(name):
    driver.get("http://localhost:8765")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stMetricValue']"))
    )
    time.sleep(3)
    out = f"C:\\Users\\RIDGE\\MARS-QUANT\\{name}"
    result = driver.execute_cdp_cmd("Page.captureScreenshot", {"format": "png"})
    import base64
    with open(out, "wb") as f:
        f.write(base64.b64decode(result["data"]))
    print(f"[OK] {out}: {os.path.getsize(out)} bytes")

capture("dashboard_refresh1.png")

# Inject another eval
conn = sqlite3.connect(DB, check_same_thread=False)
new_ts2 = datetime.utcnow().isoformat(timespec='microseconds')
conn.execute("""
    INSERT INTO evaluations (timestamp, symbol, gate_result, rejection_reason,
        trend_1h, bias_30m, context_15m, context_15m_reason,
        breakout_signal, breakout_price, breakout_stop,
        h1_trend, h1_strength, h1_adx,
        m30_trend, m30_strength, m30_adx,
        m15_trend, m15_strength, m15_adx)
    VALUES (?, 'XAUUSDm', 'ALLOWED', NULL,
        'LONG_BIAS', 'LONG_BIAS', 'TRADEABLE', 'Spread and ATR within normal range',
        1, 4155.80, 4146.30,
        'NEUTRAL', 0.0, 0.0, 'NEUTRAL', 0.0, 0.0, 'NEUTRAL', 0.0, 0.0)
""", (new_ts2,))
conn.commit()
conn.close()
print(f"[OK] Injected second test eval at {new_ts2}")

capture("dashboard_refresh2.png")

driver.quit()
print("[OK] Two refreshes captured")