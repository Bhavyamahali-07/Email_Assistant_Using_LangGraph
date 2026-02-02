import streamlit as st
from assistant import run_ai_email_assistant

st.title("📧 AI Email Assistant")

if st.button("▶ Run Assistant"):
    run_ai_email_assistant()
    st.success("Done! Check Gmail drafts & Calendar")
