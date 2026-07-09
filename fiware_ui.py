import os
import sys

import streamlit as st
import streamlit_authenticator as stauth
from fiware_tool import FiwareClient, Config
from ui.sidebar import get_fiware_logo, draw_sidebar_status
from ui import (
    tab_architecture,
    tab_entities,
    tab_service_groups,
    tab_subscriptions,
    tab_migration,
    tab_cratedb,
    tab_metrics,
    tab_portainer,
    tab_info,
)

st.set_page_config(page_title="FIWARE Dashboard", page_icon="🌐", layout="wide")

# --- 1. AUTH configuration ---
# Credential hash and cookie signing key must be supplied via environment
# variables. Never commit real credentials/secrets to source control.
ADMIN_PASSWORD_HASH = os.getenv("DASHBOARD_ADMIN_PASSWORD_HASH")
COOKIE_KEY = os.getenv("DASHBOARD_COOKIE_KEY")
ADMIN_EMAIL = os.getenv("DASHBOARD_ADMIN_EMAIL")

if not ADMIN_PASSWORD_HASH or not COOKIE_KEY or not ADMIN_EMAIL:
    st.error(
        "DASHBOARD_ADMIN_PASSWORD_HASH, DASHBOARD_COOKIE_KEY and DASHBOARD_ADMIN_EMAIL must be set as "
        "environment variables (see .env / docker-compose.yml)."
    )
    sys.exit(1)

credentials = {
    "usernames": {
        "admin": {
            "email": ADMIN_EMAIL,
            "name": "admin",
            "password": ADMIN_PASSWORD_HASH,
        }
    }
}

authenticator = stauth.Authenticate(
    credentials=credentials,
    cookie_name="fiware_dashboard_cookie",
    cookie_key=COOKIE_KEY,
    cookie_expiry_days=30
)

# rendering login widget
authenticator.login(fields={"Form name": "FIWARE Dashboard Login"})
authentication_status = st.session_state.get("authentication_status")
username = st.session_state.get("username")
name = st.session_state.get("name")

# --- 2. check authentication status ---
if authentication_status == False:
    st.error("Invalid username or password.")

elif authentication_status == None:
    st.warning("Enter valid credentials to sign in.")

elif authentication_status: # if login is successful, render the main dashboard:

    # Initialize configuration and store it in session state for reuse across tabs
    if "cfg" not in st.session_state:
        st.session_state.cfg = Config()

    cfg = st.session_state.cfg

    # Initialize FiwareClient and store it in session state for reuse across tabs
    if "fiware_client" not in st.session_state:
        st.session_state.fiware_client = FiwareClient(cfg)

    client = st.session_state.fiware_client

    fiware_logo = get_fiware_logo()
    if fiware_logo:
        st.sidebar.image(fiware_logo, use_container_width=True)
        st.sidebar.markdown("---")

    draw_sidebar_status(client, cfg)

    # Place the logout button in the sidebar
    authenticator.logout("Sign out", "sidebar")

    st.title("FIWARE Operations Dashboard")

    TAB_LABELS = [
        "Architecture", "Entities", "Service Groups",
        "Subscriptions", "Service Group Migration",
        "CrateDB Explorer", "Orion Statistics & Metrics", "Docker Management", "Resources",
    ]
    tabs = st.tabs(TAB_LABELS)


    with tabs[0]: tab_architecture.render(client, cfg)
    with tabs[1]: tab_entities.render(client, cfg)
    with tabs[2]: tab_service_groups.render(client, cfg)
    with tabs[3]: tab_subscriptions.render(client, cfg)
    with tabs[4]: tab_migration.render(client, cfg)
    with tabs[5]: tab_cratedb.render(client, cfg)
    with tabs[6]: tab_metrics.render(client, cfg)
    with tabs[7]: tab_portainer.render(client, cfg)
    with tabs[8]: tab_info.render(client, cfg)

