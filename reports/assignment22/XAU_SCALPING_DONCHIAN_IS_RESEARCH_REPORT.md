# XAU-SCALPING-DONCHIAN-001 In-Sample Research Report

**Strategy ID**: XAU-SCALPING-DONCHIAN-001
**Generated**: 2026-11-25T15:34:15.986126+00:00

## Configuration
```json
{
  "params": {
    "donchian_lookback": 20,
    "ema_period": 50,
    "ema_slope_bars": 5,
    "atr_period": 14,
    "atr_stop_multiplier": 2.0,
    "risk_fraction": 0.01,
    "starting_equity": 10000.0,
    "allow_short": true,
    "allow_long": true,
    "execution_timeframe": "M5",
    "max_holding_bars": 6,
    "max_holding_minutes": 30,
    "use_m1_context": false,
    "m1_donchian_lookback": 20,
    "m1_atr_period": 14,
    "m1_atr_stop_multiplier": 2.0,
    "account_equity_usd": 30.0,
    "leverage": 2000,
    "min_lot": 0.01,
    "max_lot": 200.0,
    "lot_step": 0.01,
    "contract_size": 100.0,
    "point_size": 0.001,
    "pip_size": 0.01
  },
  "instrument_spec": {
    "symbol": "XAUUSDm",
    "contract_size": 100.0,
    "pip_size": 0.01,
    "point_size": 0.001,
    "quote_currency": "USD",
    "volume_min": 0.01,
    "volume_max": 200.0,
    "volume_step": 0.01,
    "volume_spec_source": "mt5.live",
    "spec_source": "mt5.live",
    "pip_value_per_lot_usd": 1.0,
    "point_value_per_lot_usd": 0.1
  },
  "cost_model": {
    "spread_multiplier": 1.0,
    "commission_per_lot_round_trip": 0.0,
    "slippage_points": 0.0,
    "swap_per_lot_night": 0.0,
    "use_observed_spread": true,
    "fallback_spread_points": 200.0,
    "cost_source": "observed_bar_spread"
  },
  "execution_model": {
    "entry_fill": "next_bar_open",
    "stop_fill": "gap_aware_conservative",
    "same_bar_priority": "worst_price",
    "exit_fill": "next_bar_open",
    "time_exit_fill": "next_bar_open",
    "reversal_policy": "opposite_signal_ignored"
  },
  "data": {
    "m1": "data/processed/xauusdm/m1/v1.2.0/data.parquet",
    "m5": "data/processed/xauusdm/m5/v1.2.0/data.parquet",
    "h1": "data/processed/xauusdm/h1/v1.2.0/data.parquet"
  }
}
```

## Baseline Metrics (Version 1 Equivalent: M5 execution, 30-min max hold)
- **trade_count**: 2975
- **win_rate**: 0.3751
- **avg_win_usd**: 11.4134
- **avg_loss_usd**: -12.1883
- **expectancy_usd**: -3.3347
- **expectancy_r**: -0.1833
- **profit_factor**: 0.5622
- **gross_pnl_usd**: -9920.7701
- **net_pnl_usd**: -9920.7701
- **gross_return**: -0.9921
- **net_return**: -0.9921
- **starting_equity**: 10000.0000
- **final_equity**: 79.2299
- **max_drawdown_usd**: -9980.8643
- **max_drawdown_pct**: -0.9923
- **drawdown_max_days**: 1260
- **drawdown_mean_days**: 630.0000
- **sharpe**: -4.8890
- **sortino**: -2.9785
- **exposure**: 0.0623
- **turnover_annualised**: 164758.0522
- **traded_notional_usd**: 61408184.7730
- **avg_holding_minutes**: 34.6034
- **median_holding_minutes**: 25.0000
- **max_holding_minutes**: 4405.0000
- **total_commission_usd**: 0.0000
- **total_swap_usd**: 0.0000
- **observed_spread_cost_usd**: 8244.3590
- **pre_spread_net_pnl_usd**: -1676.4111
- **pre_spread_expectancy_usd**: -0.5635
- **long_trades**: 1517
- **short_trades**: 1458
- **long_net_pnl_usd**: -4320.3384
- **short_net_pnl_usd**: -5600.4317
- **long_win_rate**: 0.3883
- **short_win_rate**: 0.3615
- **bars_in_market**: 15226
- **total_bars**: 244470
- **rejected_signals**: 8583
- **exit_breakdown**: {'time_exits': 1970, 'stop_exits': 896, 'mid_exits': 109, 'end_of_data_exits': 0}
- **conventions**: {'sharpe': 'daily mark-to-market equity returns, annualised sqrt(252)', 'sortino': 'daily returns, downside deviation (negative returns only), sqrt(252)', 'drawdown': 'mark-to-market equity curve, peak-to-trough', 'profit_factor': 'gross winning net P&L / gross losing net P&L', 'exposure': 'fraction of execution bars with an open position', 'turnover': 'traded notional / average equity, annualised'}

