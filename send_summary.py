"""Send a plain-text results note to everyone in MAIL_BOTH.

Used for the short summary that both players get. The existing send_email.py
still handles the paste-ready table that goes to Brien alone.

    python send_summary.py <file> "<subject>"

Environment: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_BOTH
MAIL_BOTH may hold several addresses separated by commas.

The From address is SMTP_USER - the Fastmail account doing the sending. That
matters: mail claiming to come from an address Fastmail cannot vouch for tends
to be binned by Yahoo and the like.
"""
import os, smtplib, ssl, sys
from email.message import EmailMessage


def main():
    if len(sys.argv) < 3:
        print("usage: send_summary.py <file> <subject>")
        return 2
    path, subject = sys.argv[1], sys.argv[2]
    if not os.path.exists(path):
        print("%s does not exist, so there is nothing to send." % path)
        return 0
    body = open(path, encoding="utf-8").read().strip()
    if not body:
        print("%s is empty, so there is nothing to send." % path)
        return 0

    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "465").strip() or 465)
    user = os.environ.get("SMTP_USER", "").strip()
    pw = os.environ.get("SMTP_PASS", "")
    raw = os.environ.get("MAIL_BOTH", "")
    to = [a.strip() for a in raw.replace(";", ",").split(",") if a.strip()]

    missing = [n for n, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                              ("SMTP_PASS", pw), ("MAIL_BOTH", raw)) if not v]
    if missing:
        print("FAILED: these secrets are not set: %s" % ", ".join(missing))
        return 1
    if not to:
        print("FAILED: MAIL_BOTH holds no usable address.")
        return 1

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(user, pw)
            s.send_message(msg)
    print("Sent %r to %s" % (subject, ", ".join(to)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("FAILED:", e)
        sys.exit(1)
