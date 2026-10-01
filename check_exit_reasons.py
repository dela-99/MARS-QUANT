import sqlite3, tempfile
c = sqlite3.connect(tempfile.gettempdir() + r'\mt5_audit_real.db', check_same_thread=False)
print('Exit reason distribution in current closed fills:')
for r in c.execute('SELECT exit_reason, COUNT(*) FROM fills WHERE is_closed=1 GROUP BY exit_reason ORDER BY 2 DESC').fetchall():
    print(f'  {str(r[0]):10} -> {r[1]}')
print()
print('System (SL/TP) vs Manual split:')
sys_n = c.execute("SELECT COUNT(*) FROM fills WHERE is_closed=1 AND exit_reason IN ('sl_hit','tp_hit')").fetchone()[0]
man_n = c.execute("SELECT COUNT(*) FROM fills WHERE is_closed=1 AND (exit_reason IS NULL OR exit_reason NOT IN ('sl_hit','tp_hit'))").fetchone()[0]
print(f'  System (SL/TP): {sys_n}')
print(f'  Manual (other): {man_n}')