import streamlit as st

st.set_page_config(page_title="ByteXL", page_icon="🩺", layout="wide")

pages = [
    st.Page("pages/upload.py", title="Upload", icon="📤", default=True),
    st.Page("pages/timeline.py", title="Timeline", icon="🗓️"),
    st.Page("pages/document.py", title="Document", icon="📄"),
    st.Page("pages/trends.py", title="Trends", icon="📈"),
    st.Page("pages/confirm.py", title="Confirm", icon="✅"),
]
st.navigation(pages).run()