## Current Configuration Metrics
- **trade_count**: 2975
- **win_rate**: 0.3751
- **avg_win_usd**: 11.4134
- **avg_loss_usd**: -12.1883
- **expectancy_usd**: -3.3347
- **expectancy_r**: -0.1833
- **profit_factor**: 0.5622
- **gross_pnl_usd**: -9920.7701
- **net_pnl_usd**: -9920.7701
- **gross_return**: -0.9921
- **net_return**: -0.9921
- **starting_equity**: 10000.0000
- **final_equity**: 79.2299
- **max_drawdown_usd**: -9980.8643
- **max_drawdown_pct**: -0.9923
- **drawdown_max_days**: 1260
- **drawdown_mean_days**: 630.0000
- **sharpe**: -4.8890
- **sortino**: -2.9785
- **exposure**: 0.0623
- **turnover_annualised**: 164758.0522
- **traded_notional_usd**: 61408184.7730
- **avg_holding_minutes**: 34.6034
- **median_holding_minutes**: 25.0000
- **max_holding_minutes**: 4405.0000
- **total_commission_usd**: 0.0000
- **total_swap_usd**: 0.0000
- **observed_spread_cost_usd**: 8244.3590
- **pre_spread_net_pnl_usd**: -1676.4111
- **pre_spread_expectancy_usd**: -0.5635
- **long_trades**: 1517
- **short_trades**: 1458
- **long_net_pnl_usd**: -4320.3384
- **short_net_pnl_usd**: -5600.4317
- **long_win_rate**: 0.3883
- **short_win_rate**: 0.3615
- **bars_in_market**: 15226
- **total_bars**: 244470
- **rejected_signals**: 8583
- **exit_breakdown**: {'time_exits': 1970, 'stop_exits': 896, 'mid_exits': 109, 'end_of_data_exits': 0}
- **conventions**: {'sharpe': 'daily mark-to-market equity returns, annualised sqrt(252)', 'sortino': 'daily returns, downside deviation (negative returns only), sqrt(252)', 'drawdown': 'mark-to-market equity curve, peak-to-trough', 'profit_factor': 'gross winning net P&L / gross losing net P&L', 'exposure': 'fraction of execution bars with an open position', 'turnover': 'traded notional / average equity, annualised'}

