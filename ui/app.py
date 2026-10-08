import streamlit as st

from common import NAV

st.set_page_config(page_title="PERRY · Your Personal Health Assistant", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")

pages = [st.Page(path, title=label, icon=icon, default=(i == 0)) for i, (path, label, icon) in enumerate(NAV)]
st.navigation(pages, position="hidden").run()
