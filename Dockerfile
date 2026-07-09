# Lightweight Python image as base
FROM python:3.14-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy all code
COPY . .

# Expose the Streamlit port
EXPOSE 8501

# Healthcheck to see if the dashboard is running
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# Start command
ENTRYPOINT ["streamlit", "run", "fiware_ui.py", "--server.port=8501", "--server.address=0.0.0.0"]