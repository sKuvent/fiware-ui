import streamlit as st

def render(client, cfg):
    st.header("📚 FIWARE References & Documentation")
    st.markdown(
            "This page provides a structured overview of the most important documentation, "
            "API references, and guides for operating and managing the FIWARE infrastructure."
    )
    
    st.divider()

    # --- CATEGORY 1: Orion Context Broker ---
    st.subheader("🌐 Orion Context Broker & Metrics")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### Orion Statistics")
        st.write(
                "Details for monitoring Orion's internal status to analyze subscription bottlenecks."
        )
        st.link_button(
            "📖 Orion Statistics Doc", 
            "https://fiware-orion.readthedocs.io/en/master/admin/statistics.html",
            use_container_width=True
        )

    with col2:
        st.markdown("### Orion Metrics API")
        st.write(
                "Details for monitoring Orion metrics to analyze performance and resource usage."
        )
        st.link_button(
            "📖 Orion Metrics Doc", 
            "https://fiware-orion.readthedocs.io/en/master/admin/metrics_api.html",
            use_container_width=True
        )

    with col3:
        st.markdown("### Core Orion documentation")
        st.write(
                "The official documentation for administration, API specifications (NGSIv2 / NGSI-LD), "
                "and Context Broker performance tuning."
        )
        st.link_button(
            "📖 Orion Manuals", 
            "https://fiware-orion.readthedocs.io/",
            use_container_width=True
        )

    st.divider()

    # --- CATEGORY 2: IoT Agents ---
    st.subheader("🔌 IoT Agents & Device Integration")
    col3, col4, col5 = st.columns(3)

    with col3:
        st.markdown("### IoT Agent Node Library API")
        st.write(
                "The API reference for the underlying Node.js library used by FIWARE IoT Agents."
        )
        st.link_button(
            "📖 IoT Agent API GitHub", 
            "https://github.com/telefonicaid/iotagent-node-lib/blob/master/doc/api.md",
            use_container_width=True
        )

    with col4:
        st.markdown("### IoT Agent for JSON / MQTT")
        st.write(
            "Specific documentation for IoT Agent JSON, commonly used for communication via "
            "MQTT-based device messaging and payload-driven IoT structures."
        )
        st.link_button(
            "📖 IoTA JSON Doc", 
            "https://fiware-iotagent-json.readthedocs.io/",
            use_container_width=True
        )

    with col5:
        st.markdown("### IoT Agent configuration")
        st.write("All configuration details for the IoT Agent.")
        st.link_button(
            "📖 IoTA configuration", 
            "https://fiware-iotagent-json.readthedocs.io/en/latest/installationguide.html#configuration",
            use_container_width=True
        )

    st.divider()

    # --- CATEGORY 3: Performance ---
    st.subheader("⚡ Performance & Optimization")
    col6, col7 = st.columns(2)

    with col6:
        st.markdown("### Orion Context Broker Performance Tuning")
        st.write(
                "Guide for optimizing Orion Context Broker performance."
        )
        st.link_button(
            "📖 Orion Performance Tuning", 
            "https://fiware-orion.readthedocs.io/en/latest/admin/perf_tuning.html",
            use_container_width=True
        )

    with col7:
        st.markdown("### IoT Agent Performance Tuning")
        st.write(
                "Guide for optimizing IoT Agent JSON performance."
        )
        st.link_button(
            "📖 IoTA Performance Tuning", 
            "https://fiware-iotagent-json.readthedocs.io/en/latest/installationguide.html#high-performance-configuration",
            use_container_width=True
        )

    st.divider()

    # --- CATEGORY 4: Data Persistence & Further Reading ---
    st.subheader("🗄️ Data Persistence & Smart Data Models")
    
    with st.expander("📊 Time Series & CrateDB / QuantumLeap", expanded=True):
        st.markdown(
                "Historical data from the Context Broker is stored through **QuantumLeap** into a **CrateDB** instance."
        )
        c_col1, c_col2 = st.columns(2)
        with c_col1:
                st.link_button("📖 QuantumLeap configuration", "https://quantumleap.readthedocs.io/en/latest/admin/configuration/")
        with c_col2:
                st.link_button("📖 CrateDB SQL reference", "https://crate.io/docs/crate/reference/en/latest/")

    with st.expander("💡 FIWARE Data Models & Standards", expanded=False):
        st.markdown("To ensure interoperability, entities should follow the official guidelines.")
        st.link_button("🌐 Smart Data Models Initiative", "https://smartdatamodels.org/")
