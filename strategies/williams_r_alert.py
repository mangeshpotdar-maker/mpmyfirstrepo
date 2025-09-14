import configparser
import pandas as pd
from kiteconnect import KiteConnect
import datetime
import os
import sys
import logging

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import is_market_open
import alerts

def get_kite_client():
    """Initializes and returns a KiteConnect client instance."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    api_key = config['zerodha']['api_key']
    access_token = config['zerodha']['access_token']

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_historical_data(kite, instrument_token, interval='15minute', period=30):
    """Fetches historical data for a given instrument."""
    to_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    from_date = (datetime.datetime.now() - datetime.timedelta(days=period)).strftime('%Y-%m-%d %H:%M:%S')
    try:
        data = kite.historical_data(instrument_token, from_date, to_date, interval)
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        logging.error(f"Error fetching historical data for {instrument_token}: {e}")
        return None

def calculate_willr(df, period=14):
    """
    Calculates Williams %R for a given DataFrame manually using pandas.
    Formula: %R = (Highest High - Close) / (Highest High - Lowest Low) * -100
    """
    if df is not None and not df.empty and len(df) >= period:
        high = df['high'].rolling(period).max()
        low = df['low'].rolling(period).min()
        close = df['close']

        df['willr'] = (high - close) / (high - low) * -100
        return df
    return None

def check_alert_condition(df, threshold=-20):
    """Checks if the Williams %R has crossed below the threshold."""
    if df is not None and not df.empty and len(df) > 1: # Need at least 2 points to check for a cross
        latest_willr = df['willr'].iloc[-1]
        previous_willr = df['willr'].iloc[-2]
        if latest_willr < threshold and previous_willr >= threshold:
            return True
    return False

def run_strategy():
    """The main function to run the Williams %R alert strategy."""
    if not is_market_open():
        return

    config = configparser.ConfigParser()
    config.read('config/config.ini')

    try:
        kite = get_kite_client()
        instruments = {
            'NIFTY': config['instruments']['nifty'],
            'BANKNIFTY': config['instruments']['banknifty']
        }
        willr_period = int(config['strategy']['willr_period'])
        willr_threshold = int(config['strategy']['willr_threshold'])

        for name, token in instruments.items():
            logging.info(f"Fetching data for {name}...")
            df = get_historical_data(kite, token)
            if df is not None:
                df = calculate_willr(df, period=willr_period)
                if check_alert_condition(df, threshold=willr_threshold):
                    latest_willr = df['willr'].iloc[-1]
                    logging.warning(f"ALERT: Williams %R for {name} crossed below {willr_threshold}! Current value: {latest_willr:.2f}")
                    find_otm_put_and_alert(kite, name)
    except Exception as e:
        logging.error(f"An error occurred in the strategy: {e}")

def find_otm_put_and_alert(kite, underlying_name):
    """Finds the nearest OTM put option and triggers alerts."""
    try:
        # Step 1: Get LTP of the underlying index
        instrument_map = {
            'NIFTY': 'NIFTY 50',
            'BANKNIFTY': 'NIFTY BANK'
        }
        instrument_name = f"NSE:{instrument_map.get(underlying_name, underlying_name)}"

        underlying_ltp_data = kite.ltp(instrument_name)
        if not underlying_ltp_data:
            logging.error(f"Could not fetch LTP for {instrument_name}")
            return

        underlying_ltp = underlying_ltp_data[instrument_name]["last_price"]
        logging.info(f"Current LTP of {underlying_name} is {underlying_ltp}")

        # Step 2: Get all NFO instruments (with caching)
        instruments_file = 'nfo_instruments.csv'
        if not os.path.exists(instruments_file):
            logging.info("Fetching NFO instruments list from Zerodha...")
            nfo_instruments = kite.instruments('NFO')
            pd.DataFrame(nfo_instruments).to_csv(instruments_file, index=False)

        nfo_df = pd.read_csv(instruments_file)

        # Step 3: Filter for relevant put options
        options_df = nfo_df[nfo_df['name'] == underlying_name]
        puts_df = options_df[options_df['instrument_type'] == 'PE'].copy()
        puts_df['expiry'] = pd.to_datetime(puts_df['expiry'])
        nearest_expiry = puts_df[puts_df['expiry'] >= datetime.datetime.now().date()]['expiry'].min()
        nearest_expiry_puts = puts_df[puts_df['expiry'] == nearest_expiry]

        # Step 4: Find the nearest OTM strike
        otm_puts = nearest_expiry_puts[nearest_expiry_puts['strike'] < underlying_ltp]
        if otm_puts.empty:
            logging.warning(f"No OTM puts found for {underlying_name} with LTP {underlying_ltp}")
            return

        nearest_otm_put = otm_puts.loc[otm_puts['strike'].idxmax()]
        otm_tradingsymbol = nearest_otm_put['tradingsymbol']

        # Step 5: Get the price of the OTM put
        otm_ltp_data = kite.ltp(f"NFO:{otm_tradingsymbol}")
        if not otm_ltp_data:
            logging.error(f"Could not fetch LTP for OTM put {otm_tradingsymbol}")
            return

        otm_ltp = otm_ltp_data[f"NFO:{otm_tradingsymbol}"]["last_price"]

        logging.info(f"Nearest OTM Put: {otm_tradingsymbol}, Strike: {nearest_otm_put['strike']}, Price: {otm_ltp}")

        # Step 6: Trigger alerts
        alert_message = (f"Williams %R Alert for {underlying_name}!\n"
                         f"Nearest OTM Put: {otm_tradingsymbol}\n"
                         f"Strike Price: {nearest_otm_put['strike']}\n"
                         f"Current Price: {otm_ltp}")

        logging.info("--- Sending Alert ---")
        logging.info(alert_message)
        alerts.send_email(f"Williams %R Alert for {underlying_name}", alert_message)
        alerts.send_whatsapp(alert_message)

    except Exception as e:
        logging.error(f"Error in find_otm_put_and_alert: {e}")

import logging

if __name__ == '__main__':
    from utils import setup_logging
    setup_logging()
    run_strategy()
