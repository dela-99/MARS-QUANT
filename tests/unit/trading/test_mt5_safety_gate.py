"""
Tests for MT5 Demo Account Safety Gate (Step 0).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from mars.apps.trading.mt5_executor import DemoAccountGate


class TestDemoAccountSafetyGate:
    """Step 0: Mandatory safety gate - hard-fail on non-demo accounts."""
    
    def test_gate_passes_on_demo_account(self):
        """Gate should pass when account is DEMO (trade_mode=0)."""
        # Create mock MT5 module
        mock_mt5 = Mock()
        mock_account_info = Mock()
        mock_account_info.login = 12345678
        mock_account_info.trade_mode = 0  # TRADE_MODE_DEMO = 0
        mock_account_info.balance = 100000.0
        mock_account_info.equity = 100000.0
        mock_account_info.currency = "USD"
        mock_account_info.leverage = 100
        
        mock_mt5.account_info.return_value = mock_account_info
        
        # Should not raise
        result = DemoAccountGate.verify_demo_account(mock_mt5)
        
        assert result["account_number"] == 12345678
        assert result["trade_mode"] == 0
        assert result["balance"] == 100000.0
        mock_mt5.account_info.assert_called_once()
    
    def test_gate_hard_fails_on_live_account(self):
        """Gate should raise RuntimeError on LIVE account (trade_mode=2)."""
        mock_mt5 = Mock()
        mock_account_info = Mock()
        mock_account_info.login = 987654321
        mock_account_info.trade_mode = 2  # TRADE_MODE_REAL = 2
        mock_account_info.balance = 50000.0
        mock_account_info.equity = 50000.0
        mock_account_info.currency = "USD"
        mock_account_info.leverage = 30
        
        mock_mt5.account_info.return_value = mock_account_info
        
        with pytest.raises(RuntimeError) as exc_info:
            DemoAccountGate.verify_demo_account(mock_mt5)
        
        error_msg = str(exc_info.value)
        assert "SAFETY GATE FAILED" in error_msg
        assert "NOT a DEMO account" in error_msg
        assert "987654321" in error_msg
        assert "Trade mode: 2" in error_msg  # Capital T in "Trade mode"
        assert "To disable this gate, modify DemoAccountGate.verify_demo_account()" in error_msg
    
    def test_gate_hard_fails_on_contest_account(self):
        """Gate should raise RuntimeError on CONTEST account (trade_mode=1)."""
        mock_mt5 = Mock()
        mock_account_info = Mock()
        mock_account_info.login = 111222333
        mock_account_info.trade_mode = 1  # TRADE_MODE_CONTEST = 1
        mock_account_info.balance = 10000.0
        mock_account_info.equity = 10000.0
        mock_account_info.currency = "USD"
        mock_account_info.leverage = 50
        
        mock_mt5.account_info.return_value = mock_account_info
        
        with pytest.raises(RuntimeError) as exc_info:
            DemoAccountGate.verify_demo_account(mock_mt5)
        
        error_msg = str(exc_info.value)
        assert "SAFETY GATE FAILED" in error_msg
        assert "NOT a DEMO account" in error_msg
    
    def test_gate_fails_when_account_info_unavailable(self):
        """Gate should fail if account_info() returns None."""
        mock_mt5 = Mock()
        mock_mt5.account_info.return_value = None
        mock_mt5.last_error.return_value = (1, "No connection")
        
        with pytest.raises(RuntimeError) as exc_info:
            DemoAccountGate.verify_demo_account(mock_mt5)
        
        error_msg = str(exc_info.value)
        assert "Failed to get account info" in error_msg
    
    def test_gate_logs_account_info_on_startup(self, capsys):
        """Gate should log account number and trade_mode on every startup."""
        mock_mt5 = Mock()
        mock_account_info = Mock()
        mock_account_info.login = 476944496
        mock_account_info.trade_mode = 0
        mock_account_info.balance = 100000.0
        mock_account_info.equity = 100000.0
        mock_account_info.currency = "USD"
        mock_account_info.leverage = 100
        
        mock_mt5.account_info.return_value = mock_account_info
        
        DemoAccountGate.verify_demo_account(mock_mt5)
        
        captured = capsys.readouterr()
        assert "MT5 ACCOUNT CONNECTED" in captured.out
        assert "476944496" in captured.out
        assert "Trade Mode: 0" in captured.out
    
    def test_gate_not_bypassable_by_env_var(self):
        """Gate must not be bypassable by environment variable."""
        # This test documents the requirement - the gate logic
        # does not check any environment variable for bypass
        import inspect
        source = inspect.getsource(DemoAccountGate.verify_demo_account)
        
        # Verify no bypass logic exists
        assert "os.getenv" not in source
        assert "BYPASS" not in source
        assert "DISABLE" not in source
        assert "skip" not in source.lower()
        # The only way to disable is to modify the source code


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])