# src/feature_engineering_advanced.py
import pandas_ta as ta



def calculate_all_indicators(df):
    """Calculates a rich set of technical indicators on the DataFrame."""
    print("Calculating ~20 technical indicators...")
    print("--- Starting Advanced Feature Engineering ---")
    
    # Use the pandas_ta Strategy builder for efficiency
    # We will list the indicators mentioned in the paper.
    # Note: Some names might be slightly different in pandas_ta.
    # 'kind' is the indicator name, you can find them in the pandas_ta documentation.
    my_study = ta.Study(
        name="RL Paper Indicators",
        description="A collection of ~20 indicators from the RL paper",
        ta=[
            # Momentum Indicators
            {"kind": "rsi"},          # Relative Strength Index
            {"kind": "mom"},          # Momentum
            {"kind": "stoch"},        # Stochastic Oscillator (%K and %D)
            {"kind": "macd"},         # Moving Average Convergence Divergence
            {"kind": "cci"},          # Commodity Channel Index
            {"kind": "roc"},          # Rate of Change
            {"kind": "cmo"},          # Chande Momentum Oscillator
            {"kind": "stochrsi"},     # Stochastic RSI
            {"kind": "willr"},        # Williams %R (similar to Ultimate Oscillator)
            
            # Trend Indicators
            {"kind": "adx"},          # Average Directional Movement Index
            {"kind": "trix"},         # TRIX
            {"kind": "psar"},         # Parabolic SAR
            {"kind": "tema"},         # Triple Exponential Moving Average
            {"kind": "trima"},        # Triangular Moving Average
            {"kind": "wma"},          # Weighted Moving Average
            {"kind": "dema"},         # Double Exponential Moving Average
            
            # Volume and Volatility Indicators
            {"kind": "mfi"},          # Money Flow Index
            {"kind": "bop"},          # Balance of Power
            {"kind": "atr"},          # Average True Range
        ]
    )
    
    # Run the strategy on the DataFrame (this appends all columns)
    df.ta.study(my_study)
    
    return df