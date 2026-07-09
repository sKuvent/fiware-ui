# FIWARE UI

A Streamlit-based administration dashboard for operating and monitoring a FIWARE stack, including Orion Context Broker, IoT Agent, and CrateDB

## Features

- System architecture overview
- Entity search, inspection, editing, and deletion
- Service group management
- Orion subscription management
- CrateDB query and preview tools
- Orion and QuantumLeap Proxy metrics
- Service migration tools
- MQTT broker monitoring
- Docker and Portainer integration
- Authenticated dashboard access

## Tech Stack

- Python 3.12+
- Streamlit
- streamlit-authenticator
- requests
- pandas
- matplotlib
- graphviz
- paho-mqtt
- uv for Python and dependency management

## Project Structure

```text
fiware-ui/
├── fiware_ui.py
├── fiware_tool.py
├── pyproject.toml
├── uv.lock
├── .python-version
├── Dockerfile
├── .env.example
├── fiware_logo.png
└── ui/
    ├── tab_architecture.py
    ├── tab_entities.py
    ├── tab_service_groups.py
    ├── tab_subscriptions.py
    ├── tab_migration.py
    ├── tab_cratedb.py
    ├── tab_metrics.py
    ├── tab_portainer.py
    └── tab_info.py
```

## Requirements

- `uv`
- Python 3.12 or newer
- Reachable FIWARE services
- Valid dashboard authentication secrets
- Graphviz system package, depending on the operating system
- Docker and Docker Compose for container-based deployment

Python can be installed and managed directly through `uv`.

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd fiware-ui
```

Install the required Python version:

```bash
uv python install 3.12
```

Synchronize the project environment:

```bash
uv sync
```

This creates a local `.venv` environment and installs the dependency versions defined in `uv.lock`.

## Environment Variables

Copy the example configuration:

```bash
cp .env.example .env
```

Required authentication variables:

```env
DASHBOARD_ADMIN_PASSWORD_HASH=<bcrypt-password-hash>
DASHBOARD_COOKIE_KEY=<long-random-secret>
DASHBOARD_ADMIN_EMAIL=admin@example.com
```

Optional service configuration:

```env
ORION_URL=http://orion:1026
IOTA_URL=http://iot-agent:4041
CRATE_URL=http://crate:4200
MQTT_BROKER_URL=mqtt://mqtt:1883
QL_PROXY_URL=http://quantumleap-proxy:4300
PORTAINER_URL=http://portainer:9000

FIWARE_SERVICE=openiot
FIWARE_SERVICEPATH=/
REQUEST_TIMEOUT=10
```

Load the environment variables on Linux or macOS:

```bash
set -a
source .env
set +a
```

## Running Locally

Start the Streamlit application through `uv`:

```bash
uv run streamlit run fiware_ui.py \
  --server.port=8501 \
  --server.address=0.0.0.0
```

Open the dashboard at:

```text
http://localhost:8501
```

Using `uv run` ensures that the command is executed inside the project environment with the locked dependency versions.

## Dependency Management

Add a production dependency:

```bash
uv add <package>
```

Add a development dependency:

```bash
uv add --dev <package>
```

Remove a dependency:

```bash
uv remove <package>
```

Synchronize the environment after pulling changes:

```bash
uv sync
```

Update all dependencies:

```bash
uv lock --upgrade
uv sync
```

Check that `pyproject.toml` and `uv.lock` are synchronized without modifying the lockfile:

```bash
uv lock --check
```

The generated `uv.lock` file must be committed to the repository. The `.venv` directory must not be committed.

## Docker

Build the container:

```bash
docker build -t fiware-ui .
```

Run the container:

```bash
docker run \
  --env-file .env \
  --publish 8501:8501 \
  fiware-ui
```

Alternatively, start the dashboard through Docker Compose:

```bash
docker compose up -d fiware-ui --build
```

Check the container logs:

```bash
docker compose logs -f fiware-ui
```

## Security Notes

- Never commit `.env` or real credentials.
- Never commit `DASHBOARD_ADMIN_PASSWORD_HASH` or `DASHBOARD_COOKIE_KEY`.
- Use environment variables or a secret manager for credentials.
- Restrict network access to the dashboard in production.
- Place the dashboard behind an HTTPS reverse proxy.
- Keep Streamlit XSRF protection enabled.
- Use a restricted CrateDB user where possible.
- Review destructive operations such as entity deletion, migration, and arbitrary SQL execution before enabling production access.

## Development Workflow

Create a feature branch:

```bash
git checkout -b feature/<feature-name>
```

Install the locked environment:

```bash
uv sync --locked
```

Run the application:

```bash
uv run streamlit run fiware_ui.py
```

Before committing dependency changes, verify that the lockfile is current:

```bash
uv lock --check
```

Commit both files when dependencies change:

```text
pyproject.toml
uv.lock
```

## Contributing

1. Create a focused feature or bug-fix branch.
2. Keep changes small and reviewable.
3. Test changes against a FIWARE environment.
4. Update the documentation when configuration or dependencies change.
5. Include screenshots for user-interface changes.
6. Open a pull request with a concise description.

## License

This project is licensed under the Apache License 2.0. See `LICENSE` for details.