#!/usr/bin/env python3
"""
FIWARE Migration Tool for Orion Context Broker + IoT Agent JSON

Use cases
- List entities by type
- Patch existing Orion entities
- Delete old Orion entities
- Create a new IoT Agent service group (V2 strategy)
- Validate entity schemas roughly before/after migration

Examples
python fiware_migration_tool.py list --type BatteryStatus
python fiware_migration_tool.py patch --type BatteryStatus --add-schema-version v2 --set-source MBMS
python fiware_migration_tool.py delete --type BatteryStatus --id-prefix urn:example:device:BatteryStatus:
python fiware_migration_tool.py create-service-group \
  --apikey KV-BATT-MBMS-Status-V2 \
  --entity-type BatteryStatusV2 \
    --entity-name-exp "'urn:example:device:BatteryStatusV2:' + id" \
  --attributes '[{"object_id":"State","name":"state","type":"Text"},{"object_id":"Reason","name":"reason","type":"Text"},{"object_id":"Heartbeat","name":"heartbeat","type":"StructuredValue"}]' \
  --static-attributes '[{"name":"source","type":"Text","value":"MBMS"},{"name":"schemaVersion","type":"Text","value":"v2"}]'

Environment variables
- ORION_URL          default http://localhost:1026
- IOTA_URL           default http://localhost:4041
- CRATE_URL          default http://localhost:4200
- MQTT_BROKER_URL    default mqtt://localhost:1883
- QL_PROXY_URL       default http://localhost:8080
- FIWARE_SERVICE     default smartenergy
- FIWARE_SERVICEPATH default /
- REQUEST_TIMEOUT    default 20

Notes
- This tool targets NGSIv2 Orion endpoints.
- PATCH /v2/entities/{id}/attrs is used for updating/adding attributes.
- For many entities, pagination is handled using limit/offset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
import paho.mqtt.client as mqtt
from urllib.parse import urlparse
import time
from datetime import datetime
import requests
import logging
from paho.mqtt.enums import CallbackAPIVersion

# Logger configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("FIWARE-Tool")

@dataclass
class Config:
    orion_url: str = os.getenv("ORION_URL", "http://localhost:1026")
    iota_url: str = os.getenv("IOTA_URL", "http://localhost:4041")
    crate_url: str = os.getenv("CRATE_URL", "http://localhost:4200")
    mqtt_broker_url: str = os.getenv("MQTT_BROKER_URL", "mqtt://localhost:1883")
    ql_proxy_url: str = os.getenv("QL_PROXY_URL", "http://localhost:8080")
    fiware_service: str = os.getenv("FIWARE_SERVICE", "smartenergy")
    fiware_servicepath: str = os.getenv("FIWARE_SERVICEPATH", "/")
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))

    @property
    def fiware_headers(self) -> Dict[str, str]:
        return {
            "fiware-service": self.fiware_service,
            "fiware-servicepath": self.fiware_servicepath,
        }

    @property
    def fiware_json_headers(self) -> Dict[str, str]:
        headers = dict(self.fiware_headers)
        headers["Content-Type"] = "application/json"
        return headers


class FiwareClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.mqtt = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
        self.mqtt_history: Dict[str, Dict[str, Any]] = {}

        # Bind callbacks directly during initialization
        self.mqtt.on_message = self.on_message

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.config.request_timeout)
        resp = self.session.request(method, url, **kwargs)
        return resp
        
    def subscribe_topic(self, topic: str):
        self.mqtt.subscribe(topic)
        logger.info("Topic abonniert: %s", topic)

    def on_message(self, client, userdata, msg):
        try:
            topic_name = msg.topic
            payload_str = msg.payload.decode('utf-8', errors='replace')   
            # print(f"📩 Message received on {topic_name}") 
            
            # Store or update the entry for this specific topic
            self.mqtt_history[topic_name] = {
                "topic": topic_name,
                "payload": payload_str,
                "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Format suitable for Pandas
            }
        except Exception as e:
            logger.error("Fehler im MQTT-Callback: %s", e)

    def getLastMQTTPayload(self) -> List[Dict[str, Any]]:
        if not self.mqtt_history:
            return []
            
        return list(self.mqtt_history.values())

    def check_mqtt_broker(self) -> bool:

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                logger.info("✅ MQTT broker connection successful!")
                client.connected_flag = True
            else:
                client.connected_flag = False

        mqtt.Client.connected_flag = False # type: ignore
        self.mqtt.on_connect = on_connect

        try:
            parsed = urlparse(self.config.mqtt_broker_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 1883

            if not self.mqtt.is_connected():
                self.mqtt.connect(host, port)
                self.mqtt.loop_start()

            self.subscribe_topic("#")
            for _ in range(10):
                if self.mqtt.is_connected():
                    return True
                time.sleep(0.5)
            raise RuntimeError("❌ MQTT broker connection failed: Timeout")
        except Exception as e:
            raise RuntimeError(f"❌ MQTT broker connection failed: {e}")

    def check_orion(self) -> Dict[str, Any]:
        url = f"{self.config.orion_url}/version"
        resp = self._request("GET", url, headers=self.config.fiware_headers)
        self._raise_for_status(resp, "Orion version check failed")
        return self._safe_json(resp)

    def check_iota(self) -> Dict[str, Any]:
        url = f"{self.config.iota_url}/iot/about"
        resp = self._request("GET", url, headers=self.config.fiware_headers)
        self._raise_for_status(resp, "IoT Agent check failed")
        return self._safe_json(resp)

    def check_cratedb(self) -> Dict[str, Any]:
        url = f"{self.config.crate_url}"
        resp = self._request("GET", url, headers=self.config.fiware_headers)
        self._raise_for_status(resp, "CrateDB check failed")
        return self._safe_json(resp)

    def check_ql_proxy(self) -> Dict[str, Any]:
        url = f"{self.config.ql_proxy_url}/metrics"
        resp = self._request("GET", url, headers=self.config.fiware_headers)
        self._raise_for_status(resp, "QL-Proxy check failed")
        return self._safe_json(resp)    
    
    def get_admin_metrics(self, reset: bool = False):
        url = f"{self.config.orion_url}/admin/metrics"
        try:
            if reset:
                response = requests.delete(url, timeout=5)
                response.raise_for_status()
                return {}
            else:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            raise Exception(f"Failed to fetch Orion metrics: {e}")

    def get_proxy_metrics(self):
        url = f"{self.config.ql_proxy_url}/metrics"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response
        except Exception as e:
            raise Exception(f"Failed to fetch proxy metrics: {e}")

    def get_orion_stats(self, reset: bool = False):
        url = f"{self.config.orion_url}/statistics"
        
        try:
            if reset:
                response = requests.delete(url, timeout=5)
                response.raise_for_status()
                return {}
            else:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Orion statistics unreachable: {e}")
    
    def execute_crate_query(self, query: str):
        url = f"{self.config.crate_url}/_sql" # Default Port 4200
        payload = {"stmt": query}

        response = requests.post(url, json=payload, timeout=self.config.request_timeout)
        response.raise_for_status()
        
        data = response.json()
        # Convert to an easy-to-handle format (list of dicts)
        columns = data.get("cols", [])
        rows = data.get("rows", [])
        return [dict(zip(columns, row)) for row in rows]
    
    def list_subscriptions(self):
        url = f"{self.config.orion_url}/v2/subscriptions"
        resp = self._request("GET", url, headers=self.config.fiware_headers)
        return self._safe_json(resp)

    def create_subscription(self, payload):
        url = f"{self.config.orion_url}/v2/subscriptions"
        resp = self._request("POST", url, headers=self.config.fiware_json_headers, json=payload)
        return resp

    def delete_subscription(self, sub_id):
        url = f"{self.config.orion_url}/v2/subscriptions/{sub_id}"
        resp = self._request("DELETE", url, headers=self.config.fiware_headers)
        logger.debug("Delete response status: %s", resp.status_code)
        logger.debug("Body: %s", resp.text)
        self._raise_for_status(resp, f"Failed to delete {sub_id}")
        # Explicitly check for success (204 = No Content = successfully deleted)
        if resp.status_code == 204:
            return True
        else:
            logger.error("Deletion failed: %s - %s", resp.status_code, resp.text)
            self._raise_for_status(resp, f"Failed to delete {sub_id}")
            return False

    def update_subscription(self, sub_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update a subscription via PATCH."""
        # PATCH is often preferred in the V2 API, since only changed fields are transmitted
        url = f"{self.config.orion_url}/v2/subscriptions/{sub_id}"
        resp = self._request("PATCH", url, headers=self.config.fiware_json_headers, json=payload)
        self._raise_for_status(resp, f"Failed to update subscription {sub_id}")
        return self._safe_json(resp)

    def list_entities(
        self,
        entity_type: Optional[str] = None,
        id_pattern: Optional[str] = None,
        attrs: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        offset = 0

        # while True:
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "options": "keyValues",
        }
        if entity_type:
            params["type"] = entity_type
        if id_pattern:
            params["idPattern"] = id_pattern
        if attrs:
            params["attrs"] = attrs

        url = f"{self.config.orion_url}/v2/entities"
        resp = self._request("GET", url, headers=self.config.fiware_headers, params=params)
        logger.info("Query: type=%s, idPattern=%s, offset=%d, limit=%d -> Status %d", entity_type, id_pattern, offset, limit, resp.status_code)
        self._raise_for_status(resp, "Failed to list entities")
        batch = self._safe_json(resp)
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected Orion response for entity listing: {batch!r}")
        results.extend(batch)
            # if len(batch) < limit:
            #     break
            # offset += limit
        return results

    def get_entity(self, entity_id: str, entity_type: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.config.orion_url}/v2/entities/{quote(entity_id, safe='')}"
        params: Dict[str, str] = {}
        if entity_type:
            params["type"] = entity_type
        resp = self._request("GET", url, headers=self.config.fiware_headers, params=params)
        self._raise_for_status(resp, f"Failed to get entity {entity_id}")
        return self._safe_json(resp)

    def patch_entity(self, entity_id: str, payload: Dict[str, Any], entity_type: Optional[str] = None) -> None:
        url = f"{self.config.orion_url}/v2/entities/{quote(entity_id, safe='')}/attrs"
        params: Dict[str, str] = {}
        if entity_type:
            params["type"] = entity_type
        resp = self._request(
            "PATCH",
            url,
            headers=self.config.fiware_json_headers,
            params=params,
            json=payload,
        )
        self._raise_for_status(resp, f"Failed to patch entity {entity_id}")

    def delete_entity_attribute(self, entity_id: str, attr_name: str, entity_type: Optional[str] = None) -> None:
        url = f"{self.config.orion_url}/v2/entities/{quote(entity_id, safe='')}/attrs/{quote(attr_name, safe='')}"
        params: Dict[str, str] = {}
        if entity_type:
            params["type"] = entity_type
        resp = self._request("DELETE", url, headers=self.config.fiware_headers, params=params)
        self._raise_for_status(resp, f"Failed to delete attribute {attr_name} from {entity_id}")

    def delete_entity(self, entity_id: str, entity_type: Optional[str] = None) -> None:
        url = f"{self.config.orion_url}/v2/entities/{quote(entity_id, safe='')}"
        params: Dict[str, str] = {}
        if entity_type:
            params["type"] = entity_type
        resp = self._request("DELETE", url, headers=self.config.fiware_headers, params=params)
        self._raise_for_status(resp, f"Failed to delete entity {entity_id}")

    def delete_registration_by_entity(self, entity_id: str, entity_type: Optional[str] = None):
        # 1. Fetch all registrations
        url_list = f"{self.config.orion_url}/v2/registrations"
        resp = self._request("GET", url_list, headers=self.config.fiware_headers)
        registrations = resp.json()

        # 2. Find the matching registration
        for reg in registrations:
            provider_entities = reg.get("dataProvided", {}).get("entities", [])
            for target in provider_entities:
                # Match by ID and optional type
                id_match = (target.get("id") == entity_id or target.get("idPattern") == entity_id)
                type_match = (target.get("type") == entity_type) if entity_type else True
                
                if id_match and type_match:
                    reg_id = reg.get("id")
                    del_url = f"{self.config.orion_url}/v2/registrations/{reg_id}"
                    self._request("DELETE", del_url, headers=self.config.fiware_headers)
                    return True
        return False

    def list_service_groups(self) -> Dict[str, Any]:
        url = f"{self.config.iota_url}/iot/services"
        resp = self._request("GET", url, headers=self.config.fiware_headers)
        self._raise_for_status(resp, "Failed to list service groups")
        return self._safe_json(resp)   

    def create_service_group_json(self, payload_json):
        url = f"{self.config.iota_url}/iot/services"
        
        response = self._request("POST", url, headers=self.config.fiware_json_headers, json=payload_json)
        self._raise_for_status(response, "Failed to create service group")
        return self._safe_json(response)

    def create_service_group(
        self,
        apikey: str,
        entity_type: str,
        entity_name_exp: str,
        attributes: List[Dict[str, Any]],
        static_attributes: Optional[List[Dict[str, Any]]] = None,
        commands: Optional[List[Dict[str, Any]]] = None,
        resource: str = "/iot/json",
        timezone: str = "Europe/Berlin",
    ) -> Dict[str, Any]:
        url = f"{self.config.iota_url}/iot/services"
        payload = {
            "services": [
                {
                    "apikey": apikey,
                    "entity_type": entity_type,
                    "resource": resource,
                    "timezone": timezone,
                    "entityNameExp": entity_name_exp,
                    "attributes": attributes,
                    "static_attributes": static_attributes or [],
                    "commands": commands or [],
                }
            ]
        }
        resp = self._request("POST", url, headers=self.config.fiware_json_headers, json=payload)
        self._raise_for_status(resp, "Failed to create service group")
        return self._safe_json(resp)

    def delete_service_group(self, apikey: str, resource: str = "/iot/json") -> Dict[str, Any]:
        print("delete_service_group...")
        url = f"{self.config.iota_url}/iot/services"
        params = {"apikey": apikey, "resource": resource}
        resp = self._request("DELETE", url, headers=self.config.fiware_headers, params=params)
        self._raise_for_status(resp, f"Failed to delete service group apikey={apikey}")
        return self._safe_json(resp)

    def update_service_group(
        self,
        apikey: str,
        entity_type: str,
        explicitAttrs: bool,
        entity_name_exp: str,
        attributes: List[Dict[str, Any]],
        static_attributes: Optional[List[Dict[str, Any]]] = None,
        commands: Optional[List[Dict[str, Any]]] = None, # commands added
        resource: str = "/iot/json",
        timezone: str = "Europe/Berlin",
    ) -> Dict[str, Any]:
        url = f"{self.config.iota_url}/iot/services"
        params = {"apikey": apikey, "resource": resource}
        
        # For PUT on /iot/services with apikey/resource parameters,
        # the service object itself is often expected directly (without a "services" list)
        payload = {
            "entity_type": entity_type,
            "explicitAttrs": explicitAttrs,
            "timezone": timezone,
            "entityNameExp": entity_name_exp,
            "attributes": attributes,
            "static_attributes": static_attributes or [],
            "commands": commands or [] # send commands separately
        }
        
        resp = self._request("PUT", url, headers=self.config.fiware_json_headers, params=params, json=payload)
        self._raise_for_status(resp, f"Failed to update service group apikey={apikey}")
        return self._safe_json(resp)

    @staticmethod
    def _safe_json(resp: requests.Response) -> Any:
        if not resp.text.strip():
            return {"status": resp.status_code, "body": ""}
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code, "body": resp.text}

    @staticmethod
    def _raise_for_status(resp: requests.Response, context: str) -> None:
        if resp.ok:
            return
        text = resp.text.strip()
        raise RuntimeError(f"{context}. HTTP {resp.status_code}: {text}")


