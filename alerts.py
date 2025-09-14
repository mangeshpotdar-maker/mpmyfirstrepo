import smtplib
import configparser
from twilio.rest import Client

def send_email(subject, body):
    """Sends an email alert."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')

    if not config.getboolean('email', 'enabled'):
        return

    smtp_server = config['email']['smtp_server']
    smtp_port = int(config['email']['smtp_port'])
    smtp_user = config['email']['smtp_user']
    smtp_password = config['email']['smtp_password']
    recipient_email = config['email']['recipient_email']

    message = f"Subject: {subject}\n\n{body}"

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient_email, message)
        server.quit()
        print("Email alert sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_whatsapp(body):
    """Sends a WhatsApp alert using Twilio."""
    config = configparser.ConfigParser()
    config.read('config/config.ini')

    if not config.getboolean('whatsapp', 'enabled'):
        return

    twilio_sid = config['whatsapp']['twilio_sid']
    twilio_token = config['whatsapp']['twilio_token']
    whatsapp_from = config['whatsapp']['whatsapp_from']
    whatsapp_to = config['whatsapp']['whatsapp_to']

    try:
        client = Client(twilio_sid, twilio_token)
        message = client.messages.create(
            body=body,
            from_=whatsapp_from,
            to=whatsapp_to
        )
        print(f"WhatsApp alert sent successfully. SID: {message.sid}")
    except Exception as e:
        print(f"Failed to send WhatsApp message: {e}")

if __name__ == '__main__':
    # For testing purposes
    test_subject = "Test Alert"
    test_body = "This is a test alert from the trading bot."

    print("Testing email alert...")
    send_email(test_subject, test_body)

    print("\nTesting WhatsApp alert...")
    send_whatsapp(test_body)
