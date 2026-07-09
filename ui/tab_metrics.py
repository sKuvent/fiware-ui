import logging

import streamlit as st
import pandas as pd

logger = logging.getLogger(__name__)


def _format_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}min"


def render(client, cfg):
    st.info(
        """
        Here you can see how heavily the Orion Context Broker is loaded and whether there are errors.
        The data is **not refreshed automatically** - click the load button each time.
        """
    )

    # ─────────────────────────────────────────────
    # SECTION 1: Admin metrics (/admin/metrics)
    # ─────────────────────────────────────────────
    st.subheader("1️⃣ Requests & error rate (/admin/metrics)")
    st.caption(
        "Shows how many requests the broker has received and processed in total - "
        "and how many failed."
    )

    btn_col, reset_col = st.columns([3, 1])
    with btn_col:
        load_metrics = st.button(
            "🔄 Load metrics",
            help="Loads the current metrics from the Orion admin endpoint.",
            use_container_width=True,
            key="load_metrics_btn",
        )
    with reset_col:
        if st.button(
            "⚠️ Reset counters",
            help="Resets all metric counters to zero. Useful after a restart or for focused measurement.",
            type="primary",
            use_container_width=True,
            key="reset_metrics_btn",
        ):
            try:
                client.get_admin_metrics(reset=True)
                st.session_state.pop("metrics_data", None)
                st.success("✅ Metrics were reset.")
            except Exception as e:
                logger.warning("Failed to reset admin metrics: %s", e)
                st.error(f"Error while resetting: {e}")

    if load_metrics:
        try:
            st.session_state.metrics_data = client.get_admin_metrics()
        except Exception as e:
            logger.warning("Failed to load admin metrics: %s", e)
            st.error(f"Could not load metrics. Is the admin endpoint reachable? ({e})")
            st.session_state.pop("metrics_data", None)

    if "metrics_data" in st.session_state:
        metrics = st.session_state.metrics_data
        summary = metrics.get("sum", {}).get("sum", {})
        total_in = summary.get("incomingTransactions", 0)
        err_in = summary.get("incomingTransactionErrors", 0)
        total_out = summary.get("outgoingTransactions", 0)
        err_out = summary.get("outgoingTransactionErrors", 0)
        err_rate = (err_in / total_in * 100) if total_in > 0 else 0
        err_rate_out = (err_out / total_out * 100) if total_out > 0 else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric(
            "Incoming requests",
            total_in,
            help="Total number of API requests (for example from the IoT Agent or QuantumLeap) since start or last reset.",
        )
        m2.metric(
            "Incoming error rate",
            f"{err_rate:.2f}%",
            delta=f"{err_in} errors" if err_in else None,
            delta_color="inverse",
            help="Share of requests that were answered with an error.",
        )
        m3.metric(
            "Avg. response time",
            f"{summary.get('serviceTime', 0):.3f} s",
            help="Average time the broker needs to process a request.",
        )
        m4.metric(
            "Outgoing notifications",
            total_out,
            help="Number of subscription notifications Orion sent to recipients (for example QuantumLeap).",
        )
        m5.metric(
            "Outgoing error rate",
            f"{err_rate_out:.2f}%",
            delta=f"{err_out} errors" if err_out else None,
            delta_color="inverse",
            help="Share of notifications that could not be delivered.",
        )

        services = metrics.get("services", {})
        if services:
            st.divider()
            st.markdown("**Load distribution by service**")
            st.caption("Shows which services (for example 'smartenergy') generate how many requests.")
            combined_data = [
                {
                    "Service": name,
                    "Incoming requests": s.get("sum", {}).get("incomingTransactions", 0),
                    "Incoming errors": s.get("sum", {}).get("incomingTransactionErrors", 0),
                    "Outgoing notifications": s.get("sum", {}).get("outgoingTransactions", 0),
                    "Outgoing errors": s.get("sum", {}).get("outgoingTransactionErrors", 0),
                    "Avg. response time (s)": round(s.get("sum", {}).get("serviceTime", 0), 4),
                }
                for name, s in services.items()
            ]
            df_metrics = pd.DataFrame(combined_data)
            col_table, col_chart = st.columns([0.65, 0.35])
            with col_table:
                st.dataframe(
                    df_metrics.style.highlight_max(
                        subset=["Incoming errors", "Outgoing errors"], color="#ff4b4b66"
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            with col_chart:
                chart_df = df_metrics.melt(
                    id_vars="Service",
                    value_vars=["Incoming requests", "Outgoing notifications"],
                )
                st.bar_chart(chart_df, x="Service", y="value", color="variable", height=280)

        with st.expander("🔍 Show raw metrics JSON"):
            st.json(metrics)

    st.divider()

    # ─────────────────────────────────────────────
    # SECTION 2: Statistics (/statistics)
    # ─────────────────────────────────────────────
    st.subheader("2️⃣ Broker statistics (/statistics)")
    st.caption(
        "More detailed insight into internal wait times (semaphores) and the "
        "notification queue."
    )

    btn_col2, reset_col2 = st.columns([3, 1])
    with btn_col2:
        load_stats = st.button(
            "🔄 Load statistics",
            use_container_width=True,
            key="load_stats_btn",
        )
    with reset_col2:
        if st.button(
            "⚠️ Reset counters",
            type="primary",
            help="Resets all statistic counters to zero.",
            use_container_width=True,
            key="reset_stats_btn",
        ):
            try:
                client.get_orion_stats(reset=True)
                st.session_state.pop("stats_data", None)
                st.success("✅ Statistics were reset.")
            except Exception as e:
                logger.warning("Failed to reset Orion stats: %s", e)
                st.error(f"Error while resetting: {e}")

    if load_stats:
        try:
            st.session_state.stats_data = client.get_orion_stats()
        except Exception as e:
            logger.warning("Failed to load Orion stats: %s", e)
            st.warning(f"Statistics could not be loaded: {e}")
            st.session_state.pop("stats_data", None)

    if "stats_data" in st.session_state:
        stats = st.session_state.stats_data
        uptime_s = stats.get("uptime_in_secs", 0)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric(
            "Uptime",
            _format_uptime(uptime_s),
            help="Time since the last restart of the Orion container.",
        )
        s2.metric(
            "Measurement interval",
            f"{stats.get('measuring_interval_in_secs', '?')} s",
            help="Time window over which the current statistics are measured.",
        )
        s3.metric(
            "Accumulated total time (s)",
            stats.get("timing", {}).get("accumulated", {}).get("total", 0),
            help="Sum of all processing times since start.",
        )
        s4.metric(
            "Last call time (s)",
            stats.get("timing", {}).get("last", {}).get("total", 0),
            help="Processing time of the most recently handled request.",
        )

        # Semaphore wait times
        st.divider()
        st.markdown("**🔒 Internal wait times (semaphores)**")
        st.caption(
            "Semaphores are internal locking mechanisms. High wait times for `request`, `metrics`, or "
            "`dbConnectionPool` indicate overload of the broker or database."
        )
        sem_raw = stats.get("semWait", {})
        if sem_raw:
            sem_df = (
                pd.DataFrame(list(sem_raw.items()), columns=["Component", "Wait time (s)"])
                .sort_values("Wait time (s)", ascending=False)
            )
            c1, c2 = st.columns([0.4, 0.6])
            with c1:
                st.dataframe(sem_df, hide_index=True, use_container_width=True)
            with c2:
                st.bar_chart(sem_df, x="Component", y="Wait time (s)")
        else:
            st.info("No semaphore data available.")

        # Notification queue
        st.divider()
        st.markdown("**📬 Notification queue**")
        st.caption(
            "Shows how many subscription notifications were processed in the queue. "
            "High error counts mean QuantumLeap or another recipient is unreachable."
        )
        notif = stats.get("notifQueue", {})

        n1, n2, n3, n4 = st.columns(4)
        n1.metric(
            "Current queue size",
            notif.get("size", 0),
            help="How many notifications are currently waiting for delivery?",
        )
        n2.metric(
            "Successfully sent",
            notif.get("sentOk", 0),
            help="Number of successfully delivered notifications.",
        )
        n3.metric(
            "Failed",
            notif.get("sentError", 0),
            delta=f"{notif.get('sentError', 0)} errors" if notif.get("sentError", 0) else None,
            delta_color="inverse",
            help="Number of undelivered notifications (for example QuantumLeap unreachable).",
        )
        n4.metric(
            "Avg. queue wait time",
            f"{notif.get('avgTimeInQueue', 0):.2f} s",
            help="Average time a notification spends in the queue.",
        )

        notif_df = pd.DataFrame([
            {"Metric": "Received",            "Value": notif.get("in", 0)},
            {"Metric": "Outgoing",            "Value": notif.get("out", 0)},
            {"Metric": "Successfully sent",   "Value": notif.get("sentOk", 0)},
            {"Metric": "Errors",              "Value": notif.get("sentError", 0)},
            {"Metric": "Dropped",             "Value": notif.get("reject", 0)},
            {"Metric": "Queue size",          "Value": notif.get("size", 0)},
            {"Metric": "Total wait time (s)", "Value": round(notif.get("timeInQueue", 0), 2)},
            {"Metric": "Avg. wait time (s)",  "Value": round(notif.get("avgTimeInQueue", 0), 2)},
        ])
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            st.dataframe(notif_df, hide_index=True, use_container_width=True)
        with c2:
            chart_notif = notif_df[
                notif_df["Metric"].isin(
                    ["Received", "Outgoing", "Successfully sent", "Errors", "Dropped"]
                )
            ]
            st.bar_chart(chart_notif, x="Metric", y="Value")

        # API endpoint calls
        with st.expander("🔗 API endpoint calls (requests by route & method)"):
            st.caption("Shows which API routes were called how often.")
            rows = [
                {"Endpoint": path, "HTTP method": method, "Calls": count}
                for path, methods in stats.get("counters", {}).get("requests", {}).items()
                for method, count in methods.items()
            ]
            if rows:
                st.dataframe(
                    pd.DataFrame(rows).sort_values("Calls", ascending=False),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No API calls registered yet.")

    st.divider()