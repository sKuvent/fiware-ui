import json

import pandas as pd
import streamlit as st


def _parse_last_seen(series: pd.Series) -> pd.Series:
    """Parse mixed timestamp formats into naive UTC datetimes."""
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    numeric = pd.to_numeric(series, errors="coerce")

    num_mask = numeric.notna()
    if num_mask.any():
        values = numeric[num_mask].astype("float64")
        abs_values = values.abs()

        sec_mask = abs_values < 1e11
        ms_mask = (abs_values >= 1e11) & (abs_values < 1e14)
        us_mask = (abs_values >= 1e14) & (abs_values < 1e17)
        ns_mask = abs_values >= 1e17

        if sec_mask.any():
            parsed.loc[values[sec_mask].index] = pd.to_datetime(
                values[sec_mask], unit="s", errors="coerce", utc=True
            ).dt.tz_localize(None)
        if ms_mask.any():
            parsed.loc[values[ms_mask].index] = pd.to_datetime(
                values[ms_mask], unit="ms", errors="coerce", utc=True
            ).dt.tz_localize(None)
        if us_mask.any():
            parsed.loc[values[us_mask].index] = pd.to_datetime(
                values[us_mask], unit="us", errors="coerce", utc=True
            ).dt.tz_localize(None)
        if ns_mask.any():
            parsed.loc[values[ns_mask].index] = pd.to_datetime(
                values[ns_mask], unit="ns", errors="coerce", utc=True
            ).dt.tz_localize(None)

    text_mask = parsed.isna()
    if text_mask.any():
        parsed.loc[text_mask] = pd.to_datetime(
            series[text_mask], errors="coerce", utc=True
        ).dt.tz_localize(None)

    return parsed


def _status_circle_from_age(age_minutes: float) -> str:
    """Return traffic-light status based on age in minutes."""
    if pd.isna(age_minutes) or age_minutes < 0:
        return "⚪"
    if age_minutes < 2:
        return "🟢"
    if age_minutes < 10:
        return "🟡"
    return "🔴"


def render_mqtt_live(client):
    """Render live MQTT table and payload detail section."""
    if "mqtt_listener_initialized" not in st.session_state:
        try:
            client.subscribe_topic("#")
            st.session_state.mqtt_listener_initialized = True
        except Exception as mqtt_err:
            st.sidebar.warning(f"MQTT subscription delayed: {mqtt_err}")

    if "last_mqtt_data" not in st.session_state:
        st.session_state.last_mqtt_data = None

    st.subheader("Received MQTT data")
    st.markdown("Shows the last received message from the MQTT topics.")

    if st.button("🔄 Fetch data from MQTT broker", key="mqtt_refresh_btn", use_container_width=True):
        with st.spinner("Fetching current payload data..."):
            fetched_payload = client.getLastMQTTPayload()
            if fetched_payload:
                st.session_state.last_mqtt_data = fetched_payload
            else:
                st.warning("No data received from the client.")

    fetched_data = st.session_state.last_mqtt_data
    if not fetched_data:
        st.info("Click the button above to analyze the current MQTT topics.")
        return

    df = pd.DataFrame(fetched_data)

    # Ensure required columns exist
    for col in ["topic", "last_seen"]:
        if col not in df.columns:
            df[col] = "Unknown" if col == "topic" else pd.Timestamp.now()

    df["last_seen"] = _parse_last_seen(df["last_seen"])
    df = df.sort_values("last_seen", ascending=False).reset_index(drop=True)

    now = pd.Timestamp.now()
    df["age_min"] = (now - df["last_seen"]).dt.total_seconds() / 60
    df["status"] = df["age_min"].apply(_status_circle_from_age)

    display_cols = ["status", "topic", "last_seen"]
    if "payload" in df.columns:
        display_cols.append("payload")

    df_display = df[display_cols].reset_index(drop=True)
    st.session_state["_mqtt_df_display"] = df_display

    def _on_table_select():
        state = st.session_state.get("mqtt_live_table")
        df_d = st.session_state.get("_mqtt_df_display")

        if state and "rows" in state.get("selection", {}) and state["selection"]["rows"] and df_d is not None:
            selected_row_idx = state["selection"]["rows"][0]
            if selected_row_idx < len(df_d):
                st.session_state["_mqtt_sel_topic"] = df_d.iloc[selected_row_idx]["topic"]
        else:
            st.session_state.pop("_mqtt_sel_topic", None)

    st.dataframe(
        df_display,
        column_config={
            "status": st.column_config.TextColumn("Status", width="small"),
            "topic": st.column_config.TextColumn("MQTT Topic", width="large"),
            "last_seen": st.column_config.DatetimeColumn("Zuletzt gesehen", format="DD.MM.YYYY HH:mm:ss"),
            "payload": None,
        },
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select=_on_table_select,
        key="mqtt_live_table",
    )

    sel_topic = st.session_state.get("_mqtt_sel_topic")
    if sel_topic and sel_topic in df_display["topic"].values:
        matching_rows = df_display[df_display["topic"] == sel_topic]
        if matching_rows.empty:
            return

        row = matching_rows.iloc[0]
        st.markdown("---")
        st.subheader(f"Details: {sel_topic}")

        if "payload" in df_display.columns and pd.notna(row["payload"]):
            try:
                payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]

                if isinstance(payload, dict):
                    if len(payload) == 1 and isinstance(list(payload.values())[0], list):
                        key = list(payload.keys())[0]
                        p_df = pd.DataFrame(payload[key])
                        time_cols = [
                            c for c in p_df.columns
                            if any(x in c.lower() for x in ["last seen", "seen"])
                        ]

                        if time_cols:
                            try:
                                t_col = time_cols[0]
                                p_df[t_col] = _parse_last_seen(p_df[t_col])
                                p_df["Status"] = (
                                    (pd.Timestamp.now() - p_df[t_col]).dt.total_seconds() / 60
                                ).apply(_status_circle_from_age)
                                p_df = p_df[["Status"] + [c for c in p_df.columns if c != "Status"]]
                            except Exception:
                                pass
                        st.dataframe(p_df, use_container_width=True, hide_index=True)
                    else:
                        p_df = pd.DataFrame(list(payload.items()), columns=["Attribute", "Value"])
                        st.dataframe(p_df, use_container_width=True, hide_index=True)
                else:
                    st.info(f"Payload (text/value): {payload}")
            except Exception as e:
                st.error(f"Could not display payload: {e}")
                st.json(row["payload"])
        else:
            st.warning("No payload data received.")
