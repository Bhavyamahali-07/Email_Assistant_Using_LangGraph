# ============================
# app.py (WORKING STREAMLIT)
# ============================

import streamlit as st
from assistant import run_ai_email_assistant

st.set_page_config(
    page_title="AI Email Assistant",
    page_icon="📧",
    layout="centered"
)

st.title("📧 AI Email Assistant")
st.caption("Minimal working reference (Gmail drafts)")

st.divider()

if "logs" not in st.session_state:
    st.session_state.logs = []

if st.button("▶️ Run Assistant"):
    with st.spinner("Running…"):
        try:
            result = run_ai_email_assistant()
            st.session_state.logs = result["logs"]
            st.success("Done!")
        except Exception as e:
            st.error("Error")
            st.exception(e)

st.divider()
st.subheader("📝 Draft Preview")

if not st.session_state.logs:
    st.info("No drafts yet")
else:
    last = st.session_state.logs[-1]
    st.write("**To:**", last["to"])
    st.write("**Subject:**", last["subject"])
    st.text_area("Body", last["body"], height=150)
