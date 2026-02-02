# =====================================================
# AI EMAIL ASSISTANT – FINAL STREAMLIT + GITHUB SAFE
# =====================================================

import os
import json
import base64
import re
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import streamlit as st

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ======================
# CONFIG
# ======================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar"
]

DEFAULT_DURATION_MINUTES = 30
TIMEZONE = "Asia/Kolkata"
MEMORY_FILE = "assistant_memory.json"

# ======================
# PATHS
# ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

# ======================
# MEMORY
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
# GOOGLE LOGIN (CLOUD SAFE)
# ======================
def google_login():
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = json.loads(
                st.secrets["google"]["credentials"]
            )

            flow = InstalledAppFlow.from_client_config(
                client_config, SCOPES
            )

            auth_url, _ = flow.authorization_url(prompt="consent")

            st.warning("🔐 Google Authorization Required")
            st.code(auth_url)

            auth_code = st.text_input(
                "📋 Paste authorization code:",
                type="password"
            )

            if not auth_code:
                st.stop()

            flow.fetch_token(code=auth_code)
            creds = flow.credentials

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    return gmail, calendar


# ======================
# EMAIL HELPERS (🔥 FIXED)
# ======================
def extract_email_address(sender):
    match = re.search(r"<(.+?)>", sender)
    return match.group(1) if match else sender


def get_unread_emails(service, max_results=5):
    results = service.users().messages().list(
        userId="me", labelIds=["UNREAD"], maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        data = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = {
            h["name"].lower(): h["value"]
            for h in data["payload"]["headers"]
        }

        payload = data["payload"]
        body = ""

        # ✅ Single-part email
        if "data" in payload.get("body", {}):
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode("utf-8", errors="ignore")

        # ✅ Multi-part email
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and "data" in part["body"]:
                body = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="ignore")
                break

        emails.append({
            "id": msg["id"],
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", "(No Subject)"),
            "body": body.strip()
        })

    return emails


def create_gmail_draft(service, to_email, subject, body):
    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()


# ======================
# DATE & TIME
# ======================
def extract_datetime_from_email(text):
    match = re.search(
        r"(\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}).*?(\d{1,2}:\d{2})",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    date_str = f"{match.group(1)} {match.group(3)}"
    dt = datetime.strptime(date_str, "%d %b %Y %H:%M")
    return dt.replace(tzinfo=timezone.utc).astimezone()


def slot_key(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


# ======================
# CALENDAR
# ======================
def check_calendar_availability(calendar, meeting_dt):
    end = meeting_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)

    events = calendar.events().list(
        calendarId="primary",
        timeMin=meeting_dt.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True
    ).execute()

    return len(events.get("items", [])) == 0


def create_calendar_event(calendar, meeting_dt, summary):
    event = {
        "summary": summary,
        "start": {
            "dateTime": meeting_dt.isoformat(),
            "timeZone": TIMEZONE
        },
        "end": {
            "dateTime": (meeting_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)).isoformat(),
            "timeZone": TIMEZONE
        }
    }

    calendar.events().insert(
        calendarId="primary",
        body=event
    ).execute()


# ======================
# MAIN ASSISTANT
# ======================
def run_ai_email_assistant():
    memory = load_memory()
    gmail, calendar = google_login()

    emails = get_unread_emails(gmail)
    results = []

    for email in emails:
        meeting_dt = extract_datetime_from_email(email["body"])
        reply = "Could you please confirm the meeting date and time?"

        if meeting_dt:
            key = slot_key(meeting_dt)
            free = key not in memory["booked_slots"] and \
                   check_calendar_availability(calendar, meeting_dt)

            if free:
                create_calendar_event(
                    calendar,
                    meeting_dt,
                    email["subject"]
                )

                memory["booked_slots"].append(key)

                reply = f"""
Hi,

Thank you for reaching out.

I’ve scheduled the meeting on:
📅 {meeting_dt.strftime('%B %d, %Y')}
⏰ {meeting_dt.strftime('%I:%M %p')} (IST)

Looking forward to our discussion.

Best regards,
Bhavya
"""
            else:
                reply = (
                    "I currently have a scheduling conflict. "
                    "Please suggest another time."
                )

        to_email = extract_email_address(email["sender"])

        create_gmail_draft(
            gmail,
            to_email,
            "Re: " + email["subject"],
            reply.strip()
        )

        results.append({
            "from": email["sender"],
            "subject": email["subject"],
            "draft": True
        })

    save_memory(memory)
    return results
