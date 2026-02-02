# =====================================================
# AI EMAIL ASSISTANT (COLAB VERSION + STREAMLIT READY)
# =====================================================

import os
import json
import base64
import re
from datetime import datetime, timedelta

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

MEMORY_FILE = "assistant_memory.json"
DEFAULT_DURATION_MINUTES = 60
TIMEZONE = "Asia/Kolkata"

# ======================
# MEMORY
# ======================

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {
        "processed_emails": [],
        "booked_slots": []
    }

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

memory = load_memory()

def slot_key(start_dt):
    end_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)
    return f"{start_dt.isoformat()}::{end_dt.isoformat()}"

# ======================
# GOOGLE AUTH
# ======================

def google_login():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    return gmail, calendar

# ======================
# GMAIL FUNCTIONS
# ======================

def get_unread_human_emails(gmail, max_results=10):
    results = gmail.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        data = gmail.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()

        headers = data["payload"]["headers"]
        subject = sender = ""

        for h in headers:
            if h["name"] == "Subject":
                subject = h["value"]
            if h["name"] == "From":
                sender = h["value"]

        body = ""
        parts = data["payload"].get("parts", [])

        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    body = base64.urlsafe_b64decode(
                        part["body"]["data"]
                    ).decode("utf-8", errors="ignore")
        else:
            body = base64.urlsafe_b64decode(
                data["payload"]["body"]["data"]
            ).decode("utf-8", errors="ignore")

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
# CALENDAR FUNCTIONS
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
                "timeZone": TIMEZONE
            },
            "end": {
                "dateTime": event["end"],
                "timeZone": TIMEZONE
            }
        }
    ).execute()

def find_alternative_slots(calendar, start_dt, count=3):
    slots = []
    temp = start_dt + timedelta(hours=1)

    while len(slots) < count:
        if check_calendar_availability(calendar, temp):
            slots.append(temp.strftime("%B %d, %Y at %I:%M %p"))
        temp += timedelta(hours=1)

    return slots

# ======================
# NLP / FILTERS
# ======================

def extract_datetime_from_email(text):
    match = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4}).*?(\d{1,2}):(\d{2})\s*(AM|PM)",
        text,
        re.IGNORECASE | re.DOTALL
    )

    if not match:
        return None

    day, month, year, hour, minute, meridian = match.groups()
    dt_str = f"{day} {month} {year} {hour}:{minute} {meridian}"

    return datetime.strptime(dt_str, "%d %B %Y %I:%M %p")

def is_marketing_email(email):
    sender = email["sender"].lower()
    subject = email["subject"].lower()

    blocked_keywords = [
        "newsletter", "update", "results",
        "season", "round", "program", "opportunity"
    ]

    blocked_domains = [
        "simplilearn", "gradpartners",
        "linkedin", "mailer", "noreply"
    ]

    if any(word in subject for word in blocked_keywords):
        return True

    if any(domain in sender for domain in blocked_domains):
        return True

    return False

# ======================
# MAIN FUNCTION (USED BY UI)
# ======================

def run_ai_email_assistant():
    gmail, calendar = google_login()
    emails = get_unread_human_emails(gmail)

    for email in emails:

        if is_marketing_email(email):
            continue

        if email["id"] in memory["processed_emails"]:
            continue

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
                    "end": (
                        meeting_dt + timedelta(minutes=DEFAULT_DURATION_MINUTES)
                    ).strftime("%Y-%m-%dT%H:%M:%S")
                }

                create_calendar_event(calendar, event)
                memory["booked_slots"].append(key)

                reply = (
                    f"Thank you for the information. I have added the meeting to my "
                    f"calendar for {meeting_dt.strftime('%B %d, %Y at %I:%M %p')}."
                )
            else:
                alternatives = find_alternative_slots(calendar, meeting_dt)
                reply = (
                    "I have a scheduling conflict at the proposed time. "
                    "Would any of the following alternative slots work instead?\n\n"
                    + "\n".join(f"• {slot}" for slot in alternatives)
                )

        create_gmail_draft(
            gmail,
            email["sender"],
            "Re: " + email["subject"],
            reply
        )

        memory["processed_emails"].append(email["id"])
        save_memory(memory)

