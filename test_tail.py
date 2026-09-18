class TestCrossSymbolRiskAggregation(unittest.TestCase):
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

        # Simulate first XAUUSD position with $60 risk (within tier budget)
        pos1_config = TradeConfig(
            symbol="XAUUSDm",
            signal=1,
            position_size=0.01,
            entry_price=2000.00,
            stop_price=1940.00,  # 60 points = $60 risk for 0.01 lot XAUUSD
            take_profit=2150.00,
        )

        # Check aggregate risk for first position
        can_open_1, reason_1 = rm.check_aggregate_risk(pos1_config, 10000.0)
        self.assertTrue(can_open_1)

        # Register the position (simulates opening it)
        rm.total_open_risk += 60.0  # $60 risk

        # Now try to open second XAUUSD position with $60 risk
        # Total would be $120 > $100 cap
        pos2_config = TradeConfig(
            symbol="XAUUSDm",
            signal=1,
            position_size=0.01,
            entry_price=2000.00,
            stop_price=1940.00,  # 60 points = $60 risk for 0.01 lot XAUUSD
            take_profit=2150.00,
        )

        # Check aggregate risk for second position - should be rejected
        can_open_2, reason_2 = rm.check_aggregate_risk(pos2_config, 10000.0)
        self.assertFalse(can_open_2)
        self.assertIn("exceeds", reason_2.lower())


class TestMultiSymbolDryRun(unittest.TestCase):
    """Test multi-symbol dry-run behavior."""

    def test_get_enabled_symbols_returns_correct_list(self):
        from mars.apps.trading.system.pair_config import get_enabled_symbols

        enabled = get_enabled_symbols()
        expected = ["XAUUSDm", "EURUSDm", "USDJPYm"]
        self.assertEqual(enabled, expected)
        self.assertNotIn("EURGBPm", enabled)

    def test_each_symbol_has_own_config(self):
        from mars.apps.trading.system.pair_config import PAIR_CONFIG

        for symbol in ["XAUUSDm", "EURUSDm", "USDJPYm"]:
            config = PAIR_CONFIG[symbol]
            self.assertTrue(config["enabled"])
            self.assertIn("donchian_window", config)
            self.assertIn("stop_multiplier", config)
            self.assertIn("rr_ratio", config)
            self.assertEqual(config["donchian_window"], 20)
            self.assertEqual(config["stop_multiplier"], 2.0)
            self.assertEqual(config["rr_ratio"], 2.5)

        # EURGBPm has disabled_reason
        eurgbp = PAIR_CONFIG["EURGBPm"]
        self.assertFalse(eurgbp["enabled"])
        self.assertIn("disabled_reason", eurgbp)
        self.assertIn("PF=0.95", eurgbp["disabled_reason"])