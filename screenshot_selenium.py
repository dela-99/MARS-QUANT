"""Use Selenium to capture Streamlit after WebSocket-rendered content loads."""
import sys, os, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

sys.path.insert(0, r"C:\Users\RIDGE\MARS-QUANT")
os.chdir(r"C:\Users\RIDGE\MARS-QUANT")

# Check if a chromedriver is available, otherwise use built-in ChromeDriver manager
opts = Options()
opts.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
opts.add_argument("--headless=new")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-gpu")
opts.add_argument("--hide-scrollbars")
opts.add_argument("--window-size=1600,5000")

# Use the Selenium 4 built-in driver manager
from selenium.webdriver.chrome.service import Service as ChromeService

driver = None
try:
    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(1600, 5000)
    print("Navigating to http://localhost:8765 ...")
    driver.get("http://localhost:8765")

    # Wait for Streamlit content to render — look for the "stApp" container
    # or any element containing real text (not skeleton)
    print("Waiting for content to render ...")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".stMarkdown, .stMetric, [data-testid='stMetricValue']"))
    )
    # Give Streamlit a couple more seconds to finish painting
    time.sleep(4)

    # Capture full page (not just viewport)
    out = r"C:\Users\RIDGE\MARS-QUANT\dashboard_screenshot.png"
    driver.save_screenshot(out)
    print(f"Screenshot saved: {out}")
    sz = os.path.getsize(out)
    print(f"Size: {sz} bytes")
finally:
    if driver:
        driver.quit()