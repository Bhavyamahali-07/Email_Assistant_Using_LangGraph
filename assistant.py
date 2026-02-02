# =====================================================
# AI EMAIL ASSISTANT – STREAMLIT CLOUD READY
# =====================================================

import os
import json
import base64
import re
import tempfile
from datetime import datetime, timedelta

import streamlit as st

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText

# ======================
# CONFIG
# ======================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar"
]

DEFAULT_DURATION_MINUTES = 60
MEMORY_FILE = "assistant_memory.json"


# ======================
# MEMORY
# ======================

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"booked_slots": []}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


def slot_key(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


# ======================
# GOOGLE LOGIN (🔥 FIXED)
# ======================

def google_login():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 🔑 READ GOOGLE CREDS FROM STREAMLIT SECRETS
            secrets_json = json.loads(st.secrets["GOOGLE_CREDENTIALS"])

            with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as tmp:
                json.dump(secrets_json, tmp)
                tmp_path = tmp.name

            flow = InstalledAppFlow.from_client_secrets_file(tmp_path, SCOPES)
            creds = flow.run_console()

            with open("token.json", "w") as token:
                token.write(creds.to_json())

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    return gmail, calendar


# ======================
# GMAIL HELPERS
# ======================

def get_unread_human_emails(service, max_results=5):
    results = service.users().messages().list(
        userId="me",
        labelIds=["UNREAD"],
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = msg_data["payload"]["headers"]
        subject = sender = ""

        for h in headers:
            if h["name"] == "Subject":
                subject = h["value"]
            if h["name"] == "From":
                sender = h["value"]

        parts = msg_data["payload"].get("parts", [])
        body = ""

        if parts:
            data = parts[0]["body"].get("data")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        emails.append({
            "id": msg["id"],
            "sender": sender,
            "subject": subject,
            "body": body
        })

    return emails


def create_gmail_draft(gmail, to_email, subject, body):
    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    gmail.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()


# ======================
# CALENDAR HELPERS
# ======================

def check_calendar_availability(calendar, start_dt):
    end_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)

    events = calendar.events().list(
        calendarId="primary",
        timeMin=start_dt.isoformat() + "Z",
        timeMax=end_dt.isoformat() + "Z",
        singleEvents=True
    ).execute()

    return len(events.get("items", [])) == 0


def create_calendar_event(calendar, event):
    calendar.events().insert(
        calendarId="primary",
        body={
            "summary": event["summary"],
            "start": {
                "dateTime": event["start"],
                "timeZone": "Asia/Kolkata"
            },
            "end": {
                "dateTime": event["end"],
                "timeZone": "Asia/Kolkata"
            }
        }
    ).execute()


def find_alternative_slots(calendar, start_dt, count=3):
    slots = []
    dt = start_dt + timedelta(hours=1)

    while len(slots) < count:
        if check_calendar_availability(calendar, dt):
            slots.append(dt.strftime("%B %d, %Y at %I:%M %p"))
        dt += timedelta(hours=1)

    return slots


# ======================
# DATE EXTRACTION
# ======================

def extract_datetime_from_email(text):
    pattern = r"(\d{1,2} \w+ \d{4}).*?(\d{1,2}:\d{2})"
    match = re.search(pattern, text)

    if not match:
        return None

    date_str, time_str = match.groups()
    return datetime.strptime(f"{date_str} {time_str}", "%d %B %Y %H:%M")


# ======================
# MAIN ASSISTANT
# ======================

def run_ai_email_assistant():
    gmail, calendar = google_login()
    memory = load_memory()

    emails = get_unread_human_emails(gmail)

    for email in emails:
        meeting_dt = extract_datetime_from_email(email["body"])
        reply = "Could you please confirm the meeting date and time?"

        if meeting_dt:
            key = slot_key(meeting_dt)

            if key in memory["booked_slots"]:
                free = False
            else:
                free = check_calendar_availability(calendar, meeting_dt)

            if free:
                event = {
                    "summary": email["subject"] or "Meeting",
                    "start": meeting_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "end": (meeting_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES))
                    .strftime("%Y-%m-%dT%H:%M:%S")
                }

                create_calendar_event(calendar, event)
                memory["booked_slots"].append(key)
                save_memory(memory)

                reply = (
                    f"Thank you. I have added the meeting to my calendar for "
                    f"{meeting_dt.strftime('%B %d, %Y at %I:%M %p')}."
                )
            else:
                alternatives = find_alternative_slots(calendar, meeting_dt)
                reply = (
                    "I have a scheduling conflict at the proposed time.\n\n"
                    "Would any of these alternatives work?\n"
                    + "\n".join(f"• {s}" for s in alternatives)
                )

        create_gmail_draft(
            gmail,
            email["sender"],
            "Re: " + email["subject"],
            reply
        )
