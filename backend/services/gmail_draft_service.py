"""Create Gmail drafts with the outreach photo inline in the HTML body.

Uses IMAP with a Gmail App Password (GMAIL_APP_PASSWORD env var) to append
an HTML draft to the Gmail Drafts folder. The photo is CID-embedded so it
shows inline without remote-image loading prompts.

Ryan opens his normal mail app, sees the draft, taps Send. Nothing sends
without his tap.
"""

import imaplib
import logging
import os
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

GMAIL_IMAP = "imap.gmail.com"
GMAIL_USER = "ryanmena504@gmail.com"
PHOTO_CID = "bathroom-photo"

# Photo lives in the frontend public folder; backend resolves it relative to repo root.
def _photo_path() -> Optional[Path]:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "outreach-bathroom.jpg",
        Path(__file__).resolve().parent / "assets" / "outreach-bathroom.jpg",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def build_html_body(text_body: str, include_photo: bool = True) -> str:
    """Wrap the plain-text outreach in HTML with the photo inline."""
    # Escape the text and convert line breaks.
    escaped = (
        text_body.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    photo_html = (
        f'<p><img src="cid:{PHOTO_CID}" alt="Finished microcement shower" '
        f'style="max-width: 100%; border-radius: 8px;" /></p>'
        if include_photo
        else ""
    )
    return f"""<html><body style="font-family: sans-serif; font-size: 14px; color: #222;">
<p>{escaped}</p>
{photo_html}
</body></html>"""


def create_draft(
    to_email: str,
    subject: str,
    text_body: str,
    include_photo: bool = True,
) -> dict:
    """Create a Gmail draft with the photo inline. Returns draft info."""
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
            log.warning("gmail draft: photo not found, sending without inline image")

    # Append to Gmail Drafts via IMAP.
    imap = imaplib.IMAP4_SSL(GMAIL_IMAP)
    try:
        imap.login(GMAIL_USER, password)
        # Gmail's drafts folder; try the standard names.
        draft_folder = None
        for candidate in ('[Gmail]/Drafts', '[Google Mail]/Drafts'):
            status, _ = imap.select(candidate, readonly=False)
            if status == "OK":
                draft_folder = candidate
                break
        if not draft_folder:
            raise RuntimeError("Could not find Gmail Drafts folder")
        imap.append(
            draft_folder,
            "\\Draft",
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(),
        )
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return {"ok": True, "to": to_email, "subject": subject, "photo_included": include_photo}
