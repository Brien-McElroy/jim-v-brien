import os, smtplib, ssl, sys
from email.message import EmailMessage

body = open(sys.argv[1], encoding="utf-8").read()
msg = EmailMessage()
msg["Subject"] = sys.argv[2]
msg["From"] = os.environ["SMTP_USER"]
msg["To"] = os.environ["MAIL_TO"]
msg.set_content(body)
host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))
ctx = ssl.create_default_context()
if port == 465:
    s = smtplib.SMTP_SSL(host, port, context=ctx)
else:
    s = smtplib.SMTP(host, port)
    s.starttls(context=ctx)
s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
s.send_message(msg)
s.quit()
