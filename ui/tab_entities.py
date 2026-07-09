import streamlit as st
import json
from fiware_tool import filter_entities


# This function is cached and only runs every 'ttl' minutes ---
@st.cache_data(ttl=180) # 180 -> 3 minutes 
def get_cached_types_and_ids(_client):
    try:
        all_entities = _client.list_entities(limit=1000)
        unique_types = {ent.get("type") for ent in all_entities if ent.get("type")}
        available_ids = {ent.get("id") for ent in all_entities if ent.get("id")}
        
        return sorted(list(unique_types)), sorted(list(available_ids))
    except Exception as e:
        return [], []


def parse_attribute_value(raw_value: str, attribute_type: str):
    if attribute_type in {"Number", "Float", "Double"}:
        return float(raw_value)
    if attribute_type == "Integer":
        return int(raw_value)
    if attribute_type == "Boolean":
        normalized = raw_value.strip().lower()
        if normalized not in {"true", "false"}:
            raise ValueError("Boolean value must be 'true' or 'false'.")
        return normalized == "true"
    if attribute_type in {"StructuredValue", "geo:json"}:
        return json.loads(raw_value)
    return raw_value

def render(client, cfg):
    st.info(
            """
        **Entities** are the central data objects in the Orion Context Broker and represent the connected system components digitally.
        Each entity has a unique ID, a type, and a set of attributes that model operational state, measurements, and control information.

        **Lifecycle:**
        1. The IoT Agent creates the entity automatically when the first MQTT record arrives (via Service Group provisioning).
        2. Every following MQTT message only updates the value.
        3. Orion notifies active subscribers through a **Subscription** (for example QuantumLeap) about each change.
        4. QuantumLeap writes each state change as a new row into CrateDB (time series).

        **Orion keeps only the latest known state** - no time series.
        Historical data is available only through CrateDB (via QuantumLeap).
            """
    )
    st.markdown("You can fetch, filter, edit, or delete entities from this view.")

    available_types, available_ids = get_cached_types_and_ids(client)

    # ── Search area ──
    st.subheader("🔍 Search")
    col1, col2 = st.columns(2)
    with col1:
        type_options = ["Alle Typen"] + available_types
        e_type = st.selectbox(
            "Entity type",
            options=type_options,
            help="Filter by entity type. This corresponds to the device type from the Service Group.",
        )
        id_pat = st.text_input(
            "ID filter (regex)",
            placeholder="e.g. .*Cell.*",
            help="Regular expression for filtering entity IDs. Leave empty for no restriction.",
        )
    with col2:
        id_pre = st.text_input(
            "ID prefix",
            placeholder="e.g. urn:ngsi-ld:Device:",
            help="Simple text pre-filter: only entities whose ID starts with this prefix.",
        )
        limit = st.number_input(
            "Max results",
            value=100,
            min_value=1,
            max_value=1000,
            help="Maximum number of entities to return. Increase if you have many devices.",
        )

    if st.button("🔎 Search", use_container_width=True):
        search_type = None if e_type == "Alle Typen" else e_type
        with st.spinner("Loading entities from Orion Broker …"):
            results = client.list_entities(
                entity_type=search_type,
                id_pattern=id_pat or None,
                limit=int(limit),
            )
            filtered_results = filter_entities(results, id_prefix=id_pre or None)

            # Defensive post-filter: even if backend filtering behaves unexpectedly,
            # only show entities that match the selected type.
            if search_type:
                mismatched = [e for e in filtered_results if e.get("type") != search_type]
                filtered_results = [e for e in filtered_results if e.get("type") == search_type]
                if mismatched:
                    st.warning(
                        f"The backend returned {len(mismatched)} entities with a different type than '{search_type}'. "
                        "They were hidden."
                    )

            st.session_state.found_entities = filtered_results

    # ── Result list ──
    entities = st.session_state.get("found_entities")
    if not entities and "found_entities" in st.session_state:
        st.info("No entities found. Try different filters.")
        return

    if not entities:
        st.info("Start a search to display entities.")
        return

    st.success(f"**{len(entities)}** entity/entities found.")

    for i, ent in enumerate(entities):
        ent_id = ent.get("id", "Unknown ID")
        ent_type = ent.get("type", "Unknown type")
        attr_count = len([k for k in ent if k not in ("id", "type")])

        with st.expander(f"**{ent_id}**  |  Type: `{ent_type}`  |  {attr_count} attribute(s)"):
            sub_tabs = st.tabs(["👁️ View", "✏️ Edit attributes", "✏️ Edit JSON", "🗑️ Delete entity"])

            # ── Tab: View ──
            with sub_tabs[0]:
                st.caption("Full entity as currently stored in Orion Broker.")
                st.json(ent)

            # ── Tab: Edit ──
            with sub_tabs[1]:
                st.caption(
                    "Edit individual attribute values directly. Only the **value** is updated; the type stays unchanged. "
                    "For complex changes, use the **Edit JSON** tab."
                )
                updated_vals = {}
                attrs_to_edit = {k: v for k, v in ent.items() if k not in ("id", "type")}
                if not attrs_to_edit:
                    st.info("This entity has no editable attributes.")
                else:
                    cols = st.columns(2)
                    for idx, (key, val) in enumerate(attrs_to_edit.items()):
                        display_val = (
                            str(val.get("value", ""))
                            if isinstance(val, dict) and "value" in val
                            else str(val)
                        )
                        with cols[idx % 2]:
                            updated_vals[key] = st.text_input(
                                key,
                                value=display_val,
                                key=f"edit_{i}_{key}",
                                help=f"Type: {val.get('type', '?')}" if isinstance(val, dict) else None,
                            )
                    if st.button("💾 Save changes", key=f"save_ent_{i}", type="primary"):
                        try:
                            patch_payload = {}
                            for k, v in updated_vals.items():
                                if not isinstance(ent.get(k), dict):
                                    continue
                                attr_type = ent[k].get("type", "Text")
                                patch_payload[k] = {
                                    "value": parse_attribute_value(v, attr_type),
                                    "type": attr_type,
                                }

                            client.patch_entity(ent_id, patch_payload)
                            st.success("✅ Entity updated successfully!")
                        except json.JSONDecodeError:
                            st.error("Invalid JSON value for StructuredValue/geo:json attribute.")
                        except ValueError as e:
                            st.error(f"Invalid value type: {e}")
                        except Exception as e:
                            st.error(f"Error while saving: {e}")

            # ── Tab: Edit JSON ──
            with sub_tabs[2]:
                import json as _json
                st.caption(
                    "Edit the entity directly as JSON. The `id` and `type` fields are removed automatically on save "
                    "because they must not be overwritten (NGSI-v2 PATCH /attrs)."
                )
                raw_json = _json.dumps(
                    {k: v for k, v in ent.items() if k not in ("id", "type")},
                    indent=2,
                    ensure_ascii=False,
                )
                edited_json = st.text_area(
                    "Entity (JSON)",
                    value=raw_json,
                    height=400,
                    key=f"json_edit_{i}",
                )
                if st.button("💾 Save JSON", key=f"json_save_{i}", type="primary"):
                    try:
                        patch_payload = _json.loads(edited_json)
                        patch_payload.pop("id", None)
                        patch_payload.pop("type", None)
                        client.patch_entity(ent_id, patch_payload)
                        st.success("✅ Entity updated via JSON successfully!")
                    except _json.JSONDecodeError:
                        st.error("Invalid JSON - please check the syntax.")
                    except Exception as e:
                        st.error(f"Error while saving: {e}")

            # ── Tab: Delete ──
            with sub_tabs[3]:
                st.warning(
                    "⚠️ **Warning:** Deleting removes the entity permanently from Orion Broker. "
                    "Registrations are not deleted automatically. Historical data in CrateDB remains available."
                )
                confirm_key = f"confirm_delete_{i}"
                confirmed = st.checkbox(
                    f"I really want to delete `{ent_id}`",
                    key=confirm_key,
                )
                if confirmed:
                    if st.button("🗑️ Delete permanently", key=f"del_ent_{i}", type="primary"):
                        try:
                            client.delete_entity(ent_id, entity_type=ent_type)
                            st.session_state.found_entities.pop(i)
                            st.success(f"✅ Entity `{ent_id}` was deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error while deleting: {e}")
