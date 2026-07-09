import streamlit as st
import json


def render(client, cfg):
    st.info("Subscriptions let you receive notifications when an entity state changes. For example, QuantumLeap can be informed about updates so data can be stored historically in CrateDB.")

    sub_subtabs = st.tabs(["📋 Existing subscriptions", "➕ Create new subscription"])

    # ─────────────────────────────────────────────
    # TAB 1 – Display existing subscriptions
    # ─────────────────────────────────────────────
    with sub_subtabs[0]:
        st.markdown("This view shows all subscriptions registered with Orion Broker. You can activate/deactivate, edit, or delete them.")

        if st.button("🔄 Load subscriptions from broker", use_container_width=True):
            st.session_state.subs = client.list_subscriptions()
            st.rerun()

        if "subs" in st.session_state and st.session_state.subs:
            st.success(f"{len(st.session_state['subs'])} subscription(s) found.")

            for i, sub in enumerate(st.session_state.subs):
                sub_id = sub.get("id", "Unbekannte ID")
                entity_type = sub.get("subject", {}).get("entities", [{}])[0].get("type", "Alle Typen")
                description = sub.get("description", "No description")
                status = sub.get("status", "unknown")
                status_icon = "🟢" if status == "active" else "🔴"
                notif_url = sub.get("notification", {}).get("httpCustom", {}).get("url", "N/A")

                with st.expander(
                    f"{status_icon} {description}  |  Entity type: **{entity_type}**  |  Target: `{notif_url}`",
                    expanded=False,
                ):
                    tab_view, tab_edit = st.tabs(["👁️ Overview & control", "✏️ Edit JSON"])

                    with tab_view:
                        # Status toggle
                        is_active = status == "active"
                        col_toggle, col_delete = st.columns([3, 1])
                        with col_toggle:
                            new_state = st.toggle(
                                f"Subscription is **{'active'  if is_active else 'inactive'}** - toggle here",
                                value=is_active,
                                key=f"toggle_{sub_id}",
                                help="Active = Orion sends notifications. Inactive = no data is forwarded to QuantumLeap.",
                            )
                            if new_state != is_active:
                                try:
                                    new_status = "active" if new_state else "inactive"
                                    client.update_subscription(sub_id, {"status": new_status})
                                    st.toast(f"✅ Status set to '{new_status}'")
                                    st.session_state.subs[i]["status"] = new_status
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error changing status: {e}")

                        with col_delete:
                            confirm_key = f"confirm_del_{sub_id}"
                            if st.checkbox("Confirm deletion", key=confirm_key, help="Check this first, then press the delete button"):
                                if st.button("🗑️ Delete now", key=f"del_{sub_id}", type="primary"):
                                    try:
                                        client.delete_subscription(sub_id)
                                        st.session_state.subs = [s for s in st.session_state.subs if s.get("id") != sub_id]
                                        st.toast("Subscription deleted.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error deleting: {e}")

                        st.divider()
                        st.caption("Full subscription configuration (view only):")
                        st.json(sub)

                    with tab_edit:
                        st.caption(
                            "You can edit the subscription directly as JSON. "
                            "The `id` is removed automatically on save because it is assigned by the broker."
                        )
                        sub_json_edit = st.text_area(
                            "Subscription configuration (JSON)",
                            value=json.dumps(sub, indent=2),
                            height=350,
                            key=f"edit_payload_{i}",
                        )
                        if st.button("💾 Save changes", key=f"save_sub_{i}", type="primary"):
                            try:
                                new_data = json.loads(sub_json_edit)
                                new_data.pop("id", None)
                                client.update_subscription(sub_id, new_data)
                                st.success("✅ Subscription updated successfully!")
                            except json.JSONDecodeError:
                                st.error("Invalid JSON - please check the syntax.")
                            except Exception as e:
                                st.error(f"Error while saving: {e}")

                # Statistics outside the tabs, but still within the expander context
                notif = sub.get("notification", {})
                stats_val = notif.get("timesSent", 0)
                last_notif = notif.get("lastNotification", "N/A")
                fails = notif.get("failsCounter", 0)
                last_fail = notif.get("lastFailure", "N/A")

                st.markdown("**📊 Subscription statistics**")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric(
                    "Sent notifications",
                    stats_val,
                    help="How many messages has Orion sent to the target since creation?",
                )
                col2.metric(
                    "Last success",
                    last_notif.split("T")[0] if "T" in last_notif else last_notif,
                    help="Date of the last successfully delivered notification",
                )
                col3.metric(
                    "Total errors",
                    fails,
                    help="How often did delivery fail? Common cause: the target service (for example QuantumLeap) is unreachable.",
                )
                clean_fail = last_fail.split("T")[0] if "T" in last_fail else "None"
                col4.metric(
                    "Last error",
                    clean_fail,
                    delta_color="inverse",
                    help="Date of the last failure",
                )
                if last_fail != "N/A" and last_fail > last_notif:
                    st.error("⚠️ Warning: The last known delivery attempt failed. Check whether QuantumLeap is running.")
        else:
            st.info("No subscriptions loaded yet. Click 'Load subscriptions from broker' above.")

    # ─────────────────────────────────────────────
    # TAB 2 – Create new subscription
    # ─────────────────────────────────────────────
    with sub_subtabs[1]:
        st.markdown("You can create a subscription in two ways: with the **wizard** or directly with the **JSON editor**.")

        create_tabs = st.tabs(["🧙 Wizard", "🛠️ JSON editor"])

        # ── Wizard ──
        with create_tabs[0]:
            st.caption(
                "Choose an existing device group (Service Group) - the wizard will create the matching "
                "subscription for QuantumLeap automatically."
            )
            if st.button("📂 Load available device groups", key="load_sgs_builder"):
                st.session_state.list_of_sgs = client.list_service_groups().get("services", [])

            if "list_of_sgs" in st.session_state and st.session_state.list_of_sgs:
                sg_options = {sg.get("apikey"): sg for sg in st.session_state.list_of_sgs}
                selected_key = st.selectbox(
                    "Device group (API key)",
                    options=list(sg_options.keys()),
                    help="Each device group corresponds to a device type. Choose the group you want to enable data recording for.",
                )
                selected_sg = sg_options[selected_key]

                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    sub_desc = st.text_input(
                        "Description",
                        value=f"QuantumLeap subscription for {selected_sg.get('entity_type')}",
                        help="Free-form text used to identify this subscription",
                    )
                    ql_url = st.text_input(
                        "Target URL (QuantumLeap)",
                        value="http://ht-fiware.ht.etech.fb3.fh-dortmund.de:8080/v2/notify",
                        help="Address where Orion sends the updates. In the Docker network this is usually the URL below.",
                    )
                with col2:
                    pattern = st.text_input(
                        "Device ID filter (regex)",
                        value=".*",
                        help="'.*' means all devices of this type. You can also specify a single ID.",
                    )
                    sub_type = st.text_input(
                        "Entity type",
                        value=selected_sg.get("entity_type"),
                        disabled=True,
                        help="Automatically copied from the selected device group.",
                    )

                attrs = [a["name"] for a in selected_sg.get("attributes", [])]
                selected_attrs = st.multiselect(
                    "Which attributes should be stored?",
                    options=attrs,
                    help="Leave empty to record all attributes. Otherwise only the selected ones are stored.",
                )

                payload = {
                    "description": sub_desc,
                    "subject": {
                        "entities": [{"idPattern": pattern, "type": sub_type}],
                        "condition": {"attrs": []},
                    },
                    "notification": {
                        "httpCustom": {"url": ql_url, "headers": {"Fiware-TimeIndex-Attribute": "dateModified"}},
                        "attrs": selected_attrs,
                        "onlyChangedAttrs": True,
                        "metadata": [ "dateCreated", "dateModified"],
                    }
                }

                st.caption("Preview of the subscription that will be created:")
                st.json(payload)

                if st.button("✅ Register subscription with Orion Broker", type="primary"):
                    try:
                        client.create_subscription(payload)
                        st.success("🎉 Subscription created successfully! QuantumLeap will now store all changes for this device type.")
                    except Exception as e:
                        st.error(f"Error creating subscription: {e}")
            else:
                st.info("Click 'Load available device groups' to start the wizard.")

        # ── JSON editor ──
        with create_tabs[1]:
            st.caption("For advanced users: enter the subscription directly as JSON. The structure must follow the NGSI-v2 Subscription API.")
            sub_json_raw = st.text_area(
                "Subscription JSON",
                value=json.dumps(
                    {
                        "description": "Notify QuantumLeap",
                        "subject": {"entities": [{"idPattern": ".*"}]},
                        "notification": {"http": {"url": "http://quantumleap:8668/v2/notify"}},
                    },
                    indent=2,
                ),
                height=300,
            )
            if st.button("📨 Create subscription", type="primary"):
                try:
                    client.create_subscription(json.loads(sub_json_raw))
                    st.success("✅ Subscription created!")
                except json.JSONDecodeError:
                    st.error("Invalid JSON - please check the syntax.")
                except Exception as e:
                    st.error(f"Error: {e}")
