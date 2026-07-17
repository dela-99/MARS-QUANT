import MetaTrader5 as mt5
import pandas as pd
import joblib
import pytz
from datetime import datetime, time, timedelta, timezone
import time as time_sleep # Use a different alias to avoid confusion
import logging # The professional way to track events

import sys
import os
from pathlib import Path

current_dir = Path(os.getcwd())
sys.path.append(str(current_dir.parent))

from config import HYP_A_XGB_ACCOUNT_INFO
from feature_engineering_utils import calculate_all_indicators
# --- CONFIGURATION ---
# All user-adjustable settings are here
CONFIG = {
    "symbol": "XAUUSD",
    "lot_size": HYP_A_XGB_ACCOUNT_INFO.get('lot_size'),
    "model_path": "../../models/xgb_classifier_hyp_a_TUNED_paper_v3_final.joblib",
    "columns_path": "../../models/xgb_classifier_hyp_a_TUNED_paper_v3_final_model_columns.joblib",
    "mt5_account": HYP_A_XGB_ACCOUNT_INFO.get('mt5_account'),
    "mt5_password": HYP_A_XGB_ACCOUNT_INFO.get('mt5_password'),
    "mt5_server": HYP_A_XGB_ACCOUNT_INFO.get('mt5_server'),
    "magic_number": HYP_A_XGB_ACCOUNT_INFO.get('magic_number'), # A unique ID for trades placed by this bot
    "log_file": "logs/hyp_a_xgb_trading_bot_v1_paper.log"
}

# --- LOGGING SETUP ---
# This sets up a logger that writes messages to a file.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG["log_file"]),
        logging.StreamHandler() # Also print logs to the console
    ]
)

def connect_to_mt5():
    """Initializes and connects to the MetaTrader 5 terminal."""
    if not mt5.initialize(login=CONFIG["mt5_account"], password=CONFIG["mt5_password"], server=CONFIG["mt5_server"]):
        logging.error(f"MT5 initialize() failed, error code = {mt5.last_error()}")
        return False
    logging.info("MT5 connection successful.")
    return True

def get_trade_signal():
    """Orchestrates the process of getting data, engineering features, and making a prediction."""
    try:
        logging.info("Generating new trade signal...")
        # 1. Get latest data
        rates = mt5.copy_rates_from_pos(CONFIG["symbol"], mt5.TIMEFRAME_H1, 0, 400) # Get more data for longer indicators
        df_raw = pd.DataFrame(rates)
        df_raw['time'] = pd.to_datetime(df_raw['time'], unit='s')
        df_raw.set_index('time', inplace=True)
        
        # --- Rename volume column BEFORE calculating indicators ---
        df_raw.rename(columns={'tick_volume': 'volume'}, inplace=True)
        
        # 2. Run feature engineering pipeline
        df = df_raw.tz_localize('UTC')
        df = calculate_all_indicators(df)
        
        # Handle PSAR specifically
        psar_long_col = 'PSARl_0.02_0.2'
        psar_short_col = 'PSARs_0.02_0.2'
        if psar_long_col in df.columns and psar_short_col in df.columns:
            df['PSAR'] = df[psar_long_col].fillna(df[psar_short_col])
            df.drop(columns=[psar_long_col, psar_short_col], inplace=True)
        
        # Forward fill all other missing values
        df.ffill(inplace=True)
        logging.info("Indicators calculated and missing values filled.")
        
        # 3. Extract the feature vector for the current day
        today = datetime.now(timezone.utc).date()
        previous_day = today - timedelta(days=1)
        
        asia_part1 = df.loc[str(previous_day)].between_time('22:00', '23:59')
        asia_part2 = df.loc[str(today)].between_time('00:00', '07:59')
        asia_session = pd.concat([asia_part1, asia_part2])

        if asia_session.empty:
            logging.warning("Asian session data is empty. Cannot generate signal.")
            return None
        
        end_of_asia_ts = asia_session.index[-1]
        
        # Get the full row of indicator values at the end of the session
        latest_indicators = df.loc[end_of_asia_ts]
        
        # Build the feature dictionary
        features = {
            'day_of_week': today.weekday(),
            'asia_return': (asia_session['close'].iloc[-1] - asia_session['open'].iloc[0]) / asia_session['open'].iloc[0],
            'asia_range': asia_session['high'].max() - asia_session['low'].min(),
        }
        features.update(latest_indicators) # Add all indicator values
        
        features_df = pd.DataFrame([features])
        
        # 4. Load model, columns, and make prediction
        model = joblib.load(CONFIG["model_path"])
        model_columns = joblib.load(CONFIG["columns_path"])
        
        # CRITICAL: Ensure the DataFrame has the exact same columns in the exact same order
        final_features_df = features_df.reindex(columns=model_columns, fill_value=0)
        
        prediction = model.predict(final_features_df)[0]
        logging.info(f"Signal generated successfully. Prediction: {'BULLISH' if prediction==1 else 'BEARISH'}")
        return int(prediction)

    except Exception as e:
        logging.error(f"An error occurred in get_trade_signal: {e}", exc_info=True) # exc_info=True gives more detail
        return None

