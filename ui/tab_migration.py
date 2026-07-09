import streamlit as st
import json
import re
from fiware_tool import filter_entities


def render(client, cfg):
    st.info(
        """
        Here you can replace an existing **Service Group** (device configuration in the IoT Agent)
        with a new one - for example if the API key or attribute names have changed.
        """
    )
    
    st.markdown(
        """
        **Process in 3 steps:**
        1. Find and load the existing Service Group
        2. Enter the new configuration
        3. Identify affected entities and run the migration

        Note: New entities are created automatically as soon as the IoT Agent receives the next MQTT message with the new API key.
        """
    )
    st.warning(
        "⚠️ **Warning:** This action can permanently delete data in Orion. "
        "Historical data in CrateDB remains available. Please review all options carefully."
    )

    st.divider()

    # ─────────────────────────────────────────────
    # 1: Load old service group
    # ─────────────────────────────────────────────
    st.subheader("1️⃣ Load existing Service Group")
    st.caption("Select the API key of the Service Group you want to migrate.")

    if st.button("🔄 Load all Service Groups", use_container_width=True, key="load_all_sgs_btn"):
        with st.spinner("Loading Service Groups …"):
            res = client.list_service_groups()
            st.session_state.all_sgs_for_migration = res.get("services", [])

    all_sgs = st.session_state.get("all_sgs_for_migration", [])

    if not all_sgs:
        st.info("Click 'Load all Service Groups' to see available options.")
    else:
        sg_options = {f"{s.get('apikey')}  ({s.get('entity_type', '?')})": s for s in all_sgs}
        selected_label = st.selectbox(
            "Select Service Group",
            options=list(sg_options.keys()),
            help="All Service Groups registered in the IoT Agent. Choose the one you want to migrate.",
            key="migration_sg_select",
        )
        if st.button("✅ Confirm selection", use_container_width=True, key="confirm_sg_select_btn"):
            sg = sg_options[selected_label]
            st.session_state.legacy_sg = sg
            st.session_state["old_ak"] = sg.get("apikey", "")
            st.session_state["old_type"] = sg.get("entity_type", "")
            st.session_state["old_pre"] = sg.get("entityNameExp", "")
            st.rerun()

    sg_data = st.session_state.get("legacy_sg", {})

    if sg_data:
        st.success(f"✅ Service Group `{sg_data.get('apikey')}` loaded - type: `{sg_data.get('entity_type')}`")
    else:
        st.info("No Service Group loaded yet. Select one from the list.")
        return

    st.divider()

    # ─────────────────────────────────────────────
    # 2: new configuration input
    # ─────────────────────────────────────────────
    st.subheader("2️⃣ Enter new configuration")
    st.caption(
        "Adjust the fields as needed. The current values of the loaded Service Group are already filled in. "
        "Only change what has actually changed."
    )

    col1, col2 = st.columns(2)
    with col1:
        apikey = st.text_input(
            "New API key",
            value=sg_data.get("apikey", ""),
            key="old_ak",
            help="API key of the new Service Group. It can stay the same or be changed.",
        )
        entity_type = st.text_input(
            "Entity type",
            value=sg_data.get("entity_type", ""),
            key="old_type",
            help="The entity type in Orion, for example `DeviceTypeA`.",
        )
    with col2:
        prefix = st.text_input(
            "Name expression (entityNameExp)",
            value=st.session_state.get("old_pre", ""),
            key="old_pre",
            help="Expression used to build the entity ID, for example `'urn:ngsi-ld:Device:' + id`.",
        )

    st.markdown("**Attributes** - Mapping: MQTT payload key → NGSI attribute")
    new_attrs_json = st.text_area(
        "Attributes (JSON array)",
        value=json.dumps(sg_data.get("attributes", []), indent=2),
        height=180,
        key=f"attrs_{len(sg_data)}",
        help="List of active attributes. Each object has `object_id`, `name`, and `type`.",
    )

    col_s, col_c = st.columns(2)
    with col_s:
        st.markdown("**Static attributes**")
        new_static_json = st.text_area(
            "Static attributes (JSON array)",
            value=json.dumps(sg_data.get("static_attributes", []), indent=2),
            height=120,
            key=f"static_{len(sg_data)}",
            help="Fixed values automatically attached to each entity.",
        )
    with col_c:
        st.markdown("**Commands**")
        new_cmds_json = st.text_area(
            "Commands (JSON array)",
            value=json.dumps(sg_data.get("commands", []), indent=2),
            height=120,
            key=f"cmds_{len(sg_data)}",
            help="Control commands that can be sent to the device.",
        )

    st.divider()

    # ─────────────────────────────────────────────
    # 3: entities identification and migration execution
    # ─────────────────────────────────────────────
    st.subheader("3️⃣ Identify affected entities")
    st.caption(
        "Click the button to find all entities currently linked to this Service Group. "
        "They can optionally be deleted in the next step."
    )

    if st.button("🔎 Find affected entities", use_container_width=True):
        with st.spinner("Loading entities from Orion Broker …"):
            try:
                match = re.search(r"'([^']+)'", sg_data.get("entityNameExp", ""))
                filter_prefix = match.group(1) if match else None
                old_entities = client.list_entities(entity_type=sg_data.get("entity_type"))
                old_entities = filter_entities(old_entities, id_prefix=filter_prefix)
                st.session_state.migration_plan = {
                    "count": len(old_entities),
                    "ids": [e["id"] for e in old_entities],
                }
            except Exception as e:
                st.error(f"Error loading entities: {e}")

    if "migration_plan" in st.session_state:
        plan = st.session_state.migration_plan
        count = plan["count"]

        if count > 0:
            st.warning(
                f"**{count}** entity/entities are linked to this Service Group and may be affected."
            )
            with st.expander(f"🗂️ Show IDs of the {count} affected entities"):
                for eid in plan["ids"]:
                    st.code(eid)
        else:
            st.success("No linked entities found - the migration can proceed without data loss.")

        st.divider()
        st.subheader("4️⃣ Choose and run migration options")
        st.caption("Choose which steps should be executed. All disabled options will be skipped.")

        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            do_create = st.checkbox(
                "✅ Create new Service Group",
                value=True,
                help="Creates the new Service Group in the IoT Agent using the values entered above.",
            )
        with col_opt2:
            do_delete_sg = st.checkbox(
                "🗑️ Delete existing Service Group",
                value=False,
                help="Removes the original Service Group from the IoT Agent. "
                     "New devices would not be recognized until the new one is active.",
            )
        with col_opt3:
            do_delete_ent = st.checkbox(
                "🗑️ Delete existing entities",
                value=False,
                help=f"Deletes all {count} found entities from Orion. "
                     "Historical data in CrateDB remains available. "
                     "New entities are created automatically on the next MQTT record.",
            )

        actions = []
        if do_create:
            actions.append("Create new Service Group")
        if do_delete_sg:
            actions.append("Delete existing Service Group")
        if do_delete_ent:
            actions.append(f"Delete {count} entity/entities from Orion")

        if actions:
            st.info("**Planned actions:** " + " → ".join(actions))
        else:
            st.warning("No action selected. Please enable at least one option.")

        st.divider()
        confirm_key = "confirm_migration"
        st.checkbox(
            "I have reviewed the planned actions and want to start the migration",
            key=confirm_key,
        )

        if st.session_state.get(confirm_key):
            if st.button("🚀 Run migration now", type="primary", use_container_width=True):
                errors = []
                with st.status("Running migration …", expanded=True) as status:
                    try:
                        if do_create:
                            st.write("➕ Creating new Service Group …")
                            try:
                                client.create_service_group(
                                    apikey,
                                    entity_type,
                                    prefix,
                                    json.loads(new_attrs_json),
                                    json.loads(new_static_json),
                                    json.loads(new_cmds_json),
                                )
                                st.write("✅ New Service Group created.")
                            except json.JSONDecodeError:
                                errors.append("Invalid JSON in attributes/commands.")
                            except Exception as e:
                                errors.append(f"Create Service Group: {e}")

                        if do_delete_sg:
                            st.write("🗑️ Deleting existing Service Group …")
                            try:
                                client.delete_service_group(sg_data.get("apikey"))
                                st.write("✅ Existing Service Group deleted.")
                            except Exception as e:
                                errors.append(f"Delete Service Group: {e}")

                        if do_delete_ent:
                            st.write(f"🗑️ Deleting {count} entity/entities …")
                            for eid in plan["ids"]:
                                try:
                                    client.delete_entity(eid, entity_type=sg_data.get("entity_type"))
                                    client.delete_registration_by_entity(eid, entity_type=sg_data.get("entity_type"))
                                except Exception as e:
                                    errors.append(f"Entity `{eid}`: {e}")
                            if not errors:
                                st.write(f"✅ {count} entity/entities deleted.")

                        if errors:
                            status.update(label="Migration completed with errors", state="error")
                            for err in errors:
                                st.error(err)
                        else:
                            status.update(label="Migration completed successfully! ✅", state="complete")
                            st.session_state.pop("migration_plan", None)
                            st.session_state.pop("legacy_sg", None)

                    except Exception as e:
                        status.update(label="Unexpected error", state="error")
                        st.error(f"Unexpected error: {e}")

                st.info(
                    "💡 New entities are created automatically as soon as the IoT Agent "
                    "receives the next MQTT message with the new API key."
                )