## Parameter Comparison (One-Factor-at-a-Time)
| factor              | value   | baseline   |   trade_count |   win_rate |   expectancy_usd |   expectancy_r |   profit_factor |   net_pnl_usd |   net_return |   max_drawdown_pct |   sharpe |   sortino |   exposure |   avg_holding_minutes |
|:--------------------|:--------|:-----------|--------------:|-----------:|-----------------:|---------------:|----------------:|--------------:|-------------:|-------------------:|---------:|----------:|-----------:|----------------------:|
| execution_timeframe | M5      | True       |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| max_holding_bars    | 3       | False      |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| max_holding_bars    | 6       | True       |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| max_holding_bars    | 12      | False      |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| max_holding_bars    | 24      | False      |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| atr_stop_multiplier | 1.5     | False      |          2512 |   0.341561 |         -3.95994 |      -0.231839 |        0.531492 |      -9947.37 |    -0.994737 |          -0.994875 | -4.38904 |  -2.51178 |  0.0462838 |               29.6338 |
| atr_stop_multiplier | 2.0     | True       |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| atr_stop_multiplier | 2.5     | False      |          3318 |   0.380952 |         -2.98185 |      -0.156771 |        0.537311 |      -9893.79 |    -0.989379 |          -0.98947  | -5.08183 |  -3.23909 |  0.0732728 |               36.9274 |
| atr_stop_multiplier | 3.0     | False      |          3731 |   0.385956 |         -2.64293 |      -0.131131 |        0.532291 |      -9860.76 |    -0.986076 |          -0.98626  | -5.43789 |  -3.44942 |  0.0844071 |               36.7663 |
| donchian_lookback   | 15      | False      |          3164 |   0.378951 |         -3.13836 |      -0.176959 |        0.543757 |      -9929.76 |    -0.992976 |          -0.993143 | -4.79341 |  -2.88707 |  0.0660081 |               33.1432 |
| donchian_lookback   | 20      | True       |          2975 |   0.375126 |         -3.33471 |      -0.183334 |        0.562154 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |  -2.9785  |  0.0622817 |               34.6034 |
| donchian_lookback   | 25      | False      |          3084 |   0.374838 |         -3.21451 |      -0.174008 |        0.59026  |      -9913.56 |    -0.991356 |          -0.991376 | -4.82514 |  -3.09741 |  0.0649446 |               33.189  |
| donchian_lookback   | 30      | False      |          2996 |   0.371162 |         -3.30779 |      -0.177732 |        0.585568 |      -9910.14 |    -0.991014 |          -0.991034 | -4.874   |  -3.14978 |  0.0628462 |               33.3545 |

## Cost Sensitivity
| factor             |   value | baseline   |   trade_count |   expectancy_usd |   net_pnl_usd |   net_return |   max_drawdown_pct |   sharpe |   observed_spread_cost_usd |   total_commission_usd |
|:-------------------|--------:|:-----------|--------------:|-----------------:|--------------:|-------------:|-------------------:|---------:|---------------------------:|-----------------------:|
| spread_multiplier  |     1   | True       |          2975 |         -3.33471 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |                    8244.36 |                 nan    |
| spread_multiplier  |     1.5 | False      |          2179 |         -4.55831 |      -9932.56 |    -0.993256 |          -0.993398 | -5.21835 |                    9149.19 |                 nan    |
| spread_multiplier  |     2   | False      |          1640 |         -6.06018 |      -9938.7  |    -0.99387  |          -0.994012 | -5.18452 |                    9904.7  |                 nan    |
| spread_multiplier  |     3   | False      |          1066 |         -9.33801 |      -9954.31 |    -0.995431 |          -0.995458 | -4.61235 |                   10819.3  |                 nan    |
| commission_per_lot |     0   | True       |          2975 |         -3.33471 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |                     nan    |                   0    |
| commission_per_lot |     1   | False      |          2924 |         -3.39265 |      -9920.12 |    -0.992012 |          -0.992321 | -4.82963 |                     nan    |                 332.44 |
| commission_per_lot |     2   | False      |          2831 |         -3.50474 |      -9921.91 |    -0.992191 |          -0.992435 | -4.87742 |                     nan    |                 644.34 |
| commission_per_lot |     5   | False      |          2569 |         -3.86297 |      -9923.98 |    -0.992398 |          -0.992491 | -4.99881 |                     nan    |                1470.35 |
| slippage_points    |     0   | True       |          2975 |         -3.33471 |      -9920.77 |    -0.992077 |          -0.992305 | -4.88901 |                     nan    |                 nan    |
| slippage_points    |     1   | False      |          2964 |         -3.34692 |      -9920.27 |    -0.992027 |          -0.992353 | -4.88721 |                     nan    |                 nan    |
| slippage_points    |     2   | False      |          2964 |         -3.34687 |      -9920.12 |    -0.992012 |          -0.992336 | -4.88746 |                     nan    |                 nan    |
| slippage_points    |     5   | False      |          2934 |         -3.38146 |      -9921.2  |    -0.99212  |          -0.992389 | -4.87096 |                     nan    |                 nan    |

