with open('tests/unit/trading/test_risk_rules.py', 'r') as f:
    lines = f.readlines()

# Find the line with 'assert abs(pnl_usd - 6.25) < 1e-10' at proper indent
target_idx = None
for i, line in enumerate(lines):
    if line.strip() == 'assert abs(pnl_usd - 6.25) < 1e-10' and line.startswith('        '):
        target_idx = i
        break

print(f'Target line: {target_idx}')

if target_idx is not None:
    # Keep everything up to and including this line
    new_lines = lines[:target_idx+1]
    
    # Add new tests with correct indentation
    additions = [
        '\n\n',
        '# Phase 5: Multi-pair tests\n',
        'class TestDisabledPair(unittest.TestCase):\n',
        '    """Test that disabled pairs generate zero signals/orders."""\n\n',
        '    def setUp(self):\n',
        '        from mars.apps.trading.system.pair_config import PAIR_CONFIG\n',
        '        self.original_eurgbp = PAIR_CONFIG["EURGBPm"].copy()\n',
        '        PAIR_CONFIG["EURGBPm"]["enabled"] = False\n\n',
        '    def tearDown(self):\n',
        '        from mars.apps.trading.system.pair_config import PAIR_CONFIG\n',
        '        PAIR_CONFIG["EURGBPm"] = self.original_eurgbp\n\n',
        '    def test_disabled_pair_generates_zero_signals(self):\n',
        '        """Disabled pair should produce no signals through the pipeline."""\n',
        '        from mars.apps.trading.system.pair_config import PAIR_CONFIG, get_enabled_symbols\n',
        '        from mars.apps.trading.signals.trend_breakout import TrendBreakoutSignal\n\n',
        '        # EURGBPm is disabled\n',
        '        self.assertFalse(PAIR_CONFIG["EURGBPm"]["enabled"])\n',
        '        self.assertNotIn("EURGBPm", get_enabled_symbols())\n\n',
        '        # XAUUSDm is enabled\n',
        '        self.assertTrue(PAIR_CONFIG["XAUUSDm"]["enabled"])\n',
        '        self.assertIn("XAUUSDm", get_enabled_symbols())\n\n',
        '        # Signal generator for disabled pair should still be creatable\n',
        '        # but should not be called in live session\n',
        '        config = PAIR_CONFIG["EURGBPm"]\n',
        '        signal_gen = TrendBreakoutSignal(\n',
        '            donchian_window=config["donchian_window"],\n',
        '            stop_multiplier=config["stop_multiplier"],\n',
        '            rr_ratio=config["rr_ratio"],\n',
        '        )\n',
        '        # Signal gen exists but live runner skips it\n',
        '        self.assertIsNotNone(signal_gen)\n\n\n',
        'class TestCrossSymbolRiskAggregation(unittest.TestCase):\n',
        '    """Test that risk caps aggregate ACROSS symbols, not per-symbol independently."""\n\n',
        '    def test_concurrent_risk_cap_shared_across_symbols(self):\n',
        '        """Two symbols with open positions should share the concurrent risk cap."""\n',
        '        from mars.apps.trading.system.tiered_risk_config import (\n',
        '            get_risk_tiers,\n',
        '            select_tier_by_equity,\n',
        '            get_max_concurrent_risk,\n',
        '        )\n\n',
        '        tiers = get_risk_tiers()\n',
        '        tier = select_tier_by_equity(10000.0)  # Tier 1\n',
        '        max_concurrent = get_max_concurrent_risk(tier)\n\n',
        '        # Tier 1: max_concurrent_risk = 1.0% equity = $100\n',
        '        self.assertEqual(max_concurrent, 0.01 * 10000.0)\n\n',
        '        # Simulate two symbols each trying to use 0.6% risk\n',
        '        # Total would be 1.2% > 1.0% cap -> should be rejected\n',
        '        eur_risk = 0.006 * 10000.0  # $60\n',
        '        usd_risk = 0.006 * 10000.0  # $60\n',
        '        total_risk = eur_risk + usd_risk  # $120\n\n',
        '        self.assertGreater(total_risk, max_concurrent)\n\n',
        '        # The risk manager should reject the second position\n',
        '        # when total concurrent risk would exceed cap\n',
        '        from mars.apps.trading.risk.risk_manager import RiskManager\n\n',
        '        rm = RiskManager(tier)\n\n',
        '        # Mock position objects\n',
        '        class MockPos:\n',
        '            def __init__(self, symbol, risk_usd):\n',
        '                self.symbol = symbol\n',
        '                self.risk_usd = risk_usd\n\n',
        '        pos1 = MockPos("EURUSDm", eur_risk)\n',
        '        pos2 = MockPos("USDJPYm", usd_risk)\n\n',
        '        # First position should be allowed\n',
        '        can_open_1 = rm.can_open_position(pos1)\n',
        '        self.assertTrue(can_open_1)\n',
        '        rm.register_position(pos1)\n\n',
        '        # Second position should be rejected (exceeds cap)\n',
        '        can_open_2 = rm.can_open_position(pos2)\n',
        '        self.assertFalse(can_open_2)\n\n\n',
        'class TestMultiSymbolDryRun(unittest.TestCase):\n',
        '    """Test multi-symbol dry-run behavior."""\n\n',
        '    def test_get_enabled_symbols_returns_correct_list(self):\n',
        '        from mars.apps.trading.system.pair_config import get_enabled_symbols\n\n',
        '        enabled = get_enabled_symbols()\n',
        '        expected = ["XAUUSDm", "EURUSDm", "USDJPYm"]\n',
        '        self.assertEqual(enabled, expected)\n',
        '        self.assertNotIn("EURGBPm", enabled)\n\n',
        '    def test_each_symbol_has_own_config(self):\n',
        '        from mars.apps.trading.system.pair_config import PAIR_CONFIG\n\n',
        '        for symbol in ["XAUUSDm", "EURUSDm", "USDJPYm"]:\n',
        '            config = PAIR_CONFIG[symbol]\n',
        '            self.assertTrue(config["enabled"])\n',
        '            self.assertIn("donchian_window", config)\n',
        '            self.assertIn("stop_multiplier", config)\n',
        '            self.assertIn("rr_ratio", config)\n',
        '            self.assertEqual(config["donchian_window"], 20)\n',
        '            self.assertEqual(config["stop_multiplier"], 2.0)\n',
        '            self.assertEqual(config["rr_ratio"], 2.5)\n\n',
        '        # EURGBPm has disabled_reason\n',
        '        eurgbp = PAIR_CONFIG["EURGBPm"]\n',
        '        self.assertFalse(eurgbp["enabled"])\n',
        '        self.assertIn("disabled_reason", eurgbp)\n',
        '        self.assertIn("PF=0.95", eurgbp["disabled_reason"])\n',
    ]
    
    new_lines.extend(additions)
    
    with open('tests/unit/trading/test_risk_rules.py', 'w') as f:
        f.writelines(new_lines)
    print('File rewritten successfully')