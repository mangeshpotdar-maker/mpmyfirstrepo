import time
import configparser
import logging
import importlib
import threading
from utils import setup_logging, is_market_open
import report_logger

def get_active_strategy_modules():
    """Reads the config and dynamically imports all active strategy modules."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    modules = []
    try:
        strategy_names = config['general']['active_strategies'].split(',')
        for name in strategy_names:
            name = name.strip()
            if not name:
                continue
            try:
                module = importlib.import_module(f"strategies.{name}")
                modules.append(module)
                logging.info(f"Successfully loaded strategy module: {name}")
            except ImportError:
                logging.error(f"Failed to import strategy: {name}. Make sure the file strategies/{name}.py exists.")
    except KeyError:
        logging.error("Active strategies not defined in config. Please add 'active_strategies' to the [general] section.")
    return modules

def strategy_runner(strategy_module, poll_interval):
    """The function that will be executed by each strategy thread."""
    logging.info(f"Thread for strategy '{strategy_module.__name__}' started.")
    while True:
        try:
            if is_market_open():
                strategy_module.run_strategy()
            # The sleep is inside the loop of the thread
            time.sleep(poll_interval)
        except Exception as e:
            logging.error(f"An error occurred in strategy {strategy_module.__name__}: {e}", exc_info=True)
            # Wait before retrying in case of an error
            time.sleep(poll_interval)


def main():
    """Main function to run the alert bot."""
    setup_logging()

    config = configparser.ConfigParser()
    config.read('config/config.ini')
    poll_interval = int(config['strategy']['poll_interval'])

    strategy_modules = get_active_strategy_modules()
    if not strategy_modules:
        logging.error("No valid strategies found. Exiting.")
        return

    logging.info(f"Starting Trading Alert Bot with {len(strategy_modules)} strategies.")
    logging.info(f"Polling interval for all strategies: {poll_interval} seconds.")

    # Create and start a thread for each strategy
    threads = []
    for module in strategy_modules:
        thread = threading.Thread(target=strategy_runner, args=(module, poll_interval))
        thread.daemon = True  # Threads will exit when the main program exits
        thread.start()
        threads.append(thread)

    # The main loop now handles EOD reporting and daily resets
    market_was_open = False
    while True:
        try:
            market_is_currently_open = is_market_open()

            if market_is_currently_open and not market_was_open:
                logging.info("Market has just opened. Resetting daily reporters.")
                report_logger.reset_daily_alerts()

            elif not market_is_currently_open and market_was_open:
                logging.info("Market has just closed. Generating end-of-day CSV report.")
                report_logger.generate_daily_csv_report()

            market_was_open = market_is_currently_open

            # The main thread can sleep for a longer interval, as it only checks for market close
            time.sleep(60)

        except KeyboardInterrupt:
            logging.info("Bot stopped by user. Exiting.")
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
