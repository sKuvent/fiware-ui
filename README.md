# FIWARE UI

Streamlit dashboard for operating and monitoring a FIWARE stack (Orion, IoT Agent, CrateDB, MQTT, QuantumLeap Proxy) in a generic environment.

## Features

- System architecture overview
- Entity search, inspection, editing, and deletion
- Service group and subscription management
- CrateDB query and preview tools
- Orion and QL-Proxy metrics views
- Sidebar health checks for core services

## Tech Stack

- Python 3.10+
- Streamlit
- streamlit-authenticator
- requests
- pandas
- matplotlib
- graphviz
- paho-mqtt

## Project Structure

```
fiware-ui/
├── fiware_ui.py
├── fiware_tool.py
├── requirements.txt
├── ui/
└── utils/
```

## Requirements

- Python 3.14 or newer
- Reachable FIWARE services (Orion, IoT Agent, CrateDB, MQTT, QL-Proxy)
- Valid dashboard auth secrets via environment variables

## Environment Variables

Authentication (required):

- `DASHBOARD_ADMIN_PASSWORD_HASH`
- `DASHBOARD_COOKIE_KEY`
- `DASHBOARD_ADMIN_EMAIL`

Service endpoints (optional, have defaults in code):

- `ORION_URL`
- `IOTA_URL`
- `CRATE_URL`
- `MQTT_BROKER_URL`
- `QL_PROXY_URL`
- `PORTAINER_URL`
- `FIWARE_SERVICE`
- `FIWARE_SERVICEPATH`
- `REQUEST_TIMEOUT`

You can start from `.env.example` and adapt the values to your environment.

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DASHBOARD_ADMIN_PASSWORD_HASH='<bcrypt-hash>'
export DASHBOARD_COOKIE_KEY='<long-random-secret>'
export DASHBOARD_ADMIN_EMAIL='admin@example.com'

# optional endpoint overrides
# cp .env.example .env

streamlit run fiware_ui.py --server.port=8501 --server.address=0.0.0.0
```

Open: `http://localhost:8501`

## Docker

Build and run this UI container from the platform repository using Docker Compose, for example:

```bash
docker compose up -d fiware-ui --build
```

## Security Notes

- Never commit real values for `DASHBOARD_ADMIN_PASSWORD_HASH` or `DASHBOARD_COOKIE_KEY`.
- Use environment variables or a secret manager for all credentials.
- Keep project-specific IPs, domains, and broker URLs out of source code; use `.env` or container environment variables instead.
- Review exposed ports and network access in your compose setup before production usage.

## Contributing

1. Create a feature branch.
2. Keep changes focused and test manually against your FIWARE environment.
3. Open a pull request with a short change summary and screenshots (if UI-related).

## License

This project is licensed under the Apache License 2.0. See `LICENSE` for details.
