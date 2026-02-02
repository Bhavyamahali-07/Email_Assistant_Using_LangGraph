# =====================================================
# AI EMAIL ASSISTANT – STREAMLIT + TOKEN.JSON VERSION
# =====================================================

import os
import json
import base64
import re
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText

# ======================
# CONFIG
# ======================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar"
]

MEMORY_FILE = "assistant_memory.json"
DEFAULT_DURATION_MINUTES = 30


# ======================
# GOOGLE LOGIN (TOKEN ONLY)
# ======================

def google_login():
    if not os.path.exists("token.json"):
        raise RuntimeError(
            "❌ token.json not found. "
            "Run Google OAuth locally once to generate it."
        )

    creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open("token.json", "w") as f:
            f.write(creds.to_json())

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    return gmail, calendar


# ======================
# MEMORY HELPERS
# ======================

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"booked_slots": []}


def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


# ======================
# EMAIL HELPERS
# ======================

def get_unread_emails(gmail, max_results=5):
    results = gmail.users().messages().list(
        userId="me",
        labelIds=["UNREAD"],
        maxResults=max_results
    ).execute()

    return results.get("messages", [])


def get_email_content(gmail, msg_id):
    msg = gmail.users().messages().get(
        userId="me",
        id=msg_id,
        format="full"
    ).execute()

    headers = msg["payload"].get("headers", [])
    subject = sender = ""

    for h in headers:
        if h["name"] == "Subject":
            subject = h["value"]
        if h["name"] == "From":
            sender = h["value"]

    body = ""
    parts = msg["payload"].get("parts", [])
    for p in parts:
        if p.get("mimeType") == "text/plain":
            body = base64.urlsafe_b64decode(
                p["body"]["data"]
            ).decode("utf-8")

    return {
        "id": msg_id,
        "subject": subject,
        "sender": sender,
        "body": body
    }


def create_draft(gmail, to, subject, body):
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    gmail.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()


# ======================
# CALENDAR HELPERS
# ======================

def create_calendar_event(calendar, summary, start_dt, duration_minutes=30):
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event = {
        "summary": summary,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }

    calendar.events().insert(
        calendarId="primary",
        body=event
    ).execute()


# ======================
# DATE PARSER (SIMPLE)
# ======================

def extract_meeting_datetime(text):
    match = re.search(
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4}).*?(\d{1,2}):(\d{2})",
        text
    )
    if not match:
        return None

    day, month, year, hour, minute = map(int, match.groups())
    return datetime(year, month, day, hour, minute)


# ======================
# MAIN ASSISTANT
# ======================

def run_ai_email_assistant():
    gmail, calendar = google_login()
    memory = load_memory()

    messages = get_unread_emails(gmail)

    for m in messages:
        email = get_email_content(gmail, m["id"])
        meeting_dt = extract_meeting_datetime(email["body"])

        if meeting_dt:
            create_calendar_event(
                calendar,
                email["subject"] or "Meeting",
                meeting_dt,
                DEFAULT_DURATION_MINUTES
            )

            reply = (
                f"Hi,\n\n"
                f"I've scheduled the meeting on "
                f"{meeting_dt.strftime('%d %b %Y at %I:%M %p')}.\n\n"
                f"Thanks!"
            )
        else:
            reply = (
                "Hi,\n\n"
                "Thanks for your email. "
                "I will get back to you shortly.\n\n"
                "Regards"
            )

        create_draft(
            gmail,
            email["sender"],
            "Re: " + email["subject"],
            reply
        )

    save_memory(memory)
