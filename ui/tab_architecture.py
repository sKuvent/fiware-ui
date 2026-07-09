import pandas as pd
import streamlit as st
from ui.architecture_helpers import render_mqtt_live


def render(client, cfg):
    st.header("System Architecture & Data Flow")

    st.graphviz_chart(
        """
        digraph {
            graph [rankdir=LR, bgcolor=transparent]
            node [shape=box, style="filled,rounded", fontname="Arial", fontsize=10]
            devices [label="🧩 Devices", fillcolor="#C1E1C1"]
            iota [label="🔌 IoT Agent", fillcolor="#00A6CE"]
            orion [label="🧠 Orion Broker", fillcolor="#FFD580"]
            ql [label="📈 QuantumLeap", fillcolor="#00A6CE"]
            crate [label="🗄️ CrateDB", fillcolor="#E0E0E0"]
            mongo [label="🍃 MongoDB", shape=cylinder, fillcolor="#AFE1AF"]

            devices -> iota     [label="MQTT"]
            iota -> orion       [label=" "]
            orion -> ql         [label=" "]
            ql -> crate         [label=" "]

            iota -> mongo [style=dashed, label="config & device state"]
            orion -> mongo [style=dashed, label="current state"]
        }
    """
    )
    st.info(
        "**Flow:** "
        "Devices → IoT Agent → Orion (real time) → QuantumLeap → CrateDB (history)"
    )

    st.subheader("📦 Module Descriptions")
    modul_data = [
        {"Module": "Device integration", "Role": "Input layer", "Description": "Collects device data and forwards it to the IoT Agent."},
        {"Module": "IoT Agent (IoTA)", "Role": "Translator", "Description": "Converts device-specific protocols into the standard FIWARE language (NGSI)."},
        {"Module": "Orion Context Broker", "Role": "Central state", "Description": "Stores only the latest value of each entity."},
        {"Module": "MongoDB", "Role": "Metadata store", "Description": "Internal database for Orion and the IoT Agent. Stores configuration and current state, not time series."},
        {"Module": "QuantumLeap", "Role": "Time-series relay", "Description": "Forwards data from Orion into the database."},
        {"Module": "CrateDB", "Role": "Historical archive", "Description": "SQL database for long-term analysis and history. Every change received from Orion is stored as a new timestamped row."},
    ]
    st.table(modul_data)
    
    st.warning(
        "**Note:** MongoDB does not store history. If data is deleted there, Orion forgets the current state and the IoT Agent loses its configuration."
    )

    # --- Live MQTT data ---
    render_mqtt_live(client)

    st.divider()

    # --- Summary ---
    st.subheader("📊 System Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("System components", len(modul_data))

    df_live_updated = st.session_state.get("_mqtt_df_display")
    if df_live_updated is not None and "status" in df_live_updated.columns:
        col2.metric("Active topics (🟢)", (df_live_updated["status"] == "🟢").sum())
    else:
        col2.metric("Active topics (🟢)", "–", delta="Click 'Fetch' first")

    try:
        client.check_mqtt_broker()
        broker_status, delta_val = "Verbunden ✅", "OK"
    except Exception:
        broker_status, delta_val = "Offline ❌", "Error"
    col3.metric("MQTT broker", broker_status, delta=delta_val)