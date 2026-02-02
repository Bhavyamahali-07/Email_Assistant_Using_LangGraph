# =====================================================
# AI EMAIL ASSISTANT – STREAMLIT CLOUD SAFE VERSION
# =====================================================

import os
import json
import base64
import re
from datetime import datetime, timedelta

import streamlit as st

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText

# ======================
# CONFIG
# ======================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

MEMORY_FILE = "assistant_memory.json"
DEFAULT_DURATION_MINUTES = 30


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
# GOOGLE LOGIN (SECRETS)
# ======================

def google_login():
    token_data = st.secrets["google_token"]

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    return gmail, calendar


# ======================
# GMAIL HELPERS
# ======================

def create_gmail_draft(gmail, to, subject, body):
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    gmail.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()


# ======================
# CALENDAR HELPERS
# ======================

def check_calendar_availability(calendar, meeting_dt):
    start = meeting_dt.isoformat() + "Z"
    end = (meeting_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)).isoformat() + "Z"

    events = (
        calendar.events()
        .list(
            calendarId="primary",
            timeMin=start,
            timeMax=end,
            singleEvents=True,
        )
        .execute()
        .get("items", [])
    )

    return len(events) == 0


def create_calendar_event(calendar, meeting_dt, summary):
    event = {
        "summary": summary,
        "start": {
            "dateTime": meeting_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": (meeting_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)).isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }

    calendar.events().insert(
        calendarId="primary",
        body=event,
    ).execute()


def find_alternative_slots(calendar, meeting_dt, count=3):
    slots = []
    candidate = meeting_dt + timedelta(minutes=30)

    while len(slots) < count:
        if check_calendar_availability(calendar, candidate):
            slots.append(candidate.strftime("%B %d, %I:%M %p"))
        candidate += timedelta(minutes=30)

    return slots


# ======================
# DATE EXTRACTION
# ======================

def extract_datetime(text):
    match = re.search(r"(\d{1,2}:\d{2})", text)
    if not match:
        return None

    time_part = match.group(1)
    hour, minute = map(int, time_part.split(":"))

    dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    if dt < datetime.now():
        dt += timedelta(days=1)

    return dt


# ======================
# MAIN RUNNER
# ======================

def run_ai_email_assistant():
    st.info("🔐 Connecting to Gmail & Calendar...")
    gmail, calendar = google_login()

    memory = load_memory()

    # 🔹 SAMPLE EMAIL (Replace with real fetch logic later)
    email = {
        "sender": "someone@example.com",
        "subject": "Meeting Request",
        "body": "Can we meet today at 3:00?",
    }

    meeting_dt = extract_datetime(email["body"])

    if not meeting_dt:
        st.warning("No meeting time detected.")
        return

    slot_key = meeting_dt.strftime("%Y-%m-%d %H:%M")

    if slot_key in memory["booked_slots"]:
        free = False
    else:
        free = check_calendar_availability(calendar, meeting_dt)

    if free:
        create_calendar_event(calendar, meeting_dt, email["subject"])
        memory["booked_slots"].append(slot_key)
        save_memory(memory)

        reply = (
            f"Thanks for the message.\n\n"
            f"I have scheduled the meeting on "
            f"{meeting_dt.strftime('%B %d at %I:%M %p')}."
        )
    else:
        alternatives = find_alternative_slots(calendar, meeting_dt)
        reply = (
            "Thanks for reaching out.\n\n"
            "I have a conflict at the proposed time. "
            "Would any of the following work instead?\n\n"
            + "\n".join(f"- {slot}" for slot in alternatives)
        )

    create_gmail_draft(
        gmail,
        email["sender"],
        "Re: " + email["subject"],
        reply,
    )

    st.success("✅ Gmail draft created & calendar checked!")
