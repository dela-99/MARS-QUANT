# M.A.R.S. Quant — Assignment 13
## Local Configuration Guide (Placeholders Only)

**DO NOT COMMIT THIS FILE OR ANY `.env` FILE.**
**NEVER SHARE CREDENTIALS THROUGH CHAT, EMAIL, OR GIT.**

---

### Required Environment Variables

Create a local `.env` file in the project root (`C:\Users\RIDGE\MARS-QUANT\.env`) with the following placeholders replaced by your actual values:

```bash
# Exness MT5 Demo Account (obtain fresh from Exness)
DEMO_ACCOUNT_NUMBER=YOUR_ACCOUNT_NUMBER
PASSWORD=YOUR_PASSWORD
SERVER=MetaQuotes-Demo

# FRED API Key (obtain fresh from FRED)
FRED_API_KEY=YOUR_FRED_API_KEY
```

---

### How to Obtain Fresh Credentials

#### Exness Demo Account
1. Log in to Exness Personal Area: https://my.exness.com/
2. Create a new **MT5 Demo Account** (Standard or Raw Spread)
3. Note the:
   - **Login** (account number) → `DEMO_ACCOUNT_NUMBER`
   - **Password** → `PASSWORD`
   - **Server** (e.g., `MetaQuotes-Demo`, `Exness-MT5Trial`) → `SERVER`

#### FRED API Key
1. Register at: https://fred.stlouisfed.org/docs/api/api_key.html
2. Generate a new API key
3. Replace `YOUR_FRED_API_KEY`

---

### Verification Commands

After creating `.env`, verify configuration loads correctly:

```bash
# Test MT5Config loads from env
cd C:\Users\RIDGE\MARS-QUANT
.venv/Scripts/python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from mars.apps.trading.mt5_executor import MT5Config
cfg = MT5Config(
    login=int(os.getenv('DEMO_ACCOUNT_NUMBER')),
    password=os.getenv('PASSWORD', ''),
    server=os.getenv('SERVER', ''),
)
print(f'is_configured: {cfg.is_configured()}')
print(f'login: {cfg.login}')
print(f'server: {cfg.server}')
"
```

Expected output with valid credentials:
```
is_configured: True
login: 12345678
server: MetaQuotes-Demo
```

---

### Run Dry-Run (No Credentials Needed)

```bash
# Single symbol
.venv/Scripts/python run_session_v3.py --symbols XAUUSDm --mock-mt5 --dry-run

# Multi-symbol
.venv/Scripts/python run_session_v3.py --symbols XAUUSDm,EURUSDm --mock-mt5 --dry-run
```

---

### Phase C: Live Demo Terminal Connection

Once credentials are configured and MT5 terminal is running/logged in:

```bash
# Connect to live MT5 terminal (requires running MT5 with logged-in demo account)
.venv/Scripts/python run_session_v3.py --symbols XAUUSDm --dry-run
```

This will:
1. Connect to running MT5 terminal
2. Verify account is DEMO (trade_mode=0)
3. Get live equity for tier selection
4. Validate XAUUSDm symbol metadata from broker
5. Run dry-run signal generation against live data

---

### Phase D: Controlled Demo Execution (REQUIRES EXPLICIT AUTHORIZATION)

**Only after successful Phase C and explicit user confirmation:**

```bash
# Live demo execution (minimal risk, smallest volume)
.venv/Scripts/python run_session_v3.py --symbols XAUUSDm --duration 60
```

---

### Security Reminders

- ✅ `.env` is in `.gitignore` — will never be committed
- ✅ `.env.example` contains only placeholders
- ✅ No hardcoded defaults in source code
- ✅ `MT5Config.is_configured()` fails closed (returns False without all 3)
- ✅ `DemoAccountGate` mandatory — cannot trade on non-DEMO accounts
- ❌ Never share actual values in chat, reports, or git
- ❌ Never commit `.env` files
- ❌ Rotate credentials if ever exposed

---

### Current Placeholders (from .env.example)

```
DEMO_ACCOUNT_NUMBER=YOUR_ACCOUNT_NUMBER
PASSWORD=YOUR_PASSWORD
SERVER=MetaQuotes-Demo
FRED_API_KEY=YOUR_FRED_API_KEY
```

**Replace all `YOUR_*` values with actual credentials before Phase C.**