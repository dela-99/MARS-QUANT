"""Verify the path resolution fix works for all suffixed broker symbols."""
from mars.apps.trading.system.pair_config import get_data_path, get_config_key, get_contract_specs
import os

print('=== Path resolution for all known broker symbols ===')
for sym in ['XAUUSDm', 'EURUSDm', 'USDJPYm', 'EURGBPm']:
    cfg_key = get_config_key(sym)
    path = get_data_path(sym)
    specs = get_contract_specs(sym)
    exists = os.path.exists(path)
    cs = specs.get('contract_size')
    ps = specs.get('pip_size')
    print(f"  {sym:8} -> cfg_key={cfg_key:8}  contract_size={cs:>7.0f}  pip_size={ps:.5f}  exists={exists}")
    print(f"             path: {path}")

# What the OLD broken code would have produced
print('\n=== What the OLD broken code would have produced ===')
for sym in ['XAUUSDm', 'EURUSDm', 'USDJPYm', 'EURGBPm']:
    old_path = f"data/processed/{sym.lower()}/m5/v1.0.0/data.parquet"
    exists = os.path.exists(old_path)
    print(f"  {sym:8} -> {old_path}  exists={exists}")