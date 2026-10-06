import requests, re
r = requests.get('http://127.0.0.1:8765/')
html = r.text

# Find metric sections
matches = re.findall(r'data-testid="stMetric"[^>]*>.*?</div>\s*</div>', html, re.DOTALL)
print(f'Metric matches found: {len(matches)}')
if matches:
    print('FIRST METRIC HTML (first 1500 chars):')
    print(matches[0][:1500])
    print()
    print('SECOND METRIC HTML (first 1500 chars):')
    print(matches[1][:1500] if len(matches) > 1 else '(none)')

# Look for open positions
print()
print('=== Looking for "Open Positions" section ===')
idx = html.find('Open Positions')
if idx > 0:
    print(f'Found at offset {idx}:')
    print(html[idx:idx+3000])
else:
    print('Not found in initial HTML')