def execute_trade(action_type):
    """Sends a trade order to the MT5 terminal."""
    symbol = CONFIG["symbol"]
    lot_size = CONFIG["lot_size"]
    
    # Get the correct price for the action
    price = mt5.symbol_info_tick(symbol).ask if action_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
    
    # Build the trade request dictionary
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": action_type,
        "price": price,
        "deviation": 20, # Slippage tolerance in points
        "magic": CONFIG["magic_number"],
        "comment": "Hyp A XGBoost Bot Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"Order send failed, retcode={result.retcode}, comment={result.comment}")
    else:
        logging.info(f"Order successful: {'BUY' if action_type == mt5.ORDER_TYPE_BUY else 'SELL'} {lot_size} {symbol} at {price}. Order #{result.order}")
    return result

# def close_all_trades():
#     """Closes all open positions for the specified symbol managed by this bot."""
#     positions = mt5.positions_get(symbol=CONFIG["symbol"])
#     if positions is None:
#         logging.info("No open positions to close.")
#         return

#     closed_count = 0
#     for pos in positions:
#         # Only close positions opened by this bot (magic number check)
#         if pos.magic == CONFIG["magic_number"]:
#             # Logic to close the position
#             # (Simplified here - a full implementation would check buy/sell and create an opposing order)
#             # For simplicity, we create a generic close request.
#             # This part requires careful implementation based on MT5 docs for market close orders.
#             # A robust implementation is more complex, for now we will just log.
#             logging.info(f"Closing position #{pos.ticket}...")
#             # Here you would call mt5.order_send with a close request
#             closed_count += 1
    
#     if closed_count == 0:
#         logging.info("No positions managed by this bot were found.")
#     else:
#         logging.info(f"Closed {closed_count} positions.")


# In src/trading_bot.py, replace the old close_all_trades function

def close_all_trades():
    """
    Finds all open positions for the bot's symbol and magic number,
    then sends the correct opposing orders to close them.
    """
    symbol = CONFIG["symbol"]
    magic_number = CONFIG["magic_number"]
    
    # Get all open positions
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        logging.info("No open positions to close.")
        return

    logging.info(f"Found {len(positions)} total open positions. Checking for bot trades...")
    
    closed_count = 0
    # Loop through each position
    for pos in positions:
        # IMPORTANT: Only manage trades opened by this specific bot
        if pos.magic == magic_number:
            
            # Determine the correct closing order type
            # If it's a BUY position, we need to SELL to close.
            if pos.type == mt5.ORDER_TYPE_BUY:
                action_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(symbol).bid
                logging.info(f"Preparing to CLOSE BUY position #{pos.ticket} with a SELL order.")
            # If it's a SELL position, we need to BUY to close.
            elif pos.type == mt5.ORDER_TYPE_SELL:
                action_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(symbol).ask
                logging.info(f"Preparing to CLOSE SELL position #{pos.ticket} with a BUY order.")
            else:
                logging.warning(f"Unknown position type for ticket #{pos.ticket}. Skipping.")
                continue

            # Create the closing trade request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket, # The ticket of the position to close
                "symbol": symbol,
                "volume": pos.volume, # Must close the exact same volume
                "type": action_type,
                "price": price,
                "deviation": 20,
                "magic": magic_number,
                "comment": "Bot Closing Trade",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            # Send the closing order
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logging.error(f"Failed to close position #{pos.ticket}. Reason: {result.comment} (Retcode: {result.retcode})")
            else:
                logging.info(f"Successfully sent close order for position #{pos.ticket}. Result: {result.comment}")
                closed_count += 1
    
    if closed_count > 0:
        logging.info(f"Finished closing {closed_count} positions.")
    else:
        logging.info("No open positions managed by this bot were found to close.")


