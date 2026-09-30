"""Capture the full dashboard with explicit scroll-and-stitch OR just a tall window.

Pylance note: `selenium` lives in .venv/Lib/site-packages (installed via
`.venv\\Scripts\\python.exe -m pip install selenium`). If imports break in
your editor, reload the Python window or re-run "Python: Restart Language Server".
"""
import sys, os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

opts = Options()
opts.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-gpu")
opts.add_argument("--hide-scrollbars")
# Very tall window to capture everything in one shot
opts.add_argument("--window-size=1600,8000")

driver = webdriver.Chrome(options=opts)
driver.set_window_size(1600, 8000)
print("Navigating...")
driver.get("http://localhost:8765")

print("Waiting for content...")
WebDriverWait(driver, 30).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='stMetricValue'], .stMetric"))
)
time.sleep(8)  # let everything render

out = r"C:\Users\RIDGE\MARS-QUANT\dashboard_full.png"
# Full-page screenshot using DevTools Protocol via Chrome's Page.captureScreenshot
result = driver.execute_cdp_cmd("Page.captureScreenshot", {"captureBeyondViewport": True, "format": "png"})
import base64
with open(out, "wb") as f:
    f.write(base64.b64decode(result["data"]))
print(f"Saved {out}: {os.path.getsize(out)} bytes")

driver.quit()