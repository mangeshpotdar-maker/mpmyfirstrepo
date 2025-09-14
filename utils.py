import configparser
import datetime
import pytz
import os

def is_market_open():
    """Checks if the Indian stock market is open."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')

    market_open_hour = int(config['market']['market_open_hour'])
    market_open_minute = int(config['market']['market_open_minute'])
    market_close_hour = int(config['market']['market_close_hour'])
    market_close_minute = int(config['market']['market_close_minute'])

    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(tz)

    market_open = now.replace(hour=market_open_hour, minute=market_open_minute, second=0, microsecond=0)
    market_close = now.replace(hour=market_close_hour, minute=market_close_minute, second=0, microsecond=0)

    # Check if it's a weekday (0=Monday, 6=Sunday)
    if now.weekday() >= 5:
        return False

    return market_open <= now <= market_close

import logging
from logging.handlers import TimedRotatingFileHandler

def setup_logging():
    """Configures logging to file and console."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Ensure logs directory exists
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # File handler for daily logs
    log_file = f"logs/alerts_{datetime.datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=30)
    file_handler.setFormatter(log_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Add handlers if they don't exist
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

if __name__ == '__main__':
    # For testing purposes
    setup_logging()
    logging.info("Testing logger setup.")
    if is_market_open():
        logging.info("Market is open.")
    else:
        logging.info("Market is closed.")
