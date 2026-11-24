
import os
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv(".env")

sender = os.getenv("SMTP_USER")
password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
receiver = os.getenv("EMAIL_TO", sender)

try:
    print("Dang ket noi Gmail SMTP...")

    msg = EmailMessage()
    msg["Subject"] = "FireWatch - Kiem tra gui email"
    msg["From"] = sender
    msg["To"] = receiver
    msg.set_content(
        "FireWatch da ket noi Gmail SMTP thanh cong. "
        "Day la email kiem tra he thong."
    )

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(sender, password)

        print("SMTP LOGIN SUCCESS")

        smtp.send_message(msg)
        print("EMAIL SENT - SMTP da chap nhan thu")

except Exception as e:
    print("EMAIL ERROR:", type(e).__name__, str(e))
