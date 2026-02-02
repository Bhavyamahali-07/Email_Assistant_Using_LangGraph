# =====================================================
# AI EMAIL ASSISTANT – FINAL STREAMLIT SAFE VERSION
# =====================================================

import os
import json
import base64
import re
from datetime import datetime, timedelta, timezone

from email.mime.text import MIMEText

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
# GOOGLE LOGIN (STREAMLIT SAFE)
# ======================
def google_login():
    creds = None

    # Load existing token
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 🔐 Read OAuth config from Streamlit Secrets
            client_config = json.loads(
                st.secrets["google"]["credentials"]
            )

            flow = InstalledAppFlow.from_client_config(
                client_config,
                SCOPES
            )

            # ✅ CLOUD-SAFE: NO BROWSER REQUIRED
            auth_url, _ = flow.authorization_url(
                prompt="consent"
            )

            st.warning("🔐 Google Authorization Required")
            st.markdown(
                f"""
                1. Open this URL in a **new browser tab**  
                2. Login with Google  
                3. Allow permissions  
                4. Copy the **authorization code**  
                """
            )
            st.code(auth_url)

            auth_code = st.text_input(
                "📋 Paste the authorization code here:",
                type="password"
            )

            if not auth_code:
                st.stop()

            flow.fetch_token(code=auth_code)
            creds = flow.credentials

        # Save token
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    gmail_service = build("gmail", "v1", credentials=creds)
    calendar_service = build("calendar", "v3", credentials=creds)

    return gmail_service, calendar_service




# ======================
# EMAIL HELPERS
# ======================
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

        headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
        body = ""

        parts = data["payload"].get("parts", [])
        for part in parts:
            if part["mimeType"] == "text/plain":
                body = base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode("utf-8", errors="ignore")

        emails.append({
            "id": msg["id"],
            "sender": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "body": body
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
                create_calendar_event(
                    calendar,
                    meeting_dt,
                    email["subject"] or "Meeting"
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
                    "I currently have a scheduling conflict at the proposed time. "
                    "Could you please suggest an alternative slot?"
                )

        create_gmail_draft(
            gmail,
            email["sender"],
            "Re: " + email["subject"],
            reply.strip()
        )

    save_memory(memory)
