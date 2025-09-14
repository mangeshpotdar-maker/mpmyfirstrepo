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
from utils import setup_logging
import alerts
import report_logger

# In-memory cache for the previous poll's OI data.
# This dictionary will hold {tradingsymbol: oi}
previous_oi_data = {}
# Cache for instrument data to avoid fetching repeatedly
instrument_data_cache = {
    "nfo_df": None,
    "fno_stocks": None,
    "stock_to_instrument": None
}

def get_kite_client():
    """Initializes and returns a KiteConnect client instance."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    api_key = config['zerodha']['api_key']
    access_token = config['zerodha']['access_token']
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def initialize_instrument_data(kite):
    """Fetches and caches the required instrument data for the session."""
    if instrument_data_cache["nfo_df"] is None:
        logging.info("Initializing instrument data for OI Spurt Screener...")
        nfo_df = pd.DataFrame(kite.instruments('NFO'))
        nse_df = pd.DataFrame(kite.instruments('NSE'))

        # Get F&O stock symbols (excluding indices)
        all_underlyings = nfo_df['name'].unique()
        indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'NIFTYMID50']
        fno_stocks = [s for s in all_underlyings if s not in indices]

        # Create a map of stock symbol to its NSE instrument token
        fno_stocks_df = nse_df[nse_df['tradingsymbol'].isin(fno_stocks) & (nse_df['exchange'] == 'NSE')]
        stock_to_instrument = pd.Series(fno_stocks_df.instrument_token.values, index=fno_stocks_df.tradingsymbol).to_dict()

        # Cache the data
        instrument_data_cache["nfo_df"] = nfo_df
        instrument_data_cache["fno_stocks"] = fno_stocks
        instrument_data_cache["stock_to_instrument"] = stock_to_instrument
        logging.info(f"Found {len(fno_stocks)} F&O stocks to monitor.")

def get_atm_options_for_all_stocks(kite):
    """Finds ATM call and put options for all F&O stocks."""
    if instrument_data_cache["fno_stocks"] is None:
        initialize_instrument_data(kite)

    nfo_df = instrument_data_cache["nfo_df"]
    fno_stocks = instrument_data_cache["fno_stocks"]
    stock_to_instrument = instrument_data_cache["stock_to_instrument"]

    # Get LTP for all stocks in one call
    instrument_tokens = list(stock_to_instrument.values())
    ltp_data = kite.ltp(instrument_tokens)
    if not ltp_data:
        logging.error("Could not fetch LTP for F&O stocks.")
        return []

    atm_options = []
    for stock_symbol, instrument in stock_to_instrument.items():
        if instrument not in ltp_data:
            continue

        ltp = ltp_data[instrument]['last_price']

        # Find ATM strike
        stock_options = nfo_df[nfo_df['name'] == stock_symbol].copy()
        if stock_options.empty:
            continue

        stock_options['expiry'] = pd.to_datetime(stock_options['expiry'])
        nearest_expiry = stock_options[stock_options['expiry'] >= datetime.datetime.now().date()]['expiry'].min()
        nearest_options = stock_options[stock_options['expiry'] == nearest_expiry]

        atm_strike = nearest_options.iloc[(nearest_options['strike'] - ltp).abs().argsort()[:1]]['strike'].iloc[0]

        # Get ATM call and put tradingsymbols
        atm_call = nearest_options[(nearest_options['strike'] == atm_strike) & (nearest_options['instrument_type'] == 'CE')]
        atm_put = nearest_options[(nearest_options['strike'] == atm_strike) & (nearest_options['instrument_type'] == 'PE')]

        if not atm_call.empty:
            atm_options.append(f"NFO:{atm_call.iloc[0]['tradingsymbol']}")
        if not atm_put.empty:
            atm_options.append(f"NFO:{atm_put.iloc[0]['tradingsymbol']}")

    return atm_options

def run_strategy():
    """The main function to run the OI spurt screener strategy."""
    global previous_oi_data

    config = configparser.ConfigParser()
    config.read('config/config.ini')

    if not config.getboolean('oi_spurt_screener', 'enabled', fallback=False):
        logging.info("OI Spurt Screener is disabled in the config.")
        time.sleep(300) # Sleep longer if disabled
        return

    oi_change_threshold = config.getfloat('oi_spurt_screener', 'oi_change_percentage')

    try:
        kite = get_kite_client()

        # This will run once per session
        if instrument_data_cache["fno_stocks"] is None:
            initialize_instrument_data(kite)

        # Get the list of ATM options to monitor for this cycle
        instruments_to_monitor = get_atm_options_for_all_stocks(kite)
        if not instruments_to_monitor:
            logging.warning("Could not determine any ATM options to monitor in this cycle.")
            return

        logging.info(f"Monitoring OI for {len(instruments_to_monitor)} ATM options.")

        # Get quotes for all instruments in a single call
        quote_data = kite.quote(instruments_to_monitor)

        current_oi_data = {}
        for instrument, data in quote_data.items():
            tradingsymbol = instrument.split(':')[1]
            current_oi = data['oi']
            current_oi_data[tradingsymbol] = current_oi

            if tradingsymbol in previous_oi_data and previous_oi_data[tradingsymbol] > 0:
                prev_oi = previous_oi_data[tradingsymbol]
                oi_change_percent = ((current_oi - prev_oi) / prev_oi) * 100

                if abs(oi_change_percent) >= oi_change_threshold:
                    alert_msg = (f"OI Spurt Alert: {tradingsymbol}\n"
                                 f"OI changed by {oi_change_percent:.2f}% in the last minute.\n"
                                 f"Previous OI: {prev_oi}, Current OI: {current_oi}")
                    logging.warning(alert_msg)
                    alerts.send_email(f"OI Spurt Alert: {tradingsymbol}", alert_msg)
                    alerts.send_whatsapp(alert_msg)
                    report_logger.log_alert("oi_spurt_screener", alert_msg)

        # Update the cache for the next run
        previous_oi_data = current_oi_data
        logging.info("OI Spurt Screener cycle finished.")

    except Exception as e:
        logging.error(f"An error occurred in the OI Spurt Screener strategy: {e}", exc_info=True)
        # If there's an error (e.g., API), reset instrument cache to force re-initialization
        instrument_data_cache["nfo_df"] = None


if __name__ == '__main__':
    setup_logging()
    logging.info("--- Running OI Spurt Screener in Test Mode ---")
    run_strategy()