# In src/trading_bot.py, add this new function

def log_daily_pnl():
    """
    Calculates and logs the total profit/loss for all trades
    closed today that were managed by this bot.
    """
    magic_number = CONFIG["magic_number"]
    
    # Define the time range for today (from midnight to now)
    utc_from = datetime.utcnow().replace(hour=0, minute=0, second=0)
    utc_to = datetime.utcnow()
    
    # Get the history of deals (executed trades) in that time range
    deals = mt5.history_deals_get(utc_from, utc_to)
    
    if deals is None or len(deals) == 0:
        logging.info("No deals found in history for today.")
        return

    daily_profit = 0.0
    trade_count = 0
    
    for deal in deals:
        # Filter for our bot's trades and only count "out" deals (closing trades)
        if deal.magic == magic_number and deal.entry == mt5.DEAL_ENTRY_OUT:
            daily_profit += deal.profit
            trade_count += 1
            
    if trade_count > 0:
        logging.info("--- DAILY P&L SUMMARY ---")
        logging.info(f"Total trades closed today: {trade_count}")
        logging.info(f"Total Profit/Loss: ${daily_profit:.2f}")
        logging.info("---------------------------")
    else:
        logging.info("No trades managed by this bot were closed today.")

def main():
    """The main loop that runs the bot."""
    logging.info("Starting trading bot...")
    if not connect_to_mt5():
        return # Exit if connection fails

    london_tz = pytz.timezone('Europe/London')
    trade_placed_today = False
    last_checked_day = None

    while True:
        try:
            # now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
            now_utc = datetime.now(timezone.utc).replace(tzinfo=pytz.utc)
            current_day = now_utc.date()

            # Reset the trade flag at the start of a new day
            if current_day != last_checked_day:
                trade_placed_today = False
                last_checked_day = current_day
                logging.info(f"New trading day: {current_day}. Ready for signals.")

            # --- Define Dynamic Session Times ---
            london_open_local = london_tz.localize(datetime.combine(current_day, time(8, 0)))
            london_close_local = london_tz.localize(datetime.combine(current_day, time(17, 0)))
            london_open_utc = london_open_local.astimezone(pytz.utc)
            london_close_utc = london_close_local.astimezone(pytz.utc)

            # --- TRADING LOGIC ---
            # 1. Check if it's time to open a trade
            if now_utc >= london_open_utc and not trade_placed_today and now_utc.weekday() < 5: # Monday-Friday
                logging.info("London session open. Attempting to place trade.")
                
                # First, close any lingering positions from yesterday.
                close_all_trades()

                signal = get_trade_signal()
                if signal is not None:
                    if signal == 1: # Bullish
                        execute_trade(mt5.ORDER_TYPE_BUY)
                    elif signal == 0: # Bearish
                        execute_trade(mt5.ORDER_TYPE_SELL)
                    
                    trade_placed_today = True # Mark that we've traded
                else:
                    logging.warning("Could not get a valid signal. No trade placed.")
                    trade_placed_today = True # Still mark as true to prevent retrying

            # 2. Check if it's time to close the day's trade
            if now_utc >= london_close_utc and trade_placed_today:
                logging.info("London session close. Closing all open positions.")
                close_all_trades()
                # The trade flag will be reset on the next day's rollover
                
                # --- NEW LINE ADDED HERE ---
                log_daily_pnl()
                
                # We need to ensure we don't try to close again today.
                # A simple way is to "end the day" for the bot.
                trade_placed_today = False # Reset the flag
                logging.info("End of day procedure complete. Waiting for next trading day.")
            
            time_sleep.sleep(60) # Wait for 60 seconds before checking again

        except KeyboardInterrupt:
            logging.info("Bot stopped by user.")
            mt5.shutdown()
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}")
            time_sleep.sleep(300) # Wait 5 minutes before retrying on major error

if __name__ == "__main__":
    main()