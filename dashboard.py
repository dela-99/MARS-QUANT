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
from datetime import datetime, timedelta
from pathlib import Path

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
# Data Access Layer (Read-Only)
# ============================================================

@st.cache_data(ttl=30)
def get_db_connection():
    """Get read-only connection to audit database."""
    db_path = os.path.join(tempfile.gettempdir(), 'mt5_audit_real.db')
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
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


# ============================================================
# Pair Configuration
# ============================================================

def get_pair_config():
    """Get PAIR_CONFIG from the system module."""
    sys.path.insert(0, str(Path(__file__).parent))
    from mars.apps.trading.system.pair_config import PAIR_CONFIG, get_enabled_symbols
    return PAIR_CONFIG, get_enabled_symbols()


PAIR_CONFIG, ENABLED_SYMBOLS = get_pair_config()


# ============================================================
# Sidebar
# ============================================================

st.sidebar.title("📊 M.A.R.S. Dashboard")

# Refresh button
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Symbol selector for price chart
st.sidebar.subheader("Chart Settings")
chart_symbol = st.sidebar.selectbox(
    "Select Symbol for Price Chart",
    options=[s for s in ENABLED_SYMBOLS],
    index=0,
)

# Time range for chart
chart_hours = st.sidebar.slider(
    "Chart Time Range (hours)",
    min_value=1,
    max_value=168,
    value=24,
)

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
kill_switch = load_kill_switch_status()
backup_status = load_backup_status()

# ============================================================
# Panel 1: Account Overview
# ============================================================

st.header("1️⃣ Account Overview")

# Get current equity from kill_switch (most reliable) or compute from fills
current_equity = kill_switch.get('current_equity', 0.0)
if current_equity == 0.0 and not fills_df.empty and 'profit' in fills_df.columns:
    # Approximate equity from cumulative P&L + starting balance
    current_equity = 10000.0 + fills_df['profit'].sum()

# Daily P&L - approximate from fills today
daily_pnl = 0.0
if not fills_df.empty and 'timestamp' in fills_df.columns and 'profit' in fills_df.columns:
    fills_df['ts'] = pd.to_datetime(fills_df['timestamp'], errors='coerce')
    today = datetime.now().date()
    today_fills = fills_df[fills_df['ts'].dt.date == today]
    daily_pnl = today_fills['profit'].sum()

# Drawdown - from kill_switch or approximate
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

pair_cols = st.columns(len(PAIR_CONFIG))

for idx, (symbol, config) in enumerate(PAIR_CONFIG.items()):
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
        
        # MTF Gate status (from latest signals)
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
# Panel 3: Price Chart / Signal Timeline
# ============================================================

st.header(f"3️⃣ Price Chart: {chart_symbol}")

# We don't have live price data in the audit DB, so show a placeholder
# In a real deployment, this would connect to MT5 or data feed
st.info("📈 **Price Chart Placeholder** - In live deployment, this panel connects to MT5/data feed to show real-time price with Donchian bands, ATR stops, and session shading.")

# Show signal history as a timeline instead
if not signals_df.empty:
    symbol_signals = signals_df[signals_df['symbol'] == chart_symbol].copy()
    if not symbol_signals.empty:
        symbol_signals['timestamp'] = pd.to_datetime(symbol_signals['timestamp'], errors='coerce')
        symbol_signals = symbol_signals.dropna(subset=['timestamp'])
        symbol_signals = symbol_signals.sort_values('timestamp')
        
        # Filter by time range
        cutoff = datetime.now() - timedelta(hours=chart_hours)
        symbol_signals = symbol_signals[symbol_signals['timestamp'] >= cutoff]
        
        if not symbol_signals.empty:
            fig = go.Figure()
            
            # Signal markers
            for _, row in symbol_signals.iterrows():
                sig = row.get('signal', 0)
                if sig != 0:
                    color = 'green' if sig == 1 else 'red'
                    symbol_shape = 'triangle-up' if sig == 1 else 'triangle-down'
                    fig.add_trace(go.Scatter(
                        x=[row['timestamp']],
                        y=[0],  # Y position placeholder
                        mode='markers',
                        marker=dict(symbol=symbol_shape, size=12, color=color),
                        name=f"{'Long' if sig == 1 else 'Short'} Signal",
                        showlegend=False,
                    ))
            
            fig.update_layout(
                title=f"Signal Timeline - {chart_symbol} (Last {chart_hours}h)",
                xaxis_title="Time",
                yaxis_title="Signal",
                height=400,
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# Panel 4: Signal/Trade Log Table
# ============================================================

st.header("4️⃣ Signal & Trade Log")

# Merge signals, risk_decisions, fills
log_cols = st.columns([3, 1])

with log_cols[1]:
    filter_symbol = st.selectbox(
        "Filter by Symbol",
        options=["All"] + list(PAIR_CONFIG.keys()),
        index=0,
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
    log_df = log_df.head(200)  # Limit display
    
    # Format for display
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

st.header("5️⃣ Open Positions Across All Symbols")

# Get current open positions from fills (heuristic: latest fill per symbol)
if not fills_df.empty:
    open_positions = []
    for symbol in PAIR_CONFIG.keys():
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

st.header("6️⃣ Risk Events Feed")

col1, col2 = st.columns([3, 1])

with col2:
    event_filter = st.selectbox(
        "Filter by Event Type",
        options=["All", "MIN_LOT_OVERRIDE", "MTF_ALIGNMENT_REJECTED", "CONSECUTIVE_LOSS_HALT", "KILL_SWITCH", "OTHER"],
        index=0,
    )
    symbol_filter = st.selectbox(
        "Filter by Symbol",
        options=["All"] + list(PAIR_CONFIG.keys()),
        index=0,
    )

if not risk_events_df.empty:
    events = risk_events_df.copy()
    events['timestamp'] = pd.to_datetime(events['timestamp'], errors='coerce')
    events = events.dropna(subset=['timestamp'])
    events = events.sort_values('timestamp', ascending=False)
    
    # Extract symbol from details if available (risk_events table doesn't have symbol column)
    if 'details' in events.columns:
        def extract_symbol(details):
            for sym in PAIR_CONFIG.keys():
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

st.header("7️⃣ Ops Status")

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