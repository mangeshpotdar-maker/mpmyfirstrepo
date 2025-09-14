import pandas as pd
import datetime
import os
import logging

# A list to hold dictionaries of alert data
daily_alerts_data = []

def log_alert(strategy_name, alert_details):
    """
    Logs a structured alert from any strategy.

    Args:
        strategy_name (str): The name of the strategy that triggered the alert.
        alert_details (str): The full text of the alert message.
    """
    try:
        daily_alerts_data.append({
            "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "strategy": strategy_name,
            "details": alert_details
        })
        logging.info(f"Alert logged for strategy: {strategy_name}")
    except Exception as e:
        logging.error(f"Failed to log alert: {e}", exc_info=True)

def generate_daily_csv_report():
    """
    Generates a CSV report of all alerts logged during the day.
    """
    if not daily_alerts_data:
        logging.info("No alerts were logged today. CSV report will not be generated.")
        return

    try:
        df = pd.DataFrame(daily_alerts_data)

        # Ensure logs directory exists
        if not os.path.exists('logs'):
            os.makedirs('logs')

        date_str = datetime.date.today().strftime('%Y-%m-%d')
        filepath = f"logs/EOD_Report_{date_str}.csv"

        df.to_csv(filepath, index=False)
        logging.info(f"Successfully generated end-of-day CSV report at: {filepath}")

    except Exception as e:
        logging.error(f"Failed to generate daily CSV report: {e}", exc_info=True)

def reset_daily_alerts():
    """
    Resets the in-memory list of alerts. Should be called at the start of each day.
    """
    global daily_alerts_data
    logging.info("Resetting daily alert logger for the new day.")
    daily_alerts_data = []

if __name__ == '__main__':
    # For testing purposes
    logging.basicConfig(level=logging.INFO)

    print("--- Testing Report Logger ---")
    reset_daily_alerts()

    log_alert("test_strategy_1", "This is the first test alert.")
    log_alert("test_strategy_2", "This is the second test alert with more details.")

    print(f"Current alerts in memory: {daily_alerts_data}")

    generate_daily_csv_report()

    # Check if the file was created
    date_str = datetime.date.today().strftime('%Y-%m-%d')
    filepath = f"logs/EOD_Report_{date_str}.csv"
    if os.path.exists(filepath):
        print(f"Successfully created test report: {filepath}")
        # Clean up the test file
        os.remove(filepath)
    else:
        print("Failed to create test report.")
