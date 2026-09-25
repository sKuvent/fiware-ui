import streamlit as st
import os

PORTAINER_URL = os.getenv("PORTAINER_URL", "http://localhost:9000")


def render(client, cfg):
    st.header("🐳 Docker Management with Portainer")

    st.link_button("Open Portainer", url=PORTAINER_URL, type="primary", help="Opens the Portainer web UI in a new browser tab.")

    st.divider()

    st.info(
        "Use Portainer to manage containers, inspect logs, and restart services. "
        "This dashboard no longer exposes MQTT mapping configuration here."
    )

    st.caption("Open Portainer from the button above to manage the deployment stack.")