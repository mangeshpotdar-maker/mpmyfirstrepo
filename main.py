import time
import configparser
import logging
import importlib
import threading
from utils import setup_logging, is_market_open
import report_logger
import sys

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
    while is_market_open():
        try:
            strategy_module.run_strategy()
            # The sleep is inside the loop of the thread
            time.sleep(poll_interval)
        except Exception as e:
            logging.error(f"An error occurred in strategy {strategy_module.__name__}: {e}", exc_info=True)
            # Wait before retrying in case of an error
            time.sleep(poll_interval)
    logging.info(f"Market closed. Stopping thread for strategy '{strategy_module.__name__}'.")


def main():
    """Main function to run the alert bot."""
    setup_logging()

    # Check market status at startup
    if not is_market_open():
        logging.info("Market is currently closed. The bot will not start. Exiting.")
        sys.exit()

    config = configparser.ConfigParser()
    config.read('config/config.ini')
    poll_interval = int(config['strategy']['poll_interval'])

    strategy_modules = get_active_strategy_modules()
    if not strategy_modules:
        logging.error("No valid strategies found. Exiting.")
        return

    logging.info(f"Market is open. Starting Trading Alert Bot with {len(strategy_modules)} strategies.")
    logging.info(f"Polling interval for all strategies: {poll_interval} seconds.")

    # Reset daily reporters at the start of the day
    report_logger.reset_daily_alerts()

    # Create and start a thread for each strategy
    threads = []
    for module in strategy_modules:
        thread = threading.Thread(target=strategy_runner, args=(module, poll_interval))
        # No longer daemon threads, we will wait for them to finish
        thread.start()
        threads.append(thread)

    # Wait for all strategy threads to complete. They will exit when the market closes.
    for thread in threads:
        thread.join()

    # Perform end-of-day tasks after all threads have completed
    logging.info("All strategy threads have completed. Generating end-of-day CSV report.")
    report_logger.generate_daily_csv_report()

    logging.info("EOD tasks complete. Exiting application.")


if __name__ == "__main__":
    main()
