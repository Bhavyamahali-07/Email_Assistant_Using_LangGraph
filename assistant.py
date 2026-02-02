# ================================
# assistant.py (WORKING REFERENCE)
# ================================

import os
import json
import base64
import re
from datetime import datetime
from email.mime.text import MIMEText

import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ----------------
# CONFIG
# ----------------
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

# ----------------
# GOOGLE LOGIN
# ----------------
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
            st.warning("🔐 Google Login Required")
            st.code(auth_url)

            code = st.text_input("Paste authorization code", type="password")
            if not code:
                st.stop()

            flow.fetch_token(code=code)
            creds = flow.credentials

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# ----------------
# FETCH EMAILS
# ----------------
def get_emails(service):
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=5
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="full"
        ).execute()

        headers = {
            h["name"].lower(): h["value"]
            for h in msg["payload"]["headers"]
        }

        body = ""
        payload = msg["payload"]

        if "data" in payload.get("body", {}):
            body = base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode(errors="ignore")

        emails.append({
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "body": body
        })

    return emails

# ----------------
# CREATE DRAFT
# ----------------
def create_draft(service, to_email, subject, body):
    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()

# ----------------
# MAIN FUNCTION
# ----------------
def run_ai_email_assistant():
    gmail = google_login()
    emails = get_emails(gmail)

    logs = []

    for e in emails:
        reply = "Thanks for your email. I will get back to you shortly."

        create_draft(
            gmail,
            e["from"],
            "Re: " + e["subject"],
            reply
        )

        logs.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "to": e["from"],
            "subject": e["subject"],
            "body": reply
        })

    return {
        "emails": len(emails),
        "drafts": len(logs),
        "logs": logs
    }
