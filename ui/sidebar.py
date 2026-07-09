import logging
import os
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

logger = logging.getLogger(__name__)

FIWARE_LOGO_URL = "https://www.fiware.org/custom/brand-guide/img/logo/fiware/primary/png/logo-fiware.png"
LOGO_FILENAME = "fiware_logo.png"

# Single source of truth for all system health checks: (client method name, display label).
# Used both for the cached status probe and the "run now" button, so they never drift apart.
SERVICE_CHECKS = [
    ("check_orion", "Orion Broker"),
    ("check_cratedb", "CrateDB"),
    ("check_iota", "IoT Agent"),
    ("check_mqtt_broker", "MQTT Broker"),
]


def get_fiware_logo():
    """Returns the local logo path, downloading it once on first use."""
    if os.path.exists(LOGO_FILENAME):
        return LOGO_FILENAME
    try:
        response = requests.get(FIWARE_LOGO_URL, stream=True, timeout=5)
        response.raise_for_status()
        with open(LOGO_FILENAME, "wb") as f:
            f.write(response.content)
        return LOGO_FILENAME
    except requests.exceptions.RequestException as e:
        logger.warning("Failed to download FIWARE logo: %s", e)
    except OSError as e:
        logger.warning("Failed to save FIWARE logo to %s: %s", LOGO_FILENAME, e)
    return None


# 1. Cached function for the status checks (valid for 60 seconds)
# The '_' before client tells Streamlit to ignore the complex object
@st.cache_data(ttl=60, show_spinner=False)
def fetch_system_status(_client):
    """Runs the checks in parallel and caches the result for 60 seconds."""
    # Uses threads so a slow/unreachable service doesn't block the others
    with ThreadPoolExecutor(max_workers=len(SERVICE_CHECKS)) as executor:
        future_to_label = {
            executor.submit(getattr(_client, method_name)): label
            for method_name, label in SERVICE_CHECKS
        }
        results = {}
        for future in future_to_label:
            label = future_to_label[future]
            try:
                future.result()
                results[label] = f"🟢 **{label}:** Online"
            except Exception as e:
                logger.debug("Health check failed for %s: %s", label, e)
                results[label] = f"🔴 **{label}:** Offline"

    return results


def draw_sidebar_status(client, cfg):
    # Load status from cache (runs blazingly fast)
    status_results = fetch_system_status(client)

    with st.sidebar:
        st.header("🌐 System Status")
        with st.container(border=True):
            # Display results from cache
            for _, label in SERVICE_CHECKS:
                st.markdown(status_results.get(label, f"⚪ **{label}:** Unknown"))

            if st.button("🔄 Refresh status", use_container_width=True):
                # Explicitly clear the cache to force a fresh measurement
                fetch_system_status.clear()
                st.rerun()

        st.divider()

        with st.expander("⚙️ Configuration"):
            cfg.orion_url = st.text_input("Orion URL", cfg.orion_url, key="cfg_orion_url")
            cfg.iota_url = st.text_input("IoT Agent URL", cfg.iota_url, key="cfg_iota_url")
            cfg.crate_url = st.text_input("CrateDB URL", cfg.crate_url, key="cfg_crate_url")
            cfg.mqtt_broker_url = st.text_input("MQTT Broker URL", cfg.mqtt_broker_url, key="cfg_mqtt_url")
            cfg.fiware_service = st.text_input("Service", cfg.fiware_service, key="cfg_service")
            cfg.fiware_servicepath = st.text_input("Service Path", cfg.fiware_servicepath, key="cfg_path")

            if st.button("Run system check", use_container_width=True):
                with st.spinner("Checking connections live..."):
                    try:
                        for method_name, _ in SERVICE_CHECKS:
                            getattr(client, method_name)()
                        st.success("All systems are reachable!")
                        # Also refresh the sidebar cache on success
                        fetch_system_status.clear()
                    except Exception as e:
                        st.error(f"Connection error: {e}")