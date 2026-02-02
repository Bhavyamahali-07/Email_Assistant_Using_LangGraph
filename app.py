import streamlit as st
from assistant import run_ai_email_assistant
from datetime import datetime

# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="AI Email Assistant",
    page_icon="📧",
    layout="wide"
)

# -------------------------------------------------
# SESSION STATE INIT
# -------------------------------------------------
if "logs" not in st.session_state:
    st.session_state.logs = []

if "stats" not in st.session_state:
    st.session_state.stats = {
        "emails_processed": 0,
        "drafts_created": 0,
        "events_created": 0,
    }

# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.markdown(
    """
    <h1 style="text-align:center;">📧 AI Email Assistant</h1>
    <p style="text-align:center; color: gray;">
        Smart Gmail & Calendar automation with human approval
    </p>
    """,
    unsafe_allow_html=True
)

st.divider()

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
with st.sidebar:
    st.header("⚙️ Controls")

    auto_calendar = st.toggle(
        "Auto-create calendar events when free",
        value=True
    )

    st.markdown("---")

    st.header("📊 Stats")
    st.metric("Emails processed", st.session_state.stats["emails_processed"])
    st.metric("Drafts created", st.session_state.stats["drafts_created"])
    st.metric("Events created", st.session_state.stats["events_created"])

    st.markdown("---")
    st.caption("🔐 OAuth-secured • 🤖 AI-powered • 🧠 Memory enabled")

# -------------------------------------------------
# MAIN LAYOUT
# -------------------------------------------------
left, right = st.columns([2, 1])

# -------------------------------------------------
# LEFT: ACTION + PREVIEW
# -------------------------------------------------
with left:
    st.subheader("🚀 Run Assistant")

    st.info(
        "This will scan unread Gmail emails, detect meeting requests, "
        "check calendar conflicts, and create **draft replies only**."
    )

    run_btn = st.button("▶️ Run Email Assistant", use_container_width=True)

    if run_btn:
        with st.spinner("🔄 Processing emails…"):
            try:
                result = run_ai_email_assistant()

                # result is expected as a dict (safe even if None)
                if isinstance(result, dict):
                    st.session_state.stats["emails_processed"] += result.get("emails", 0)
                    st.session_state.stats["drafts_created"] += result.get("drafts", 0)
                    st.session_state.stats["events_created"] += result.get("events", 0)

                    # Logs
                    for log in result.get("logs", []):
                        st.session_state.logs.append(log)

                st.success("✅ Assistant run completed successfully")

            except Exception as e:
                st.error("❌ Error occurred while running assistant")
                st.exception(e)

    st.divider()
    st.subheader("📨 Latest Draft Preview")

    if st.session_state.logs:
        latest = st.session_state.logs[-1]
        st.markdown(f"**To:** {latest.get('to','')}")
        st.markdown(f"**Subject:** {latest.get('subject','')}")
        st.text_area(
            "Draft Body",
            latest.get("body", ""),
            height=220
        )
    else:
        st.info("No drafts yet. Run the assistant to see preview.")

# -------------------------------------------------
# RIGHT: LOGS PANEL
# -------------------------------------------------
with right:
    st.subheader("🧾 Activity Logs")

    if not st.session_state.logs:
        st.info("No activity yet.")
    else:
        for i, log in enumerate(reversed(st.session_state.logs), start=1):
            with st.expander(f"Log #{i} — {log.get('time')}"):
                st.write("📩 To:", log.get("to"))
                st.write("📝 Subject:", log.get("subject"))
                st.write("📅 Action:", log.get("action"))
                st.write("🧠 Decision:", log.get("decision"))

# -------------------------------------------------
# FOOTER
# -------------------------------------------------
st.divider()
st.caption(
    "Built with ❤️ using Python, Gmail API, Google Calendar API & Streamlit"
)
