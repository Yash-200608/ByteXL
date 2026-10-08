import streamlit as st

st.set_page_config(page_title="ByteXL", page_icon="🩺", layout="wide")

pages = [
    st.Page("views/upload.py", title="Upload", icon="📤", default=True),
    st.Page("views/timeline.py", title="Timeline", icon="🗓️"),
    st.Page("views/document.py", title="Document", icon="📄"),
    st.Page("views/trends.py", title="Trends", icon="📈"),
    st.Page("views/confirm.py", title="Confirm", icon="✅"),
]
st.navigation(pages).run()
