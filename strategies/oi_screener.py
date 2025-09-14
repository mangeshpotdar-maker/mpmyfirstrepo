import configparser
import pandas as pd
from kiteconnect import KiteConnect
import datetime
import os
import sys
import logging
import time

# Add parent directory to path to import utils and alerts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import is_market_open, setup_logging
import alerts
import report_logger

# In-memory cache for initial OI data. This is reset daily by the main loop.
oi_data_cache = {}
last_reset_date = None

def get_kite_client():
    """Initializes and returns a KiteConnect client instance."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    api_key = config['zerodha']['api_key']
    access_token = config['zerodha']['access_token']
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_nfo_instruments(kite):
    """Fetches and caches NFO instruments list."""
    instruments_file = 'nfo_instruments.csv'
    if not os.path.exists(instruments_file):
        logging.info("Fetching NFO instruments list from Zerodha...")
        nfo_instruments = kite.instruments('NFO')
        pd.DataFrame(nfo_instruments).to_csv(instruments_file, index=False)
    return pd.read_csv(instruments_file)

def get_atm_strike(ltp, strike_step):
    """Calculates the ATM strike price."""
    return round(ltp / strike_step) * strike_step

def get_strikes_to_monitor(atm_strike, strikes_config_str, strike_step):
    """Parses the strikes config and returns a list of strikes to monitor."""
    strikes = {}
    for s in strikes_config_str.split(','):
        s = s.strip().upper()
        if s == 'ATM':
            strikes['ATM'] = atm_strike
        elif 'ITM-' in s:
            level = int(s.split('-')[1])
            strikes[s] = atm_strike - (level * strike_step)
        elif 'OTM-' in s:
            level = int(s.split('-')[1])
            strikes[s] = atm_strike + (level * strike_step)
    return strikes

def find_option_instrument(nfo_df, underlying_name, strike_price, option_type):
    """Finds the nearest expiry option instrument."""
    options_df = nfo_df[(nfo_df['name'] == underlying_name) &
                          (nfo_df['instrument_type'] == option_type) &
                          (nfo_df['strike'] == strike_price)].copy()
    if options_df.empty:
        return None
    options_df['expiry'] = pd.to_datetime(options_df['expiry'])
    nearest_expiry = options_df[options_df['expiry'] >= datetime.datetime.now().date()]['expiry'].min()
    instrument = options_df[options_df['expiry'] == nearest_expiry].iloc[0]
    return instrument['tradingsymbol']

def check_oi_and_alert(kite, tradingsymbol, oi_change_percentage_threshold):
    """Checks OI for a given instrument and sends alert if change is significant."""
    global oi_data_cache
    try:
        quote = kite.quote(f"NFO:{tradingsymbol}")
        if not quote:
            logging.warning(f"Could not fetch quote for {tradingsymbol}")
            return

        current_oi = quote[f"NFO:{tradingsymbol}"]["oi"]
        if tradingsymbol not in oi_data_cache:
            oi_data_cache[tradingsymbol] = current_oi
            logging.info(f"Initial OI for {tradingsymbol}: {current_oi}")
        else:
            initial_oi = oi_data_cache[tradingsymbol]
            if initial_oi == 0: # Avoid division by zero
                return

            oi_change = current_oi - initial_oi
            oi_change_percentage = (oi_change / initial_oi) * 100

            if abs(oi_change_percentage) >= oi_change_percentage_threshold:
                alert_msg = (f"OI Alert for {tradingsymbol}!\n"
                             f"OI changed by {oi_change_percentage:.2f}%\n"
                             f"Initial OI: {initial_oi}, Current OI: {current_oi}")
                logging.warning(alert_msg)
                alerts.send_email(f"OI Alert: {tradingsymbol}", alert_msg)
                alerts.send_whatsapp(alert_msg)
                report_logger.log_alert("oi_screener", alert_msg)
                # Update cache to avoid repeated alerts for the same level
                oi_data_cache[tradingsymbol] = current_oi

    except Exception as e:
        logging.error(f"Error checking OI for {tradingsymbol}: {e}")

def run_strategy():
    """The main function to run the OI screener strategy."""
    global oi_data_cache, last_reset_date

    config = configparser.ConfigParser()
    config.read('config/config.ini')

    if not config.getboolean('oi_screener', 'enabled'):
        logging.info("OI Screener is disabled in the config.")
        return

    # Daily reset of cache, managed here to be self-contained.
    today = datetime.date.today()
    if last_reset_date != today:
        logging.info("New day detected for OI Screener. Resetting OI cache.")
        oi_data_cache = {}
        last_reset_date = today

    try:
        kite = get_kite_client()
        nfo_df = get_nfo_instruments(kite)

        symbols_to_monitor = config['oi_screener']['symbols'].split(',')
        strikes_config_str = config['oi_screener']['strikes_config']
        oi_change_percentage = int(config['oi_screener']['oi_change_percentage'])

        for symbol in symbols_to_monitor:
            symbol = symbol.strip().upper()
            logging.info(f"--- Processing {symbol} ---")

            # Determine strike step and underlying instrument name
            if symbol == 'NIFTY':
                strike_step = 50
                underlying_instrument = 'NIFTY 50'
                underlying_zerodha_name = f"NSE:{underlying_instrument}"
            elif symbol == 'BANKNIFTY':
                strike_step = 100
                underlying_instrument = 'NIFTY BANK'
                underlying_zerodha_name = f"NSE:{underlying_instrument}"
            else:
                logging.warning(f"Unsupported symbol: {symbol}")
                continue

            ltp_data = kite.ltp(underlying_zerodha_name)
            if not ltp_data:
                logging.error(f"Could not fetch LTP for {underlying_instrument}")
                continue
            ltp = ltp_data[underlying_zerodha_name]['last_price']
            atm_strike = get_atm_strike(ltp, strike_step)
            logging.info(f"LTP for {symbol} is {ltp}. ATM strike is {atm_strike}.")

            strikes_to_monitor = get_strikes_to_monitor(atm_strike, strikes_config_str, strike_step)

            for strike_label, strike_price in strikes_to_monitor.items():
                for option_type in ['CE', 'PE']:
                    instrument_symbol = find_option_instrument(nfo_df, symbol, strike_price, option_type)
                    if instrument_symbol:
                        logging.info(f"Monitoring {instrument_symbol} ({strike_label} {option_type})")
                        check_oi_and_alert(kite, instrument_symbol, oi_change_percentage)
                    else:
                        logging.warning(f"Could not find {option_type} instrument for {symbol} at strike {strike_price}")

    except Exception as e:
        logging.error(f"An error occurred in the OI screener strategy: {e}", exc_info=True)

if __name__ == '__main__':
    # This block is for testing the strategy standalone
    setup_logging()
    logging.info("--- Running OI Screener in Test Mode ---")

    # In a real scenario, this would be managed by the main loop in main.py
    # For testing, we run it once.
    if is_market_open():
        run_strategy()
    else:
        logging.info("Market is closed. Not running strategy.")
