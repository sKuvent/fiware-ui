import streamlit as st
import json

DEFAULT_SERVICE_GROUP_JSON={
    "apikey": "my-api-key",
    "entity_type": "MyEntityType",
    "entityNameExp": "'urn:ngsi-ld:Device:' + id",
    "explicitAttrs": False,
    "resource": "/iot/json",
    "timezone": "Europe/Berlin",
    "attributes": [
        {"object_id": "v", "name": "voltage", "type": "Number"},
        {"object_id": "i", "name": "current", "type": "Number"},
        {"object_id": "t", "name": "temperature", "type": "Number"}
    ],
    "static_attributes": [
        {"name": "source", "type": "Text", "value": "sensorA"}
    ],
    "commands": [
        {"name": "reset", "type": "command"}
    ]
}

def render(client, cfg):
    st.info(
        """
        A **Service Group** is the configuration in the IoT Agent that describes:
        - Which **devices** (identified by API key) belong to the group
        - How **raw data** from the MQTT payload is mapped to standardized NGSI attributes
        - Which **entity type** is created in Orion

        Without a matching Service Group, the IoT Agent will not recognize incoming MQTT messages.
        """
    )

    # ─────────────────────────────────────────────
    # Load & display existing service groups
    # ─────────────────────────────────────────────
    if st.button("🔄 Load existing Service Groups", use_container_width=True):
        res = client.list_service_groups()
        st.session_state.list_of_sgs = res.get("services", [])

    if "list_of_sgs" in st.session_state:
        sgs = st.session_state.list_of_sgs
        if not sgs:
            st.info("No Service Groups found. Create a new one below.")
        else:
            st.success(f"**{len(sgs)}** Service Group(s) found.")

            for idx, sg in enumerate(sgs):
                ak = sg.get("apikey", "?")
                res_path = sg.get("resource", "/iot/json")
                ent_type = sg.get("entity_type", "?")
                attr_count = len(sg.get("attributes", []))
                static_count = len(sg.get("static_attributes", []))

                # Initialize session state for builder lists per group
                for key, field in [
                    (f"edit_attrs_{idx}", "attributes"),
                    (f"edit_static_{idx}", "static_attributes"),
                    (f"edit_commands_{idx}", "commands"),
                ]:
                    if key not in st.session_state:
                        st.session_state[key] = sg.get(field, [])

                with st.expander(
                    f"🔑 `{ak}`  |  Type: **{ent_type}**  |  {attr_count} attrs / {static_count} static",
                    expanded=False,
                ):
                    view_tab, edit_tab, builder_tab = st.tabs([
                        "👁️ Overview",
                        "🛠️ Edit JSON",
                        "🧱 Edit builder",
                    ])

                    # ── Overview ─────────────────────────────────────────────
                    with view_tab:
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Entity type", ent_type, help="Entity type created in Orion")
                        m2.metric("Explicit attrs", str(sg.get("explicitAttrs", False)), help="Only explicitly defined attributes are used")
                        m3.metric("Active attributes", attr_count, help="Number of mapped MQTT attributes")

                        st.caption(f"MQTT topic: `iot/json/{ak}/<device-mac>/attrs`")
                        st.caption(f"entityNameExp: `{sg.get('entityNameExp', '–')}`")

                        attr_tabs = st.tabs(["📐 Attributes", "📌 Static attributes", "⚡ Commands"])
                        with attr_tabs[0]:
                            st.caption("Mapped measurements: MQTT payload key → NGSI attribute name")
                            st.json(sg.get("attributes", []))
                        with attr_tabs[1]:
                            st.caption("Fixed values automatically attached to each entity")
                            st.json(sg.get("static_attributes", []))
                        with attr_tabs[2]:
                            st.json(sg.get("commands", []))

                        st.divider()
                        confirm_key = f"confirm_del_sg_{idx}"
                        st.checkbox(f"Confirm deletion of `{ak}`", key=confirm_key)
                        if st.session_state.get(confirm_key):
                            if st.button("🗑️ Delete Service Group permanently", key=f"del_{idx}", type="primary"):
                                try:
                                    client.delete_service_group(ak, res_path)
                                    st.session_state.list_of_sgs.pop(idx)
                                    st.success("✅ Service Group deleted.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")

                    # ── Edit JSON ──────────────────────────────────────────────
                    with edit_tab:
                        st.caption("Edit the core fields directly. Enter attributes, static attrs, and commands as JSON arrays.")
                        c1, c2 = st.columns(2)
                        with c1:
                            e_type = st.text_input("Entity Type", value=sg.get("entity_type", ""), key=f"et_{idx}")
                            e_exp = st.text_input(
                                "Name expression (entityNameExp)",
                                value=sg.get("entityNameExp", ""),
                                key=f"ee_{idx}",
                                help="Expression for generating the entity name, for example `'urn:ngsi-ld:Device:' + id`",
                            )
                        with c2:
                            explicit = st.checkbox(
                                "Explicit attributes",
                                value=sg.get("explicitAttrs", False),
                                key=f"ea_{idx}",
                                help="If enabled: only attributes defined here are forwarded to Orion.",
                            )

                        a_json = st.text_area("Attributes (JSON array)", value=json.dumps(sg.get("attributes", []), indent=2), height=180, key=f"at_{idx}")
                        s_json = st.text_area("Static attributes (JSON array)", value=json.dumps(sg.get("static_attributes", []), indent=2), height=120, key=f"st_{idx}")
                        c_json = st.text_area("Commands (JSON-Array)", value=json.dumps(sg.get("commands", []), indent=2), height=80, key=f"cm_{idx}")

                        if st.button("💾 Save changes", key=f"save_{idx}", use_container_width=True):
                            try:
                                parsed_attrs = json.loads(a_json)
                                parsed_static = json.loads(s_json)
                                parsed_cmds = json.loads(c_json)
                                client.update_service_group(
                                    apikey=ak, resource=res_path, entity_type=e_type,
                                    explicitAttrs=explicit, entity_name_exp=e_exp,
                                    attributes=parsed_attrs,
                                    static_attributes=parsed_static,
                                    commands=parsed_cmds,
                                )
                                st.session_state.list_of_sgs[idx].update({
                                    "entity_type": e_type, "explicitAttrs": explicit,
                                    "entityNameExp": e_exp, "attributes": parsed_attrs,
                                    "static_attributes": parsed_static, "commands": parsed_cmds,
                                })
                                st.session_state[f"edit_attrs_{idx}"] = parsed_attrs
                                st.session_state[f"edit_static_{idx}"] = parsed_static
                                st.session_state[f"edit_commands_{idx}"] = parsed_cmds
                                st.success("✅ Service Group updated!")
                                st.rerun()
                            except json.JSONDecodeError:
                                st.error("Invalid JSON - please check the syntax.")
                            except Exception as e:
                                st.error(f"Error: {e}")

                    # ── Edit builder ─────────────────────────────────────
                    with builder_tab:
                        st.caption("Edit attributes, static values, and commands through a form instead of raw JSON.")
                        c1b, c2b = st.columns(2)
                        with c1b:
                            e_type_b = st.text_input("Entity Type", value=sg.get("entity_type", ""), key=f"edit_type_{idx}")
                            e_exp_b = st.text_input("Name expression", value=sg.get("entityNameExp", ""), key=f"edit_exp_{idx}")
                        with c2b:
                            explicit_b = st.checkbox("Explicit attributes", value=sg.get("explicitAttrs", False), key=f"edit_explicit_{idx}")

                        st.divider()

                        def cb_add_attr(c_idx):
                            obj = st.session_state.get(f"tmp_e_obj_{c_idx}", "")
                            name = st.session_state.get(f"tmp_e_name_{c_idx}", "")
                            atype = st.session_state.get(f"tmp_e_type_{c_idx}", "Number")
                            if obj and name:
                                st.session_state[f"edit_attrs_{c_idx}"].append({"object_id": obj, "name": name, "type": atype})
                                st.session_state[f"tmp_e_obj_{c_idx}"] = ""
                                st.session_state[f"tmp_e_name_{c_idx}"] = ""

                        def cb_add_static(c_idx):
                            name = st.session_state.get(f"tmp_e_sname_{c_idx}", "")
                            val = st.session_state.get(f"tmp_e_sval_{c_idx}", "")
                            stype = st.session_state.get(f"tmp_e_stype_{c_idx}", "Text")
                            if name and val:
                                st.session_state[f"edit_static_{c_idx}"].append({"name": name, "type": stype, "value": val})
                                st.session_state[f"tmp_e_sname_{c_idx}"] = ""
                                st.session_state[f"tmp_e_sval_{c_idx}"] = ""

                        def cb_add_cmd(c_idx):
                            name = st.session_state.get(f"tmp_e_cname_{c_idx}", "")
                            if name:
                                st.session_state[f"edit_commands_{c_idx}"].append({"name": name, "type": "command"})
                                st.session_state[f"tmp_e_cname_{c_idx}"] = ""

                        # Attributes
                        st.markdown("**📐 Attributes** - Mapping: MQTT payload key → NGSI attribute")
                        col_in1, col_in2, col_in3, col_btn = st.columns([2, 2, 2, 1])
                        col_in1.text_input("MQTT key (object_id)", placeholder="v", key=f"tmp_e_obj_{idx}", help="Key in the incoming MQTT JSON payload")
                        col_in2.text_input("NGSI name", placeholder="voltage", key=f"tmp_e_name_{idx}", help="Attribute name in Orion / CrateDB")
                        col_in3.selectbox("Type", ["Number", "Text", "Boolean", "StructuredValue"], key=f"tmp_e_type_{idx}")
                        col_btn.write(""); col_btn.write("")
                        col_btn.button("➕", key=f"btn_e_attr_{idx}", on_click=cb_add_attr, args=(idx,))

                        for a_idx, attr in enumerate(st.session_state[f"edit_attrs_{idx}"]):
                            c_t, c_b = st.columns([6, 1])
                            c_t.markdown(f"• `{attr.get('object_id')}` ➡️ **{attr.get('name')}** ({attr.get('type')})")
                            if c_b.button("🗑️", key=f"del_e_attr_{idx}_{a_idx}_{attr.get('name')}"):
                                st.session_state[f"edit_attrs_{idx}"].pop(a_idx)
                                st.rerun()
                        if not st.session_state[f"edit_attrs_{idx}"]:
                            st.caption("No attributes defined yet.")

                        st.divider()

                        # Static attributes
                        st.markdown("**📌 Static attributes** - Fixed values automatically attached to each entity")
                        col_st1, col_st2, col_st3, col_st_btn = st.columns([2, 2, 2, 1])
                        col_st1.text_input("Name", placeholder="source", key=f"tmp_e_sname_{idx}")
                        col_st2.text_input("Value", placeholder="value", key=f"tmp_e_sval_{idx}")
                        col_st3.selectbox("Type", ["Text", "Number", "Boolean"], key=f"tmp_e_stype_{idx}")
                        col_st_btn.write(""); col_st_btn.write("")
                        col_st_btn.button("➕", key=f"btn_e_stat_{idx}", on_click=cb_add_static, args=(idx,))

                        for s_idx, attr in enumerate(st.session_state[f"edit_static_{idx}"]):
                            c_t, c_b = st.columns([6, 1])
                            c_t.markdown(f"• **{attr.get('name')}** = `{attr.get('value')}` ({attr.get('type')})")
                            if c_b.button("🗑️", key=f"del_e_stat_{idx}_{s_idx}_{attr.get('name')}"):
                                st.session_state[f"edit_static_{idx}"].pop(s_idx)
                                st.rerun()
                        if not st.session_state[f"edit_static_{idx}"]:
                            st.caption("No static attributes defined yet.")

                        st.divider()

                        # Commands
                        st.markdown("**⚡ Commands** - Control commands that can be sent to the device")
                        col_cmd1, col_cmd_btn = st.columns([5, 1])
                        col_cmd1.text_input("Command name", placeholder="reset", key=f"tmp_e_cname_{idx}")
                        col_cmd_btn.write(""); col_cmd_btn.write("")
                        col_cmd_btn.button("➕", key=f"btn_e_cmd_{idx}", on_click=cb_add_cmd, args=(idx,))

                        for c_idx, cmd in enumerate(st.session_state[f"edit_commands_{idx}"]):
                            c_t, c_b = st.columns([6, 1])
                            c_t.markdown(f"• ⚡ **{cmd.get('name')}**")
                            if c_b.button("🗑️", key=f"del_e_cmd_{idx}_{c_idx}_{cmd.get('name')}"):
                                st.session_state[f"edit_commands_{idx}"].pop(c_idx)
                                st.rerun()
                        if not st.session_state[f"edit_commands_{idx}"]:
                            st.caption("No commands defined yet.")

                        st.divider()
                        if st.button("💾 Save changes (builder)", key=f"save_builder_{idx}", use_container_width=True):
                            try:
                                client.update_service_group(
                                    apikey=ak, resource=res_path,
                                    entity_type=e_type_b, explicitAttrs=explicit_b, entity_name_exp=e_exp_b,
                                    attributes=st.session_state[f"edit_attrs_{idx}"],
                                    static_attributes=st.session_state[f"edit_static_{idx}"],
                                    commands=st.session_state[f"edit_commands_{idx}"],
                                )
                                st.session_state.list_of_sgs[idx].update({
                                    "entity_type": e_type_b, "explicitAttrs": explicit_b,
                                    "entityNameExp": e_exp_b,
                                    "attributes": st.session_state[f"edit_attrs_{idx}"],
                                    "static_attributes": st.session_state[f"edit_static_{idx}"],
                                    "commands": st.session_state[f"edit_commands_{idx}"],
                                })
                                st.success("✅ Service Group (builder) updated!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

    st.divider()

    # ─────────────────────────────────────────────
    # Create new service group
    # ─────────────────────────────────────────────
    with st.expander("➕ Create new Service Group", expanded=False):
        st.caption("Choose between the guided builder or the direct JSON editor.")

        new_tabs = st.tabs(["🧱 Builder", "🛠️ JSON editor"])

        # ── New builder ──────────────────────────────────────────────────────
        with new_tabs[0]:
            for key, default in [("builder_attrs", []), ("builder_static", []), ("builder_commands", [])]:
                if key not in st.session_state:
                    st.session_state[key] = default

            col1, col2 = st.columns(2)
            with col1:
                sg_key = st.text_input("API key *", help="Unique key - must match the MQTT topic.", key="b_key")
                sg_type = st.text_input("Entity type *", value="BatteryStatus", help="Entity type in Orion, for example `DeviceTypeA`.", key="b_type")
                sg_resource = st.text_input("Resource", value="/iot/json", key="b_res", help="MQTT resource path (default: `/iot/json`)")
            with col2:
                sg_exp = st.text_input("Name expression", value="'urn:ngsi-ld:Device:' + id", key="b_exp", help="Defines how the entity ID is formed in Orion.")
                sg_tz = st.text_input("Time zone", value="Europe/Berlin", key="b_tz")

            st.divider()

            def add_attribute():
                obj = st.session_state.get("tmp_obj_id", "")
                name = st.session_state.get("tmp_attr_name", "")
                if obj and name:
                    st.session_state.builder_attrs.append({"object_id": obj, "name": name, "type": st.session_state.get("tmp_attr_type", "Number")})
                    st.session_state.tmp_obj_id = ""
                    st.session_state.tmp_attr_name = ""

            def add_static():
                name = st.session_state.get("tmp_stat_name", "")
                val = st.session_state.get("tmp_stat_val", "")
                if name and val:
                    st.session_state.builder_static.append({"name": name, "type": st.session_state.get("tmp_stat_type", "Text"), "value": val})
                    st.session_state.tmp_stat_name = ""
                    st.session_state.tmp_stat_val = ""

            def add_command():
                name = st.session_state.get("tmp_cmd_name", "")
                if name:
                    st.session_state.builder_commands.append({"name": name, "type": "command"})
                    st.session_state.tmp_cmd_name = ""

            col_a, col_b, col_c = st.columns(3)

            with col_a:
                st.markdown("**📐 Attributes**")
                st.caption("MQTT payload key → NGSI attribute")
                st.text_input("MQTT-Key (object_id)", placeholder="v", key="tmp_obj_id")
                st.text_input("NGSI-Name", placeholder="voltage", key="tmp_attr_name")
                st.selectbox("Type", ["Number", "Text", "Boolean", "StructuredValue"], key="tmp_attr_type")
                st.button("➕ Add attribute", key="btn_add_attr", on_click=add_attribute, use_container_width=True)
                st.divider()
                for i, attr in enumerate(st.session_state.builder_attrs):
                    c_t, c_b = st.columns([4, 1])
                    c_t.caption(f"`{attr['object_id']}` ➡️ **{attr['name']}** ({attr['type']})")
                    if c_b.button("🗑️", key=f"del_b_attr_{i}"):
                        st.session_state.builder_attrs.pop(i)
                        st.rerun()
                if not st.session_state.builder_attrs:
                    st.caption("No attributes yet.")

            with col_b:
                st.markdown("**📌 Static attributes**")
                st.caption("Fixed values for each entity")
                st.text_input("Name", placeholder="source", key="tmp_stat_name")
                st.selectbox("Type", ["Text", "Number", "Boolean"], key="tmp_stat_type")
                st.text_input("Value", placeholder="value", key="tmp_stat_val")
                st.button("➕ Add static attribute", key="btn_add_stat", on_click=add_static, use_container_width=True)
                st.divider()
                for i, attr in enumerate(st.session_state.builder_static):
                    c_t, c_b = st.columns([4, 1])
                    c_t.caption(f"**{attr['name']}** = `{attr['value']}` ({attr['type']})")
                    if c_b.button("🗑️", key=f"del_b_stat_{i}"):
                        st.session_state.builder_static.pop(i)
                        st.rerun()
                if not st.session_state.builder_static:
                    st.caption("No static attributes yet.")

            with col_c:
                st.markdown("**⚡ Commands**")
                st.caption("Control commands for the device")
                st.text_input("Command name", placeholder="reset", key="tmp_cmd_name")
                st.button("➕ Add command", key="btn_add_cmd", on_click=add_command, use_container_width=True)
                st.divider()
                for i, cmd in enumerate(st.session_state.builder_commands):
                    c_t, c_b = st.columns([4, 1])
                    c_t.caption(f"⚡ **{cmd['name']}**")
                    if c_b.button("🗑️", key=f"del_b_cmd_{i}"):
                        st.session_state.builder_commands.pop(i)
                        st.rerun()
                if not st.session_state.builder_commands:
                    st.caption("No commands yet.")

            st.divider()
            if st.button("✅ Create Service Group", key="btn_create_builder", use_container_width=True):
                if not sg_key:
                    st.error("Please enter an API key!")
                else:
                    try:
                        res = client.create_service_group(
                            apikey=sg_key, entity_type=sg_type, entity_name_exp=sg_exp,
                            attributes=st.session_state.builder_attrs,
                            static_attributes=st.session_state.builder_static,
                            commands=st.session_state.builder_commands,
                            resource=sg_resource, timezone=sg_tz,
                        )
                        st.success("🎉 Service Group created successfully!")
                        st.json(res)
                        st.session_state.builder_attrs = []
                        st.session_state.builder_static = []
                        st.session_state.builder_commands = []
                    except Exception as e:
                        st.error(f"Error while creating: {e}")

        # ── New JSON editor ────────────────────────────────────────────────────
        with new_tabs[1]:
            st.caption("For advanced users: enter the full Service Group configuration as JSON.")
            payload_input = st.text_area(
                "Service Group JSON",
                value=json.dumps(DEFAULT_SERVICE_GROUP_JSON, indent=2),
                height=350,
            )
            if st.button("📨 Create Service Group (JSON)", use_container_width=True):
                try:
                    result = client.create_service_group_json(json.loads(payload_input))
                    st.success("✅ Service Group created successfully!")
                    st.json(result)
                except json.JSONDecodeError:
                    st.error("Invalid JSON - please check the syntax.")
                except Exception as e:
                    st.error(f"Error: {e}")

