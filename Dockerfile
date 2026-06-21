FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (openssh-client for ssh tunnels, and potentially curl/procps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
