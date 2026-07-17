# M.A.R.S. Research Backlog

Prioritized work to mature the system beyond the V1 Hyp-A baseline.

---

## P0 — Correctness & rigor

- [ ] **Walk-forward validation** for Hyp-A XGBoost (rolling train → test windows)
- [ ] **Purged / embargoed CV** when using overlapping features
- [ ] **Retrain PyTorch models** with chronological splits only; re-report metrics
- [ ] **Fix sequence scaler leakage**: fit scaler on train folds only
- [ ] **Align backtest periods** with model train/test day indices (not raw bar 80%)
- [ ] **Document point-in-time** for every feature column in a feature registry

## P1 — Market realism

- [ ] **Spread / slippage-aware backtest** for XAUUSD (broker-specific or historical)
- [ ] **Session open execution model** (fill at first London H1 open bar)
- [ ] **Stop-loss / take-profit policies** tied to ATR
- [ ] **Max daily loss / kill-switch** in risk policy
- [ ] **Swap / holding cost** if positions span sessions

## P2 — Strategy & regimes

- [ ] **Regime classification** (vol / trend / range) before signal application
- [ ] **Hypothesis B**: London morning → LON/NY overlap
- [ ] **Hypothesis C**: Asia+London → New York
- [ ] **Confidence thresholds** and selective trading (trade quality scoring)
- [ ] **Session studies** specific to XAUUSD (Asia range vs London breakout stats)

## P3 — Platform engineering

- [ ] Experiment tracking (MLflow or lightweight JSON run store)
- [ ] Config system (YAML) for symbols, sessions, model params
- [ ] Refactor MT5 bots onto shared FE + model interfaces
- [ ] CI: unit tests + smoke pipeline on sample data
- [ ] Feature store / cached daily feature builds
- [ ] Multi-timeframe data support (M15, H4) with consistent schemas

## P4 — Copilot (later)

- [ ] Observer mode: explain last signal + key features
- [ ] Assisted mode: operator confirms setups
- [ ] Chart annotation hooks
- [ ] Audit log of decisions (model version, features hash, risk decision)

---

## Open research questions

1. Is Asia→London edge stable post-2020 regime shifts for gold?
2. Do advanced TA features improve OOS after proper walk-forward, or only in-sample?
3. Can sequence models beat XGBoost when both use identical chronological protocol?
4. What is the minimum confidence threshold that improves expectancy after costs?