## $30 Account Feasibility Analysis (Exness XAUUSDm)
- **min_lot**: 0.01
- **min_stop_distance_price**: 2.09198713085234
- **min_risk_per_trade_usd**: 2.09198713085234
- **risk_fraction**: 0.01
- **equity_usd**: 30.0
- **margin_required_usd**: 0.0104599356542617
- **free_margin_after_entry_usd**: 29.98954006434574
- **spread_cost_per_trade_usd**: 0.20139572994713115
- **commission_per_trade_usd**: 0.0
- **total_cost_per_trade_usd**: 0.20139572994713115
- **feasible**: False
- **rejection_reason**: min volume breach: 0.01 lots risks $2.09 > budget $0.30
- **required_lots_exact**: 0.0014340432384867049
- **risk_at_min_lot_usd**: 2.09198713085234

**Conclusion**: XAUUSDm trading is INFEASIBLE at $30 under verified Exness conditions. Minimum cash risk per executable trade: $2.09. Strategy classified as infeasible at intended account size.

## Benchmarks
### Buy & Hold
- **name**: buy_and_hold
- **entry_price**: 1822.819
- **exit_price**: 2606.33
- **lots**: 0.05486008210359888
- **notional_usd**: 10000.0
- **net_pnl_usd**: 4298.347778907286
- **net_return**: 0.4298347778907286
- **sharpe**: 0.6666639261908326
- **max_drawdown_pct**: -0.21925072965189318
- **note**: unlevered full-equity long from first bar, one spread on entry, marked at bid

### No Trade
- **name**: no_trade
- **net_pnl_usd**: 0.0
- **net_return**: 0.0
- **sharpe**: 0.0
- **max_drawdown_pct**: 0.0
- **note**: baseline: no position, no cost, zero return

## Yearly Breakdown
|      |   trades |   win_rate |   net_pnl_usd |   gross_pnl_usd |   profit_factor |     avg_r |   long_trades |   short_trades |
|-----:|---------:|-----------:|--------------:|----------------:|----------------:|----------:|--------------:|---------------:|
| 2021 |      999 |   0.368368 |   -8458.54    |     -8458.54    |        0.553108 | -0.187482 |           522 |            477 |
| 2022 |     1692 |   0.393026 |   -1368.3     |     -1368.3     |        0.617415 | -0.156615 |           841 |            851 |
| 2023 |      276 |   0.293478 |     -90.7429  |       -90.7429  |        0.395309 | -0.321959 |           149 |            127 |
| 2024 |        8 |   0.25     |      -3.18471 |        -3.18471 |        0.223943 | -0.533664 |             5 |              3 |

## Session Breakdown
|         |   trades |   win_rate |   net_pnl_usd |     avg_r |   profit_factor |
|:--------|---------:|-----------:|--------------:|----------:|----------------:|
| Asia    |     1088 |   0.379596 |      -3688.12 | -0.18078  |        0.536441 |
| Late    |      314 |   0.315287 |      -1085.87 | -0.278331 |        0.518537 |
| London  |      591 |   0.384095 |      -1887.79 | -0.173684 |        0.552893 |
| NY      |      494 |   0.366397 |      -1809.41 | -0.183233 |        0.512242 |
| Overlap |      488 |   0.401639 |      -1449.58 | -0.139688 |        0.678927 |

## Exit Reason Breakdown
|             |   donchian_mid_exit |         stop |   time_exit |
|:------------|--------------------:|-------------:|------------:|
| trades      |         109         |    896       | 1970        |
| net_pnl_usd |       -1434.15      | -15197.7     | 6711.06     |
| avg_r       |          -0.729559  |     -1.00617 |    0.221131 |
| win_rate    |           0.0366972 |      0       |    0.564467 |