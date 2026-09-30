"""Find the exact transition from SHORT_BIAS to LONG_BIAS in the audit DB."""
import sqlite3, sys
db = r"C:\Users\RIDGE\AppData\Local\Temp\mt5_audit_real.db"
c = sqlite3.connect(db)
cur = c.cursor()

# Get the transition point: where bias_30m changed from SHORT_BIAS to LONG_BIAS
cur.execute("""
    SELECT timestamp, trend_1h, bias_30m, gate_result
    FROM evaluations
    WHERE symbol='XAUUSDm'
    ORDER BY timestamp ASC
""")
rows = cur.fetchall()
print(f"Total evaluations: {len(rows)}")

# Find runs of each bias state
prev = None
start = None
runs = []
for ts, h1, m30, gr in rows:
    state = (h1, m30)
    if state != prev:
        if prev is not None:
            runs.append((start, rows[i-1][0], prev))
        start = ts
        prev = state
    i = rows.index((ts, h1, m30, gr)) if (ts, h1, m30, gr) in rows else None
# Better approach: just iterate
runs = []
prev = None
start_idx = 0
for i, (ts, h1, m30, gr) in enumerate(rows):
    state = (h1, m30)
    if state != prev:
        if prev is not None:
            runs.append((rows[start_idx][0], rows[i-1][0], prev, i - start_idx))
        start_idx = i
        prev = state
if prev is not None:
    runs.append((rows[start_idx][0], rows[-1][0], prev, len(rows) - start_idx))

print("\nBias run-length summary:")
for r in runs:
    print(f"  {r[0]}  ->  {r[1]}  ({r[3]:>4} cycles)  state={r[2]}")

# Find transitions to LONG_BIAS/LONG_BIAS
print("\nLast 5 transitions (start->end, cycles, state):")
for r in runs[-5:]:
    print(f"  {r[0]} -> {r[1]}  ({r[3]} cycles)  {r[2]}")

# Show the SHORT-to-LONG transition with 2 lines before/after
print("\n=== TRANSITION SEARCH: SHORT_BIAS/SHORT_BIAS -> LONG_BIAS/LONG_BIAS ===")
for i in range(1, len(rows)):
    prev_row = rows[i-1]
    cur_row = rows[i]
    if prev_row[2] == 'SHORT_BIAS' and cur_row[2] == 'LONG_BIAS':
        print(f"30M bias flipped at {cur_row[0]} (after {prev_row[0]})")
        for j in range(max(0, i-3), min(len(rows), i+3)):
            marker = "  >>>" if j == i else "     "
            print(f"{marker} {rows[j][0]}  1H={rows[j][1]:<10}  30M={rows[j][2]:<10}  gate={rows[j][3]}")
        print("---")