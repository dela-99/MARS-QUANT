with open('tests/unit/trading/test_risk_rules.py', 'r') as f:
    lines = f.readlines()

# Find the start and end of the TestCrossSymbolRiskAggregation class
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'class TestCrossSymbolRiskAggregation' in line:
        start_idx = i
    if 'class TestMultiSymbolDryRun' in line:
        end_idx = i
        break

print(f'Start: {start_idx}, End: {end_idx}')

if start_idx is not None and end_idx is not None:
    # Replace the test class
    new_test = '''class TestCrossSymbolRiskAggregation(unittest.TestCase):
    """Test that risk caps aggregate ACROSS symbols, not per-symbol independently."""

    def test_concurrent_risk_cap_shared_across_symbols(self):
        """Two symbols with open positions should share the concurrent risk cap."""
        from mars.apps.trading.system.vol_scaled_system import RiskManager, TradeConfig

        # Create risk manager with Tier 4 ($10k+ equity, 1% risk, 6 max trades)
        rm = RiskManager()
        rm.select_tier_for_equity(10000.0)
        tier = rm.get_current_tier()
        
        # Tier 4: risk_pct_per_trade = 1% = $100 max total concurrent risk
        max_total_risk = 10000.0 * tier["risk_pct_per_trade"]
        self.assertEqual(max_total_risk, 100.0)
        
        # Simulate EURUSD position with $60 risk (within tier budget)
        eur_config = TradeConfig(
            symbol="EURUSDm",
            position_size=0.01,
            entry_price=1.1000,
            stop_price=1.0940,  # 60 pips = $60 risk for 0.01 lot
            take_profit_price=1.1150,
        )
        
        # Check aggregate risk for first position
        can_open_1, reason_1 = rm.check_aggregate_risk(eur_config, 10000.0)
        self.assertTrue(can_open_1)
        
        # Register the position (simulates opening it)
        rm.total_open_risk += 60.0  # $60 risk
        
        # Now try to open USDJPY position with $60 risk
        # Total would be $120 > $100 cap
        usd_config = TradeConfig(
            symbol="USDJPYm",
            position_size=0.01,
            entry_price=150.00,
            stop_price=149.40,  # 60 pips = $60 risk for 0.01 lot (approx)
            take_profit_price=151.50,
        )
        
        # Check aggregate risk for second position - should be rejected
        can_open_2, reason_2 = rm.check_aggregate_risk(usd_config, 10000.0)
        self.assertFalse(can_open_2)
        self.assertIn("exceeds", reason_2.lower())'''

    new_lines = lines[:start_idx]
    new_lines.append(new_test + '\n\n')
    new_lines.extend(lines[end_idx:])
    
    with open('tests/unit/trading/test_risk_rules.py', 'w') as f:
        f.writelines(new_lines)
    print('Test class replaced successfully')
else:
    print('Could not find class boundaries')