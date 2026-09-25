#!/usr/bin/env python3
"""
M.A.R.S. Trading System - Monitoring Dashboard

Read-only Streamlit dashboard for live session monitoring.
Run: streamlit run dashboard.py
"""
import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import tempfile
import sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np

# Page config
st.set_page_config(
    page_title="M.A.R.S. Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .risk-event-critical { background-color: #ffebee; border-left-color: #f44336; }
    .risk-event-warning { background-color: #fff3e0; border-left-color: #ff9800; }
    .risk-event-info { background-color: #e3f2fd; border-left-color: #2196f3; }
    .enabled-badge { background-color: #c8e6c9; color: #2e7d32; padding: 0.25rem 0.5rem; border-radius: 0.25rem; }
    .disabled-badge { background-color: #ffcdd2; color: #c62828; padding: 0.25rem 0.5rem; border-radius: 0.25rem; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Session Definitions (matching hyp_b_session_vol.py)
# ============================================================

SESSION_DEFS_UTC = {
    "asia": (0, 8),
    "london": (8, 13),      # London morning only (non-overlap)
    "overlap": (13, 17),    # London/NY overlap
    "ny": (17, 22),         # NY afternoon
}

SESSION_COLORS = {
    "asia": "rgba(255, 193, 7, 0.15)",      # amber
    "london": "rgba(33, 150, 243, 0.15)",   # blue
    "overlap": "rgba(156, 39, 176, 0.15)",  # purple
    "ny": "rgba(76, 175, 80, 0.15)",        # green
}


# ============================================================
# Data Access Layer (Read-Only)
# ============================================================

@st.cache_resource
def get_db_connection():
    """Get read-only connection to audit database."""
    db_path = os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db')
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=30)
def load_table(table_name: str, limit: int = 1000) -> pd.DataFrame:
    """Load table from audit DB."""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        query = f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT {limit}"
        df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        st.error(f"Error loading {table_name}: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


@st.cache_data(ttl=30)
def load_kill_switch_status():
    """Load kill-switch status from JSON file."""
    import json
    ks_path = os.path.join(tempfile.gettempdir(), 'risk_kill_switch.json')
    if not os.path.exists(ks_path):
        return {}
    try:
        with open(ks_path, 'r') as f:
            return json.load(f)
    except:
        return {}


@st.cache_data(ttl=30)
def load_backup_status():
    """Load backup timestamps."""
    import json
    backup_dir = os.path.join(tempfile.gettempdir(), 'audit_backups')
    status = {}
    for fname in ['primary', 'secondary']:
        fpath = os.path.join(backup_dir, f'{fname}_backup_status.json')
        if os.path.exists(fpath):
            with open(fpath, 'r') as f:
                status[fname] = json.load(f)
    return status


@st.cache_data(ttl=30)
def load_evaluations(limit: int = 200) -> pd.DataFrame:
    """Load MTF gate evaluations from audit DB."""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        query = f"SELECT * FROM evaluations ORDER BY rowid DESC LIMIT {limit}"
        df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()


# ============================================================
# Data Loading Helpers (reuse existing backtest code)
# ============================================================

@st.cache_data(ttl=30)
def load_ohlcv_data(symbol: str, hours: int = 24) -> pd.DataFrame:
    """
    Load OHLCV data for a symbol from the same parquet source as backtest.
    Uses the SYMBOL_CONFIGS from run_multi_pair_backtest.py.
    Returns the most recent N hours of available data.
    """
    try:
        # Import the config and loader from the backtest module
        sys.path.insert(0, str(Path(__file__).parent))
        from run_multi_pair_backtest import SYMBOL_CONFIGS, load_symbol_data
        from mars.apps.trading.system.pair_config import get_config_key
        
        config_key = get_config_key(symbol)
        if config_key not in SYMBOL_CONFIGS:
            return pd.DataFrame()
        
        # Get ALL available data first (don't filter by start date)
        df = load_symbol_data(config_key, start="2020-01-01")
        
        if df.empty:
            return pd.DataFrame()
        
        # Use the latest available timestamp as the "now" reference
        latest_available = df.index.max()
        cutoff = latest_available - timedelta(hours=hours + 48)  # Extra buffer for indicators
        
        # Filter to the requested hours from the latest available data
        df = df[df.index >= cutoff]
        
        return df
    except Exception as e:
        st.error(f"Error loading OHLCV for {symbol}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=30)
def compute_donchian_bands(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Compute Donchian upper/lower bands."""
    if df.empty or len(df) < window:
        return pd.DataFrame()
    
    high_max = df["high"].rolling(window).max()
    low_min = df["low"].rolling(window).min()
    
    # Shift by 1 to avoid lookahead (bands based on completed bars)
    upper = high_max.shift(1)
    lower = low_min.shift(1)
    
    return pd.DataFrame({"donchian_upper": upper, "donchian_lower": lower}, index=df.index)


@st.cache_data(ttl=30)
def compute_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute ATR (Average True Range)."""
    if df.empty or len(df) < window:
        return pd.Series(index=df.index, dtype=float)
    
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift(1))
    low_close = np.abs(df["low"] - df["close"].shift(1))
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window).mean()
    
    return atr


@st.cache_data(ttl=30)
def add_session_shading(fig: go.Figure, df: pd.DataFrame):
    """Add session shading rectangles to the chart."""
    if df.empty:
        return
    
    # Get the date range of the data (ensure UTC timezone)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    
    start_date = df.index[0].date()
    end_date = df.index[-1].date()
    
    current_date = start_date
    while current_date <= end_date:
        for session_name, (hour_start, hour_end) in SESSION_DEFS_UTC.items():
            session_start = pd.Timestamp(current_date, tz='UTC') + pd.Timedelta(hours=hour_start)
            session_end = pd.Timestamp(current_date, tz='UTC') + pd.Timedelta(hours=hour_end)
            
            # Only add if session overlaps with data range
            if session_end > df.index[0] and session_start < df.index[-1]:
                fig.add_vrect(
                    x0=session_start,
                    x1=session_end,
                    fillcolor=SESSION_COLORS[session_name],
                    layer="below",
                    line_width=0,
                    annotation_text=session_name.upper()[:3],
                    annotation_position="top left",
                    annotation_font_size=8,
                    annotation_font_color="gray",
                )
        current_date += timedelta(days=1)


# ============================================================
# Pair Configuration
# ============================================================

def get_pair_config():
    """Get PAIR_CONFIG from the system module."""
    sys.path.insert(0, str(Path(__file__).parent))
    from mars.apps.trading.system.pair_config import PAIR_CONFIG, get_enabled_symbols
    return PAIR_CONFIG, get_enabled_symbols()


PAIR_CONFIG, ENABLED_SYMBOLS = get_pair_config()

# Session symbol selection (defaults to all enabled, user can narrow down)
if "session_symbols" not in st.session_state:
    st.session_state.session_symbols = ENABLED_SYMBOLS.copy()


# ============================================================
# Sidebar
# ============================================================

st.sidebar.title("📊 M.A.R.S. Dashboard")

# Session Symbol Selection (top of sidebar - scopes all panels)
st.sidebar.subheader("🎯 Session Symbols")
st.sidebar.caption("Select which enabled symbols are active for THIS session")
session_symbols = st.sidebar.multiselect(
    "Active Session Symbols",
    options=ENABLED_SYMBOLS,
    default=st.session_state.session_symbols,
    key="sidebar_session_symbols_multiselect",
    help="Only these symbols will be shown in panels below. Must be enabled in PAIR_CONFIG."
)
st.session_state.session_symbols = session_symbols

if not session_symbols:
    st.sidebar.warning("⚠️ No session symbols selected — panels will be empty")

st.sidebar.divider()

# Refresh button
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Symbol selector for price chart
st.sidebar.subheader("Chart Settings")
chart_symbol = st.sidebar.selectbox(
    "Select Symbol for Price Chart",
    options=session_symbols if session_symbols else ENABLED_SYMBOLS,
    index=0,
    key="sidebar_chart_symbol_select",
)

# Time range for chart
chart_hours = st.sidebar.slider(
    "Chart Time Range (hours)",
    min_value=1,
    max_value=168,
    value=24,
)

st.sidebar.divider()

# Chart options
st.sidebar.subheader("Overlay Options")
show_donchian = st.sidebar.checkbox("Donchian Bands", value=True)
show_atr_stops = st.sidebar.checkbox("ATR Stops/Targets", value=True)
show_sessions = st.sidebar.checkbox("Session Shading", value=True)
show_trades = st.sidebar.checkbox("Trade Markers", value=True)

st.sidebar.divider()

# Auto-refresh
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
if auto_refresh:
    st.sidebar.info("Auto-refresh enabled")


# ============================================================
# Main Dashboard
# ============================================================

st.title("M.A.R.S. Multi-Pair Trading Dashboard")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Load all data (tables that actually exist)
signals_df = load_table('signals', 500)
risk_decisions_df = load_table('risk_decisions', 500)
fills_df = load_table('fills', 500)
risk_events_df = load_table('risk_events', 500)
evaluations_df = load_evaluations(200)
kill_switch = load_kill_switch_status()
backup_status = load_backup_status()

# ============================================================
# Panel 1: Account Overview + System Heartbeat
# ============================================================

st.header("1️⃣ Account Overview")

# System Heartbeat - show last evaluation timestamp
if not evaluations_df.empty:
    last_eval = evaluations_df.iloc[0]
    last_eval_time = pd.to_datetime(last_eval.get('timestamp'), errors='coerce')
    if pd.notna(last_eval_time):
        time_since = datetime.now() - last_eval_time.to_pydatetime().replace(tzinfo=None)
        if time_since.total_seconds() < 60:
            heartbeat_status = f"🟢 Last evaluated: {int(time_since.total_seconds())} seconds ago"
        elif time_since.total_seconds() < 300:
            heartbeat_status = f"🟡 Last evaluated: {int(time_since.total_seconds() / 60)} minutes ago"
        else:
            heartbeat_status = f"🔴 Last evaluated: {int(time_since.total_seconds() / 60)} minutes ago (STALE)"
    else:
        heartbeat_status = "⚪ No evaluation timestamp"
else:
    heartbeat_status = "⚪ No evaluations recorded yet"

# Get current equity from kill_switch (most reliable) or compute from fills
current_equity = kill_switch.get('current_equity', 0.0)
if current_equity == 0.0 and not fills_df.empty and 'profit' in fills_df.columns:
    current_equity = 10000.0 + fills_df['profit'].sum()

# Daily P&L - approximate from fills today
daily_pnl = 0.0
if not fills_df.empty and 'timestamp' in fills_df.columns and 'profit' in fills_df.columns:
    fills_df['ts'] = pd.to_datetime(fills_df['timestamp'], errors='coerce')
    today = datetime.now().date()
    today_fills = fills_df[fills_df['ts'].dt.date == today]
    daily_pnl = today_fills['profit'].sum()

# Drawdown
max_dd = kill_switch.get('max_drawdown_pct', 0.0)
if max_dd == 0.0 and current_equity > 0:
    peak = kill_switch.get('peak_equity', current_equity)
    if peak > 0:
        max_dd = (current_equity - peak) / peak * 100

# Kill-switch status
ks_halted = kill_switch.get('kill_switch_halted', False)
ks_drawdown = kill_switch.get('kill_switch_drawdown_at_trigger', 0)

# Consecutive loss halt
cl_halted = kill_switch.get('consecutive_loss_halted', False)
cl_count = kill_switch.get('consecutive_losses', 0)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Equity", f"${current_equity:,.2f}")

with col2:
    st.metric("Daily P&L", f"${daily_pnl:,.2f}")

with col3:
    dd_color = "🔴" if max_dd < -10 else "🟡" if max_dd < -5 else "🟢"
    st.metric("Max Drawdown", f"{dd_color} {max_dd:.2f}%")

with col4:
    ks_status = "🔴 HALTED" if ks_halted else "🟢 ACTIVE"
    st.metric("Kill Switch", ks_status)

with col5:
    cl_status = f"🔴 HALTED ({cl_count})" if cl_halted else f"🟢 OK ({cl_count})"
    st.metric("Consec. Losses", cl_status)

# System Heartbeat - prominently displayed
st.markdown(f"**💓 System Heartbeat:** {heartbeat_status}")

# Risk tier info
tier_info = kill_switch.get('current_tier', {})
if tier_info:
    st.info(f"📋 **Locked Risk Tier**: {tier_info.get('min_equity', 0)}-{tier_info.get('max_equity', '∞')} | "
            f"Max Risk/Trade: {tier_info.get('risk_pct_per_trade', 0)*100:.1f}% | "
            f"Max Concurrent: {tier_info.get('max_concurrent_trades', 0)} | "
            f"RR Target: {tier_info.get('reward_risk_ratio', 0)}")


# ============================================================
# Panel 2: Per-Pair Status
# ============================================================

st.header("2️⃣ Per-Pair Status")

# Filter PAIR_CONFIG to only session symbols
session_pair_config = {s: PAIR_CONFIG[s] for s in session_symbols if s in PAIR_CONFIG}

if not session_pair_config:
    st.info("No session symbols selected. Use the sidebar to choose active symbols.")
else:
    pair_cols = st.columns(len(session_pair_config))

    for idx, (symbol, config) in enumerate(session_pair_config.items()):
            with pair_cols[idx]:
                enabled = config.get('enabled', False)
                badge_class = "enabled-badge" if enabled else "disabled-badge"
                badge_text = "✅ ENABLED" if enabled else "❌ DISABLED"

                st.markdown(f"""
            <div class="metric-card">
                <h4>{symbol}</h4>
                <span class="{badge_class}">{badge_text}</span>
            </div>
            """, unsafe_allow_html=True)

                if not enabled:
                    reason = config.get('disabled_reason', 'No reason provided')
                    st.caption(f"Reason: {reason}")

                # MTF Gate status
                symbol_signals = signals_df[signals_df['symbol'] == symbol] if not signals_df.empty else pd.DataFrame()
                if not symbol_signals.empty:
                    latest = symbol_signals.iloc[0]
                    gate_cols = [c for c in symbol_signals.columns if c.startswith('gate_') or c in ['h1_trend', 'm30_trend', 'm15_trend', 'm5_trend']]
                    if gate_cols:
                        st.write("**MTF Gate:**")
                        for gc in gate_cols:
                            val = latest.get(gc, 'N/A')
                            color = "🟢" if val == 1 else "🔴" if val == -1 else "⚪"
                            st.caption(f"  {gc}: {color} {val}")

                # Last signal
                if not symbol_signals.empty:
                    latest = symbol_signals.iloc[0]
                    signal_val = latest.get('signal', 0)
                    signal_text = "🟢 LONG" if signal_val == 1 else "🔴 SHORT" if signal_val == -1 else "⚪ FLAT"
                    st.caption(f"Last Signal: {signal_text}")
                    st.caption(f"Time: {latest.get('timestamp', 'N/A')}")
                else:
                    st.caption("No signals yet")


# ============================================================
# Panel 3: Last Evaluation (MTF Gate Decisions)
# ============================================================

st.header("3️⃣ Last MTF Gate Evaluation")

if not evaluations_df.empty:
    eval_cols = st.columns(len(session_symbols))
    
    for idx, symbol in enumerate(session_symbols):
        with eval_cols[idx]:
            symbol_evals = evaluations_df[evaluations_df['symbol'] == symbol]
            if not symbol_evals.empty:
                latest = symbol_evals.iloc[0]
                
                st.markdown(f"### {symbol}")
                
                # Gate result with color
                gate_result = latest.get('gate_result', 'UNKNOWN')
                if gate_result == 'ALLOWED':
                    gate_display = "🟢 ALLOWED"
                elif gate_result == 'REJECTED':
                    gate_display = "🔴 REJECTED"
                else:
                    gate_display = f"⚪ {gate_result}"
                st.markdown(f"**Gate:** {gate_display}")
                
                # Rejection reason if rejected
                rejection_reason = latest.get('rejection_reason')
                if rejection_reason:
                    st.caption(f"Reason: {rejection_reason}")
                
                # Timeframe trends
                h1_trend = latest.get('h1_trend')
                m30_trend = latest.get('m30_trend')
                m15_context = latest.get('m15_context')
                
                trend_cols = st.columns(3)
                with trend_cols[0]:
                    trend_val = h1_trend
                    if trend_val == 'BULLISH':
                        trend_display = "🟢 BULLISH"
                    elif trend_val == 'BEARISH':
                        trend_display = "🔴 BEARISH"
                    else:
                        trend_display = f"⚪ {trend_val}" if trend_val else "⚪ N/A"
                    st.caption(f"1H: {trend_display}")
                
                with trend_cols[1]:
                    trend_val = m30_trend
                    if trend_val == 'BULLISH':
                        trend_display = "🟢 BULLISH"
                    elif trend_val == 'BEARISH':
                        trend_display = "🔴 BEARISH"
                    else:
                        trend_display = f"⚪ {trend_val}" if trend_val else "⚪ N/A"
                    st.caption(f"30M: {trend_display}")
                
                with trend_cols[2]:
                    trend_val = m15_context
                    if trend_val == 'BREAKOUT_LONG':
                        trend_display = "🟢 BREAKOUT_LONG"
                    elif trend_val == 'BREAKOUT_SHORT':
                        trend_display = "🔴 BREAKOUT_SHORT"
                    else:
                        trend_display = f"⚪ {trend_val}" if trend_val else "⚪ N/A"
                    st.caption(f"15M: {trend_display}")
                
                # 5M Signal
                breakout_signal = latest.get('breakout_signal', 0)
                signal_text = "🟢 LONG" if breakout_signal == 1 else "🔴 SHORT" if breakout_signal == -1 else "⚪ FLAT"
                st.caption(f"5M Signal: {signal_text}")
                
                # Timestamp
                ts = latest.get('timestamp')
                if ts:
                    st.caption(f"⏰ {ts}")
            else:
                st.markdown(f"### {symbol}")
                st.caption("No evaluations yet")
else:
    st.info("No MTF gate evaluations recorded yet. Start a live session to see evaluations.")

# ============================================================
# Panel 4: Price Chart with Overlays (FULL IMPLEMENTATION)
# ============================================================

st.header(f"4️⃣ Price Chart: {chart_symbol}")

# Get pair config for this symbol
pair_cfg = PAIR_CONFIG.get(chart_symbol, {})
donchian_window = pair_cfg.get("donchian_window", 20)
stop_multiplier = pair_cfg.get("stop_multiplier", 2.0)

# Load OHLCV data
with st.spinner(f"Loading {chart_symbol} price data..."):
    ohlcv_df = load_ohlcv_data(chart_symbol, hours=chart_hours)

if ohlcv_df.empty:
    st.warning(f"No price data available for {chart_symbol}. Check data path in SYMBOL_CONFIGS.")
else:
    # Compute indicators
    donchian_df = compute_donchian_bands(ohlcv_df, window=donchian_window)
    atr_series = compute_atr(ohlcv_df, window=14)
    
    # Get fills for this symbol (trade markers)
    symbol_fills = pd.DataFrame()
    if not fills_df.empty:
        symbol_fills = fills_df[fills_df['symbol'] == chart_symbol].copy()
        if not symbol_fills.empty:
            symbol_fills['timestamp'] = pd.to_datetime(symbol_fills['timestamp'], errors='coerce')
            symbol_fills = symbol_fills.dropna(subset=['timestamp'])
            # Filter to chart time range (using latest available data time as reference)
            if not ohlcv_df.empty:
                latest_time = ohlcv_df.index.max()
                cutoff = latest_time - timedelta(hours=chart_hours)
                symbol_fills = symbol_fills[symbol_fills['timestamp'] >= cutoff]
    
    # Build the candlestick chart
    fig = go.Figure()
    
    # Add session shading first (background layer)
    if show_sessions:
        add_session_shading(fig, ohlcv_df)
    
    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=ohlcv_df.index,
        open=ohlcv_df['open'],
        high=ohlcv_df['high'],
        low=ohlcv_df['low'],
        close=ohlcv_df['close'],
        name=f"{chart_symbol} OHLC",
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350',
    ))
    
    # Donchian bands
    if show_donchian and not donchian_df.empty:
        fig.add_trace(go.Scatter(
            x=donchian_df.index,
            y=donchian_df['donchian_upper'],
            mode='lines',
            line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5, dash='dash'),
            name=f'Donchian Upper ({donchian_window})',
            showlegend=True,
        ))
        fig.add_trace(go.Scatter(
            x=donchian_df.index,
            y=donchian_df['donchian_lower'],
            mode='lines',
            line=dict(color='rgba(33, 150, 243, 0.7)', width=1.5, dash='dash'),
            name=f'Donchian Lower ({donchian_window})',
            showlegend=True,
            fill='tonexty',
            fillcolor='rgba(33, 150, 243, 0.05)',
        ))
    
    # ATR-based stops/targets for open positions
    if show_atr_stops and not atr_series.empty and not symbol_fills.empty:
        # Get the most recent fill (open position)
        latest_fill = symbol_fills.iloc[-1]
        direction = latest_fill.get('direction', '')
        fill_price = latest_fill.get('filled_price', 0)
        fill_time = latest_fill.get('timestamp')
        
        if direction in ['BUY', 'SELL'] and fill_price > 0:
            # Get ATR at fill time (or current)
            if fill_time in atr_series.index:
                atr_at_fill = atr_series.loc[fill_time]
            else:
                # Find nearest ATR value
                atr_at_fill = atr_series.iloc[-1]
            
            if not np.isnan(atr_at_fill) and atr_at_fill > 0:
                stop_dist = stop_multiplier * atr_at_fill
                target_dist = stop_multiplier * 2.5 * atr_at_fill  # 2.5 R:R
                
                if direction == 'BUY':
                    stop_price = fill_price - stop_dist
                    target_price = fill_price + target_dist
                    stop_color = 'red'
                    target_color = 'green'
                else:  # SELL
                    stop_price = fill_price + stop_dist
                    target_price = fill_price - target_dist
                    stop_color = 'red'
                    target_color = 'green'
                
                # Draw horizontal lines from fill time to end of chart
                x_start = fill_time
                x_end = ohlcv_df.index[-1]
                
                # Stop loss line
                fig.add_trace(go.Scatter(
                    x=[x_start, x_end],
                    y=[stop_price, stop_price],
                    mode='lines',
                    line=dict(color=stop_color, width=2, dash='dot'),
                    name=f'Stop Loss ({stop_price:.5f})',
                    showlegend=True,
                ))
                
                # Take profit line
                fig.add_trace(go.Scatter(
                    x=[x_start, x_end],
                    y=[target_price, target_price],
                    mode='lines',
                    line=dict(color=target_color, width=2, dash='dot'),
                    name=f'Take Profit ({target_price:.5f})',
                    showlegend=True,
                ))
                
                # Fill price line
                fig.add_trace(go.Scatter(
                    x=[x_start, x_end],
                    y=[fill_price, fill_price],
                    mode='lines',
                    line=dict(color='blue', width=1.5, dash='solid'),
                    name=f'Entry ({fill_price:.5f})',
                    showlegend=True,
                ))
    
    # Trade markers (entries/exits from fills)
    if show_trades and not symbol_fills.empty:
        for _, fill in symbol_fills.iterrows():
            fill_time = fill['timestamp']
            direction = fill.get('direction', '')
            fill_price = fill.get('filled_price', 0)
            profit = fill.get('profit', 0)
            
            if direction == 'BUY':
                color = 'green'
                symbol_shape = 'triangle-up'
                label = f"BUY @ {fill_price:.5f}"
            elif direction == 'SELL':
                color = 'red'
                symbol_shape = 'triangle-down'
                label = f"SELL @ {fill_price:.5f}"
            else:
                continue
            
            fig.add_trace(go.Scatter(
                x=[fill_time],
                y=[fill_price],
                mode='markers+text',
                marker=dict(symbol=symbol_shape, size=14, color=color, line=dict(width=2, color='white')),
                text=[label],
                textposition='top center' if direction == 'BUY' else 'bottom center',
                textfont=dict(size=9, color=color),
                name=f"{direction} Fill",
                showlegend=False,
            ))
            
            # Add P&L annotation if closed
            if profit != 0:
                pnl_color = 'green' if profit > 0 else 'red'
                fig.add_annotation(
                    x=fill_time,
                    y=fill_price,
                    text=f"${profit:+.2f}",
                    showarrow=True,
                    arrowhead=2,
                    arrowcolor=pnl_color,
                    font=dict(size=8, color=pnl_color),
                    yshift=20 if direction == 'BUY' else -20,
                )
    
    # Layout
    fig.update_layout(
        title=f"{chart_symbol} - M5 Candlesticks (Last {chart_hours}h)",
        xaxis_title="Time (UTC)",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=600,
        template="plotly_white",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        margin=dict(l=50, r=50, t=80, b=50),
    )
    
    # Y-axis formatting for different symbols
    if 'JPY' in chart_symbol:
        fig.update_yaxes(tickformat='.3f')
    elif 'XAU' in chart_symbol:
        fig.update_yaxes(tickformat='.2f')
    else:
        fig.update_yaxes(tickformat='.5f')
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Chart info
    if not ohlcv_df.empty:
        latest_time = ohlcv_df.index.max()
        earliest_time = ohlcv_df.index.min()
        st.caption(f"""
        **Data:** {len(ohlcv_df)} M5 bars from {earliest_time.strftime('%Y-%m-%d %H:%M')} to {latest_time.strftime('%Y-%m-%d %H:%M')} UTC  
        **Donchian Window:** {donchian_window} bars | **ATR Window:** 14 bars | **Stop Multiplier:** {stop_multiplier}x  
        **Session Definitions (UTC):** Asia 00-08 | London 08-13 | Overlap 13-17 | NY 17-22
        """)
    else:
        st.caption("No data available for selected time range.")


# ============================================================
# Panel 4: Signal/Trade Log Table
# ============================================================

st.header("5️⃣ Signal & Trade Log")

log_cols = st.columns([3, 1])

with log_cols[1]:
    filter_symbol = st.selectbox(
        "Filter by Symbol",
        options=["All"] + session_symbols,
        index=0,
        key="panel4_signal_log_symbol_filter",
    )

# Build combined log
combined_rows = []

# Signals
if not signals_df.empty:
    for _, row in signals_df.iterrows():
        if filter_symbol != "All" and row.get('symbol') != filter_symbol:
            continue
        sig = row.get('signal', 0)
        signal_text = "LONG" if sig == 1 else "SHORT" if sig == -1 else "FLAT"
        combined_rows.append({
            'timestamp': row.get('timestamp'),
            'symbol': row.get('symbol'),
            'type': 'SIGNAL',
            'signal': signal_text,
            'decision': 'N/A',
            'risk_pct': f"{row.get('risk_pct', 0)*100:.2f}%" if row.get('risk_pct') else 'N/A',
            'pos_size': row.get('position_size', 'N/A'),
            'fill_price': 'N/A',
            'pnl': 'N/A',
        })

# Risk decisions
if not risk_decisions_df.empty:
    for _, row in risk_decisions_df.iterrows():
        if filter_symbol != "All" and row.get('symbol') != filter_symbol:
            continue
        combined_rows.append({
            'timestamp': row.get('timestamp'),
            'symbol': row.get('symbol'),
            'type': 'RISK_DECISION',
            'signal': 'N/A',
            'decision': row.get('decision', 'N/A'),
            'risk_pct': f"{row.get('per_trade_risk_pct', 0)*100:.2f}%" if row.get('per_trade_risk_pct') else 'N/A',
            'pos_size': 'N/A',
            'fill_price': 'N/A',
            'pnl': 'N/A',
        })

# Fills
if not fills_df.empty:
    for _, row in fills_df.iterrows():
        if filter_symbol != "All" and row.get('symbol') != filter_symbol:
            continue
        combined_rows.append({
            'timestamp': row.get('timestamp'),
            'symbol': row.get('symbol'),
            'type': 'FILL',
            'signal': 'N/A',
            'decision': 'FILLED',
            'risk_pct': 'N/A',
            'pos_size': f"{row.get('filled_lots', 0):.2f}" if row.get('filled_lots') else 'N/A',
            'fill_price': f"{row.get('filled_price', 0):.5f}" if row.get('filled_price') else 'N/A',
            'pnl': f"${row.get('profit', 0):,.2f}" if row.get('profit') else 'N/A',
        })

if combined_rows:
    log_df = pd.DataFrame(combined_rows)
    log_df['timestamp'] = pd.to_datetime(log_df['timestamp'], errors='coerce')
    log_df = log_df.dropna(subset=['timestamp'])
    log_df = log_df.sort_values('timestamp', ascending=False)
    log_df = log_df.head(200)
    
    display_df = log_df.copy()
    display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "timestamp": "Time",
            "symbol": "Symbol",
            "type": "Type",
            "signal": "Signal",
            "decision": "Decision",
            "risk_pct": "Risk %",
            "pos_size": "Pos Size",
            "fill_price": "Fill Price",
            "pnl": "P&L",
        },
    )
