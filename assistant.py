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
# ---------------
def google_login():
    if "oauth_done" not in st.session_state:
        st.session_state.oauth_done = False

    creds = None

    # If token already exists, just use it
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        st.session_state.oauth_done = True

    # If OAuth not done yet, start manual flow
    if not st.session_state.oauth_done:
        client_config = json.loads(
            st.secrets["google"]["credentials"]
        )

        flow = InstalledAppFlow.from_client_config(
            client_config, SCOPES
        )

        auth_url, _ = flow.authorization_url(
            prompt="consent",
            access_type="offline"
        )

        st.warning("🔐 Google Login Required (one-time)")
        st.markdown("### Step 1: Open this link")
        st.code(auth_url)

        if "auth_code" not in st.session_state:
            st.session_state.auth_code = ""

        st.markdown("### Step 2: Paste authorization code")
        st.session_state.auth_code = st.text_input(
            "Authorization code",
            value=st.session_state.auth_code,
            type="password"
        )

        if st.session_state.auth_code:
            flow.fetch_token(code=st.session_state.auth_code)
            creds = flow.credentials

            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())

            st.session_state.oauth_done = True
            st.success("✅ Google login successful. Please click **Run Assistant** again.")
            st.stop()

        else:
            st.stop()

    # Build Gmail service
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