def parse_json_arg(text: str, arg_name: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON for {arg_name}: {exc}") from exc


def build_patch_payload(
    add_schema_version: Optional[str],
    set_source: Optional[str],
    set_attr: List[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}

    if add_schema_version is not None:
        payload["schemaVersion"] = {"type": "Text", "value": add_schema_version}

    if set_source is not None:
        payload["source"] = {"type": "Text", "value": set_source}

    for raw in set_attr:
        # format: name:type:value
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise SystemExit(
                f"Invalid --set-attr '{raw}'. Expected format name:type:value, e.g. batteryVoltage:Number:52.4"
            )
        name, attr_type, value_text = parts
        value: Any = value_text
        if attr_type in {"Number", "Integer", "Float", "Double"}:
            try:
                value = float(value_text)
            except ValueError as exc:
                raise SystemExit(f"Invalid numeric value in --set-attr '{raw}'") from exc
        elif attr_type == "StructuredValue":
            value = parse_json_arg(value_text, f"--set-attr {name}")
        elif attr_type == "Boolean":
            lowered = value_text.lower()
            if lowered not in {"true", "false"}:
                raise SystemExit(f"Invalid boolean value in --set-attr '{raw}'")
            value = lowered == "true"

        payload[name] = {"type": attr_type, "value": value}

    return payload


def filter_entities(
    entities: Iterable[Dict[str, Any]],
    id_prefix: Optional[str] = None,
    contains_attr: Optional[str] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for entity in entities:
        entity_id = entity.get("id", "")
        if id_prefix and not str(entity_id).startswith(id_prefix):
            continue
        if contains_attr and contains_attr not in entity:
            continue
        out.append(entity)
    return out


def print_entities(entities: List[Dict[str, Any]], full: bool = False) -> None:
    if not entities:
        print("No entities found.")
        return
    for entity in entities:
        if full:
            print(json.dumps(entity, indent=2, ensure_ascii=False))
        else:
            attrs = [k for k in entity.keys() if k not in {"id", "type"}]
            print(f"- {entity.get('id')}  type={entity.get('type')}  attrs={','.join(attrs)}")


def cmd_check(client: FiwareClient, _args: argparse.Namespace) -> None:
    print("Checking Orion...")
    print(json.dumps(client.check_orion(), indent=2, ensure_ascii=False))
    print("\nChecking IoT Agent...")
    print(json.dumps(client.check_iota(), indent=2, ensure_ascii=False))


def cmd_list(client: FiwareClient, args: argparse.Namespace) -> None:
    entities = client.list_entities(entity_type=args.type, id_pattern=args.id_pattern, attrs=args.attrs, limit=args.limit)
    entities = filter_entities(entities, id_prefix=args.id_prefix, contains_attr=args.contains_attr)
    print_entities(entities, full=args.full)
    print(f"\nTotal: {len(entities)}")


def cmd_patch(client: FiwareClient, args: argparse.Namespace) -> None:
    payload = build_patch_payload(args.add_schema_version, args.set_source, args.set_attr)
    if not payload:
        raise SystemExit("Nothing to patch. Use --add-schema-version, --set-source, or --set-attr.")

    entities: List[Dict[str, Any]] = []
    if args.entity_id:
        entity = client.get_entity(args.entity_id, entity_type=args.type)
        entities = [entity]
    else:
        entities = client.list_entities(entity_type=args.type, id_pattern=args.id_pattern, limit=args.limit)
        entities = filter_entities(entities, id_prefix=args.id_prefix, contains_attr=args.contains_attr)

    if not entities:
        print("No matching entities for patch.")
        return

    print("Patch payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    for entity in entities:
        entity_id = entity["id"]
        print(f"Patching {entity_id} ...")
        if not args.dry_run:
            client.patch_entity(entity_id, payload, entity_type=args.type)

        for attr_name in args.delete_attr:
            print(f"Deleting attribute {attr_name} from {entity_id} ...")
            if not args.dry_run:
                client.delete_entity_attribute(entity_id, attr_name, entity_type=args.type)

    print(f"Done. Matched entities: {len(entities)}")


def cmd_delete(client: FiwareClient, args: argparse.Namespace) -> None:
    entities: List[Dict[str, Any]] = []
    if args.entity_id:
        entity = client.get_entity(args.entity_id, entity_type=args.type)
        entities = [entity]
    else:
        entities = client.list_entities(entity_type=args.type, id_pattern=args.id_pattern, limit=args.limit)
        entities = filter_entities(entities, id_prefix=args.id_prefix, contains_attr=args.contains_attr)

    if not entities:
        print("No matching entities for delete.")
        return

    for entity in entities:
        entity_id = entity["id"]
        print(f"Deleting {entity_id} ...")
        if not args.dry_run:
            client.delete_entity(entity_id, entity_type=args.type)

    print(f"Done. Deleted entities: {len(entities)}")


def cmd_validate(client: FiwareClient, args: argparse.Namespace) -> None:
    entities = client.list_entities(entity_type=args.type, id_pattern=args.id_pattern, limit=args.limit)
    entities = filter_entities(entities, id_prefix=args.id_prefix)

    if not entities:
        print("No matching entities for validation.")
        return

    expected_attrs = set(args.expected_attr)
    missing_total = 0

    for entity in entities:
        keys = set(entity.keys()) - {"id", "type"}
        missing = sorted(expected_attrs - keys)
        extra = sorted(keys - expected_attrs) if args.show_extra else []
        status = "OK" if not missing else "MISSING"
        print(f"{status}  {entity.get('id')}")
        if missing:
            missing_total += 1
            print(f"  missing: {', '.join(missing)}")
        if extra:
            print(f"  extra:   {', '.join(extra)}")

    print(f"\nValidated: {len(entities)}  with missing attrs: {missing_total}")


def cmd_create_service_group(client: FiwareClient, args: argparse.Namespace) -> None:
    attributes = parse_json_arg(args.attributes, "--attributes")
    if not isinstance(attributes, list):
        raise SystemExit("--attributes must be a JSON array")

    static_attributes = parse_json_arg(args.static_attributes, "--static-attributes") if args.static_attributes else []
    if static_attributes and not isinstance(static_attributes, list):
        raise SystemExit("--static-attributes must be a JSON array")

    payload = {
        "services": [
            {
                "apikey": args.apikey,
                "entity_type": args.entity_type,
                "resource": args.resource,
                "timezone": args.timezone,
                "entityNameExp": args.entity_name_exp,
                "attributes": attributes,
                "static_attributes": static_attributes,
            }
        ]
    }

    if args.dry_run:
        print("Dry run. Would create service group with payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    result = client.create_service_group(
        apikey=args.apikey,
        entity_type=args.entity_type,
        entity_name_exp=args.entity_name_exp,
        attributes=attributes,
        static_attributes=static_attributes,
        resource=args.resource,
        timezone=args.timezone,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_delete_service_group(client: FiwareClient, args: argparse.Namespace) -> None:
    if args.dry_run:
        print("Dry run. Would delete service group:")
        print(json.dumps({"apikey": args.apikey, "resource": args.resource}, indent=2, ensure_ascii=False))
        return

    result = client.delete_service_group(apikey=args.apikey, resource=args.resource)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_update_service_group(client: FiwareClient, args: argparse.Namespace) -> None:
    attributes = parse_json_arg(args.attributes, "--attributes")
    if not isinstance(attributes, list):
        raise SystemExit("--attributes must be a JSON array")

    static_attributes = parse_json_arg(args.static_attributes, "--static-attributes") if args.static_attributes else []
    if static_attributes and not isinstance(static_attributes, list):
        raise SystemExit("--static-attributes must be a JSON array")

    payload = {
        "services": [
            {
                "apikey": args.apikey,
                "entity_type": args.entity_type,
                "resource": args.resource,
                "timezone": args.timezone,
                "entityNameExp": args.entity_name_exp,
                "attributes": attributes,
                "static_attributes": static_attributes,
            }
        ]
    }

    if args.dry_run:
        print("Dry run. Would update service group with payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    result = client.update_service_group(
        apikey=args.apikey,
        entity_type=args.entity_type,
        explicitAttrs=True,
        entity_name_exp=args.entity_name_exp,
        attributes=attributes,
        static_attributes=static_attributes,
        resource=args.resource,
        timezone=args.timezone,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_clean_migration(client: FiwareClient, args: argparse.Namespace) -> None:
    attributes = parse_json_arg(args.attributes, "--attributes")
    if not isinstance(attributes, list):
        raise SystemExit("--attributes must be a JSON array")

    static_attributes = parse_json_arg(args.static_attributes, "--static-attributes") if args.static_attributes else []
    if static_attributes and not isinstance(static_attributes, list):
        raise SystemExit("--static-attributes must be a JSON array")

    entities = client.list_entities(entity_type=args.old_entity_type, id_pattern=args.id_pattern, limit=args.limit)
    entities = filter_entities(entities, id_prefix=args.old_id_prefix, contains_attr=args.contains_attr)

    print("Clean migration plan:")
    print(f"- old service group apikey: {args.old_apikey}")
    print(f"- new service group apikey: {args.new_apikey}")
    print(f"- old entity type: {args.old_entity_type}")
    print(f"- new entity type: {args.new_entity_type}")
    print(f"- matched old entities: {len(entities)}")

    for entity in entities:
        print(f"  delete entity: {entity['id']}")

    payload = {
        "services": [
            {
                "apikey": args.new_apikey,
                "entity_type": args.new_entity_type,
                "resource": args.resource,
                "timezone": args.timezone,
                "entityNameExp": args.new_entity_name_exp,
                "attributes": attributes,
                "static_attributes": static_attributes,
            }
        ]
    }
    print("New service group payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("Dry run only. No changes applied.")
        return

    if args.create_new_service_group:
        print(f"Creating new service group {args.new_apikey} ...")
        client.create_service_group(
            apikey=args.new_apikey,
            entity_type=args.new_entity_type,
            entity_name_exp=args.new_entity_name_exp,
            attributes=attributes,
            static_attributes=static_attributes,
            resource=args.resource,
            timezone=args.timezone,
        )

    if args.delete_old_entities:
        for entity in entities:
            entity_id = entity["id"]
            print(f"Deleting old entity {entity_id} ...")
            client.delete_entity(entity_id, entity_type=args.old_entity_type)

    if args.delete_old_service_group:
        print(f"Deleting old service group {args.old_apikey} ...")
        client.delete_service_group(apikey=args.old_apikey, resource=args.resource)

    print("Clean migration finished.")
    print("Next step: switch publishers/devices to the new API key so new entities can be recreated.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FIWARE migration tool for Orion + IoT Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check Orion and IoT Agent availability")

    p_list = sub.add_parser("list", help="List Orion entities")
    p_list.add_argument("--type", help="Filter by entity type")
    p_list.add_argument("--id-pattern", help="Orion idPattern filter, e.g. .*BatteryStatus.*")
    p_list.add_argument("--id-prefix", help="Local filter by entity id prefix")
    p_list.add_argument("--attrs", help="Comma-separated Orion attrs projection")
    p_list.add_argument("--contains-attr", help="Local filter: entity must contain this attribute")
    p_list.add_argument("--limit", type=int, default=100, help="Page size for Orion listing")
    p_list.add_argument("--full", action="store_true", help="Print full JSON entities")

    p_patch = sub.add_parser("patch", help="Patch Orion entities")
    p_patch.add_argument("--entity-id", help="Patch exactly one entity id")
    p_patch.add_argument("--type", help="Filter/type hint for Orion")
    p_patch.add_argument("--id-pattern", help="Orion idPattern filter")
    p_patch.add_argument("--id-prefix", help="Local filter by entity id prefix")
    p_patch.add_argument("--contains-attr", help="Local filter: entity must contain this attribute")
    p_patch.add_argument("--limit", type=int, default=100, help="Page size for Orion listing")
    p_patch.add_argument("--add-schema-version", help="Add or update schemaVersion Text attribute")
    p_patch.add_argument("--set-source", help="Add or update source Text attribute")
    p_patch.add_argument(
        "--set-attr",
        action="append",
        default=[],
        help="Generic attribute in format name:type:value. Repeatable.",
    )
    p_patch.add_argument(
        "--delete-attr",
        action="append",
        default=[],
        help="Delete attribute after patch. Repeatable.",
    )
    p_patch.add_argument("--dry-run", action="store_true", help="Show actions without applying them")

    p_delete = sub.add_parser("delete", help="Delete Orion entities")
    p_delete.add_argument("--entity-id", help="Delete exactly one entity id")
    p_delete.add_argument("--type", help="Filter/type hint for Orion")
    p_delete.add_argument("--id-pattern", help="Orion idPattern filter")
    p_delete.add_argument("--id-prefix", help="Local filter by entity id prefix")
    p_delete.add_argument("--contains-attr", help="Local filter: entity must contain this attribute")
    p_delete.add_argument("--limit", type=int, default=100, help="Page size for Orion listing")
    p_delete.add_argument("--dry-run", action="store_true", help="Show actions without applying them")

    p_validate = sub.add_parser("validate", help="Validate entities against expected attribute names")
    p_validate.add_argument("--type", help="Filter by entity type")
    p_validate.add_argument("--id-pattern", help="Orion idPattern filter")
    p_validate.add_argument("--id-prefix", help="Local filter by entity id prefix")
    p_validate.add_argument("--limit", type=int, default=100, help="Page size for Orion listing")
    p_validate.add_argument(
        "--expected-attr",
        action="append",
        default=[],
        required=True,
        help="Expected attribute name. Repeatable.",
    )
    p_validate.add_argument("--show-extra", action="store_true", help="Show extra attrs not in expected set")

    p_service = sub.add_parser("create-service-group", help="Create a new IoT Agent service group")
    p_service.add_argument("--apikey", required=True, help="New IoT Agent apikey")
    p_service.add_argument("--entity-type", required=True, help="New entity type")
    p_service.add_argument("--entity-name-exp", required=True, help="IoT Agent entityNameExp")
    p_service.add_argument("--attributes", required=True, help="JSON array of IoT Agent attributes")
    p_service.add_argument("--static-attributes", help="JSON array of IoT Agent static_attributes")
    p_service.add_argument("--resource", default="/iot/json", help="IoT Agent resource")
    p_service.add_argument("--timezone", default="Europe/Berlin", help="IoT Agent timezone")
    p_service.add_argument("--dry-run", action="store_true", help="Show payload without creating")

    p_service_delete = sub.add_parser("delete-service-group", help="Delete an IoT Agent service group")
    p_service_delete.add_argument("--apikey", required=True, help="IoT Agent apikey to delete")
    p_service_delete.add_argument("--resource", default="/iot/json", help="IoT Agent resource")
    p_service_delete.add_argument("--dry-run", action="store_true", help="Show action without deleting")

    p_service_update = sub.add_parser("update-service-group", help="Update an existing IoT Agent service group")
    p_service_update.add_argument("--apikey", required=True, help="Existing IoT Agent apikey")
    p_service_update.add_argument("--entity-type", required=True, help="Updated entity type")
    p_service_update.add_argument("--entity-name-exp", required=True, help="Updated IoT Agent entityNameExp")
    p_service_update.add_argument("--attributes", required=True, help="JSON array of IoT Agent attributes")
    p_service_update.add_argument("--static-attributes", help="JSON array of IoT Agent static_attributes")
    p_service_update.add_argument("--resource", default="/iot/json", help="IoT Agent resource")
    p_service_update.add_argument("--timezone", default="Europe/Berlin", help="IoT Agent timezone")
    p_service_update.add_argument("--dry-run", action="store_true", help="Show payload without updating")

    p_clean = sub.add_parser("clean-migration", help="Run clean migration: create new service group, delete old entities, delete old service group")
    p_clean.add_argument("--old-apikey", required=True, help="Old IoT Agent apikey to retire")
    p_clean.add_argument("--new-apikey", required=True, help="New IoT Agent apikey to create")
    p_clean.add_argument("--old-entity-type", required=True, help="Old Orion entity type to delete")
    p_clean.add_argument("--new-entity-type", required=True, help="New entity type for the new service group")
    p_clean.add_argument("--new-entity-name-exp", required=True, help="entityNameExp for the new service group")
    p_clean.add_argument("--old-id-prefix", help="Local filter for old entity ids")
    p_clean.add_argument("--id-pattern", help="Orion idPattern filter for old entities")
    p_clean.add_argument("--contains-attr", help="Local filter: old entity must contain this attribute")
    p_clean.add_argument("--attributes", required=True, help="JSON array of IoT Agent attributes for new service group")
    p_clean.add_argument("--static-attributes", help="JSON array of IoT Agent static_attributes for new service group")
    p_clean.add_argument("--resource", default="/iot/json", help="IoT Agent resource")
    p_clean.add_argument("--timezone", default="Europe/Berlin", help="IoT Agent timezone")
    p_clean.add_argument("--limit", type=int, default=100, help="Page size for Orion listing")
    p_clean.add_argument("--create-new-service-group", action="store_true", help="Actually create the new service group")
    p_clean.add_argument("--delete-old-entities", action="store_true", help="Actually delete matching old entities")
    p_clean.add_argument("--delete-old-service-group", action="store_true", help="Actually delete the old service group")
    p_clean.add_argument("--dry-run", action="store_true", help="Show full migration plan without applying changes")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = Config()
    client = FiwareClient(cfg)

    try:
        if args.command == "check":
            cmd_check(client, args)
        elif args.command == "list":
            cmd_list(client, args)
        elif args.command == "patch":
            cmd_patch(client, args)
        elif args.command == "delete":
            cmd_delete(client, args)
        elif args.command == "validate":
            cmd_validate(client, args)
        elif args.command == "create-service-group":
            cmd_create_service_group(client, args)
        elif args.command == "delete-service-group":
            cmd_delete_service_group(client, args)
        elif args.command == "update-service-group":
            cmd_update_service_group(client, args)
        elif args.command == "clean-migration":
            cmd_clean_migration(client, args)
        else:
            parser.error(f"Unknown command: {args.command}")
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
