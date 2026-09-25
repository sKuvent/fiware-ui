import streamlit as st
import pandas as pd
import re
from datetime import datetime


def _fmt_timestamp(ms: int) -> str:
    """Converts a Unix millisecond timestamp into a readable date."""
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(ms)


def render(client, cfg):
    # 1. Prepare data for the table
    data = {
        "Timestamp": ["publishedtime", "timeinstant", "time_index", "ql_time"],
        "Created by": ["MQTT ingestion layer", "IoT Agent", "Orion Context Broker", "QuantumLeap"],
        "Meaning": [
            "Time when the MQTT ingestion layer receives the message from the broker.",
            "Time when the IoT Agent transforms the payload into the FIWARE data model.",
            "Update time of the entity in Orion Context Broker.",
            "Processing time in QuantumLeap before storage in CrateDB."
        ]
    }

    df = pd.DataFrame(data)

    # 2. Define DOT code for the diagram


    st.info(
        """
        CrateDB serves as the system's **long-term archive**. Every change received by QuantumLeap 
        from the Orion Context Broker is stored there as a new timestamped row.

        **Table naming conventions:**
        - Prefix `mt` = multi-tenancy (tenant schema, e.g. `mtsmartenergy`)
        - Prefix `et` = entity type (device type, e.g. `etdevicea`)

        Multiple timestamps are created within the data pipeline by different components. 
        All timestamps are stored in CrateDB so processing times can be traced. 
        """
    )

    crate_tabs = st.tabs(["🔍 Data preview", "💻 SQL query tool"])


    # ─────────────────────────────────────
    # TAB 1 – Data preview
    # ─────────────────────────────────────────────
    with crate_tabs[0]:
        if st.button("🔄 Load tables", use_container_width=True, key="load_tables_btn"):
            with st.spinner("Loading table overview from CrateDB …"):
                try:
                    raw_tables = client.execute_crate_query(
                        "SELECT table_name, table_schema, number_of_shards, number_of_replicas "
                        "FROM information_schema.tables "
                        "WHERE table_schema IN ('mtsmartenergy') "
                        "ORDER BY table_schema, table_name"
                    )
                    st.session_state.crate_tables = raw_tables or []
                    if raw_tables:
                        st.success(f"✅ {len(raw_tables)} table(s) loaded.")
                    else:
                        st.warning("No tables found. Has data already reached CrateDB?")
                except Exception as e:
                    st.error(f"Error loading tables: {e}")

        tables = st.session_state.get("crate_tables", [])

        st.caption(
            "Choose a table and view the newest (or oldest) entries. "
            "`time_index` is a Unix timestamp in milliseconds."
        )

        tables = st.session_state.get("crate_tables", [])
        if not tables:
            st.info("No tables loaded yet. Click 'Load tables'.")
        else:
            table_names = [t["table_name"] for t in tables]

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                selected_table = st.selectbox(
                    "Table",
                    options=table_names,
                    help="Choose the table whose data you want to inspect.",
                    key="preview_table_select",
                )
            with col2:
                order = st.selectbox(
                    "Sort order",
                    ["DESC - newest first", "ASC - oldest first"],
                    help="Controls whether the newest or oldest entries are shown.",
                    key="preview_order_select",
                )
            with col3:
                row_limit = st.number_input(
                    "Rows",
                    value=10,
                    min_value=1,
                    max_value=500,
                    help="Maximum number of rows to display.",
                    key="preview_limit",
                )

            order_kw = "DESC" if order.startswith("DESC") else "ASC"

            if st.button("🔍 Load preview", type="primary", use_container_width=True, key="preview_btn"):
                with st.spinner(f"Loading {row_limit} rows from `{selected_table}` …"):
                    try:
                        sql = (
                            f'SELECT * FROM mtsmartenergy."{selected_table}" '
                            f"ORDER BY time_index {order_kw} LIMIT {int(row_limit)}"
                        )
                        st.session_state.preview_data = client.execute_crate_query(sql)
                        st.session_state.preview_table = selected_table
                        st.session_state.preview_sql = sql
                    except Exception as e:
                        st.error(f"Preview failed: {e}")
                        st.session_state.pop("preview_data", None)

            if "preview_data" in st.session_state:
                preview_data = st.session_state.preview_data
                preview_table = st.session_state.get("preview_table", selected_table)
                if preview_data:
                    df_preview = pd.DataFrame(preview_data)

                    # Show time_index in a readable format
                    if "time_index" in df_preview.columns:
                        loc = df_preview.columns.get_loc("time_index")
                        if isinstance(loc, int):
                            df_preview.insert(
                                loc + 1,
                                "Zeitpunkt",
                                df_preview["time_index"].apply(_fmt_timestamp),
                            )

                    st.caption(f"Executed query: `{st.session_state.get('preview_sql', '')}`")
                    st.dataframe(df_preview, use_container_width=True, hide_index=True)

                    csv = df_preview.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        f"⬇️ Export {len(df_preview)} rows as CSV",
                        data=csv,
                        file_name=f"preview_{preview_table}.csv",
                        mime="text/csv",
                    )
                else:
                    st.info(f"The table `{preview_table}` is currently empty.")

    # ─────────────────────────────────────────────
    # TAB 2 – SQL query tool
    # ─────────────────────────────────────────────
    with crate_tabs[1]:
        st.caption(
            "Run arbitrary SQL queries directly against CrateDB. "
            "Useful for analysis, debugging, or checking column names."
        )
        st.warning(
            "⚠️ **Warning:** Write operations (`DELETE`, `UPDATE`, `DROP`) are possible "
            "and can permanently change data. Use only if you know what you are doing."
        )

        default_sql = "SELECT * FROM mtsmartenergy.etmbms ORDER BY time_index DESC LIMIT 5"
        sql_query = st.text_area(
            "SQL query",
            value=default_sql,
            height=120,
            help="CrateDB supports standard SQL. Tables are stored in the 'mtsmartenergy' schema.",
            key="sql_query_input",
        )

        destructive_pattern = re.compile(r"^\s*(DELETE|UPDATE|DROP|ALTER|TRUNCATE|INSERT|CREATE)\b", re.IGNORECASE)
        is_destructive_query = bool(destructive_pattern.search(sql_query or ""))
        if is_destructive_query:
            st.error(
                "Destructive SQL detected. Confirm explicitly before execution."
            )
            st.checkbox(
                "I understand this query can modify or delete data.",
                key="confirm_destructive_sql",
            )

        col_run, col_link = st.columns([2, 1])
        with col_run:
            if st.button("▶️ Run query", type="primary", use_container_width=True, key="run_sql_btn"):
                if is_destructive_query and not st.session_state.get("confirm_destructive_sql", False):
                    st.error("Confirmation required for destructive SQL queries.")
                    return
                with st.spinner("Running query …"):
                    try:
                        results = client.execute_crate_query(sql_query)
                        st.session_state.sql_results = results
                    except Exception as e:
                        st.error(f"Database error: {e}")
                        st.session_state.pop("sql_results", None)
        with col_link:
            st.link_button(
                "🌐 Open CrateDB UI",
                url=client.config.crate_url,
                help="Opens the CrateDB web dashboard with the full SQL editor in a new tab.",
                use_container_width=True,
            )

        if "sql_results" in st.session_state:
            results = st.session_state.sql_results
            if results:
                df_sql = pd.DataFrame(results)
                st.success(f"**{len(df_sql)}** row(s) returned.")
                st.dataframe(df_sql, use_container_width=True, hide_index=True)
                csv = df_sql.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Export result as CSV",
                    data=csv,
                    file_name="crate_query_result.csv",
                    mime="text/csv",
                )
            else:
                st.info("The query returned no results (empty table or no match).")
