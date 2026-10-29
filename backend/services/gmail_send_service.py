"""Send outreach email from Ryan's Gmail in the background.

Same account, credential, and message shape as the draft service
(GMAIL_APP_PASSWORD env var; plain-text + HTML with the bathroom photo
CID-embedded) — but sent via SMTP instead of appended to Drafts. One
press in the app sends it; nothing opens on Ryan's phone and there is no
separate "Logged as sent" tap, because the send endpoint logs the touch
only after SMTP accepts the message.

SMTP failure raises before anything is logged — a failed send must never
look like a sent touch.
"""

import logging
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from services.gmail_draft_service import (
    GMAIL_USER,
    PHOTO_CID,
    _photo_path,
    build_html_body,
)

log = logging.getLogger(__name__)

GMAIL_SMTP = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


def send_email(
    to_email: str,
    subject: str,
    text_body: str,
    include_photo: bool = True,
) -> dict:
    """Send one outreach email from Ryan's Gmail. Returns send info."""
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not password:
        raise RuntimeError("GMAIL_APP_PASSWORD is not set")

    msg = MIMEMultipart("related")
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(build_html_body(text_body, include_photo), "html", "utf-8"))

    if include_photo:
        photo_path = _photo_path()
        if photo_path:
            with open(photo_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype="jpeg")
            img.add_header("Content-ID", f"<{PHOTO_CID}>")
            img.add_header("Content-Disposition", "inline", filename="microcement-bathroom.jpg")
            msg.attach(img)
        else:
            log.warning("gmail send: photo not found, sending without inline image")

    smtp = smtplib.SMTP(GMAIL_SMTP, GMAIL_SMTP_PORT, timeout=60)
    try:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(GMAIL_USER, password)
        smtp.send_message(msg)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass

    return {"ok": True, "to": to_email, "subject": subject, "photo_included": include_photo}