else:
    st.info("No signals, risk decisions, or fills recorded yet.")


# ============================================================
# Panel 5: Open Positions
# ============================================================

st.header("6️⃣ Open Positions Across All Symbols")

if not fills_df.empty:
    open_positions = []
    for symbol in session_symbols:
        symbol_fills = fills_df[fills_df['symbol'] == symbol].copy()
        if not symbol_fills.empty:
            latest = symbol_fills.iloc[0]
            direction = latest.get('direction', '')
            if direction in ['BUY', 'SELL']:
                open_positions.append({
                    'symbol': symbol,
                    'side': direction,
                    'size': f"{latest.get('filled_lots', 0):.2f}",
                    'entry_price': f"{latest.get('filled_price', 0):.5f}",
                    'entry_time': latest.get('timestamp', 'N/A'),
                })

    if open_positions:
        pos_df = pd.DataFrame(open_positions)
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")
else:
    st.info("No open positions.")


# ============================================================
# Panel 6: Risk Events Feed
# ============================================================

st.header("7️⃣ Risk Events Feed")

col1, col2 = st.columns([3, 1])

with col2:
    event_filter = st.selectbox(
        "Filter by Event Type",
        options=["All", "MIN_LOT_OVERRIDE", "MTF_ALIGNMENT_REJECTED", "CONSECUTIVE_LOSS_HALT", "KILL_SWITCH", "OTHER"],
        index=0,
        key="panel6_risk_event_type_filter",
    )
    symbol_filter = st.selectbox(
        "Filter by Symbol",
        options=["All"] + session_symbols,
        index=0,
        key="panel6_risk_event_symbol_filter",
    )

