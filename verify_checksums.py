import hashlib
import json

# Check M5 raw data
with open('data/raw/xauusdm/m5/exness/_manifest.json') as f:
    m = json.load(f)
with open('data/raw/xauusdm/m5/exness/XAUUSDm_M5_2020_2026_raw.csv', 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
print('M5 Raw CSV:')
print('  Manifest: ' + m['consolidated_checksum'])
print('  Actual:   ' + h)
print('  Match: ' + str(h == m['consolidated_checksum']))

# Check H1 raw data
with open('data/raw/xauusdm/h1/exness/_manifest.json') as f:
    m = json.load(f)
with open('data/raw/xauusdm/h1/exness/XAUUSDm_H1_2015_2025_raw.parquet', 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
print('\nH1 Raw Parquet:')
print('  Manifest: ' + m['checksum'])
print('  Actual:   ' + h)
print('  Match: ' + str(h == m['checksum']))