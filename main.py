import time
import configparser
import logging
from strategies.williams_r_alert import run_strategy
from utils import setup_logging, is_market_open

def main():
    """Main function to run the alert bot."""
    # Set up logging
    setup_logging()

    # Read configuration
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    poll_interval = int(config['strategy']['poll_interval'])

    logging.info("Starting Williams %R Alert Bot...")
    logging.info(f"Polling every {poll_interval} seconds.")

    while True:
        try:
            if is_market_open():
                logging.info("Market is open. Running strategy...")
                run_strategy()
            else:
                logging.info("Market is closed. Waiting for the next check.")

            logging.info(f"Cycle finished. Waiting for {poll_interval} seconds...")
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            logging.info("Bot stopped by user.")
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}")
            logging.info(f"Waiting for {poll_interval} seconds before retrying...")
            time.sleep(poll_interval)

if __name__ == "__main__":
    main()