if not risk_events_df.empty:
    events = risk_events_df.copy()
    events['timestamp'] = pd.to_datetime(events['timestamp'], errors='coerce')
    events = events.dropna(subset=['timestamp'])
    events = events.sort_values('timestamp', ascending=False)

    if 'details' in events.columns:
        def extract_symbol(details):
            for sym in session_symbols:
                if sym in str(details):
                    return sym
            return 'N/A'
        events['symbol'] = events['details'].apply(extract_symbol)
    
    if event_filter != "All":
        events = events[events['event_type'] == event_filter]
    if symbol_filter != "All":
        events = events[events['symbol'] == symbol_filter]
    
    events = events.head(100)
    
    for _, row in events.iterrows():
        event_type = row.get('event_type', 'UNKNOWN')
        
        if 'HALT' in event_type or 'KILL' in event_type or 'REJECT' in event_type:
            card_class = "risk-event-critical"
        elif 'OVERRIDE' in event_type:
            card_class = "risk-event-warning"
        else:
            card_class = "risk-event-info"
        
        st.markdown(f"""
        <div class="metric-card {card_class}">
            <strong>{row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</strong> | 
            <strong>{event_type}</strong> | 
            {row.get('symbol', 'N/A')}
            <br>
            <small>{row.get('details', 'No message')}</small>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No risk events recorded.")


# ============================================================
# Panel 7: Ops Status
# ============================================================

st.header("8️⃣ Ops Status")

col1, col2 = st.columns(2)

with col1:
    st.subheader("System Status")
    st.write(f"**DB Connection:** {'✅ Connected' if get_db_connection() else '❌ Disconnected'}")
    st.write(f"**Tables Available:** signals, risk_decisions, fills, risk_events")
    st.write(f"**Kill Switch:** {'🔴 HALTED' if ks_halted else '🟢 ACTIVE'}")
    st.write(f"**Consecutive Losses:** {cl_count} {'(HALTED)' if cl_halted else '(OK)'}")

with col2:
    st.subheader("Backup Status")
    for name, status in backup_status.items():
        if status:
            last_backup = status.get('last_backup', 'Never')
            st.write(f"**{name.title()} Backup:** {last_backup}")
        else:
            st.write(f"**{name.title()} Backup:** Not configured")


# ============================================================
# Footer
# ============================================================

st.divider()
st.caption("M.A.R.S. Trading Dashboard — Read-Only Monitoring | "
           "No order placement capability | "
           "Data source: SQLite audit DB (WAL mode)")