import os
import re

patterns = [
    r'[0-9]{6,10}',
    r'[A-Za-z0-9]{32,}',
    r'password\s*[:=]\s*["\']?[^"\'\s]+',
    r'secret\s*[:=]\s*["\']?[^"\'\s]+',
    r'token\s*[:=]\s*["\']?[^"\'\s]+',
    r'key\s*[:=]\s*["\']?[^"\'\s]+',
]

files_to_check = [
    'C:\\Users\\RIDGE\\MARS-QUANT\\configs\\instrument_spec_xauusdm.yaml',
    'C:\\Users\\RIDGE\\MARS-QUANT\\configs\\session_momentum_001.yaml',
    'C:\\Users\\RIDGE\\MARS-QUANT\\data\\catalog.yaml',
    'C:\\Users\\RIDGE\\MARS-QUANT\\run_session_v3.py',
    'C:\\Users\\RIDGE\\MARS-QUANT\\mars\\libs\\data\\xauusdm_exness.py',
    'C:\\Users\\RIDGE\\MARS-QUANT\\mars\\libs\\risk\\contract_aware.py',
]

for f in files_to_check:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
            content = fp.read()
        for p in patterns:
            matches = re.findall(p, content, re.IGNORECASE)
            if matches:
                print(f + ': Pattern ' + p + ' -> ' + str(matches[:5]))