# Lightweight Python base
FROM python:3.11-slim

# Python runtime optimizations
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    UVICORN_LOOP=uvloop \
    UVICORN_HTTP=httptools

WORKDIR /app

# Install build deps only temporarily
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better cache)
COPY requirements.txt .

# Install high-performance runtime deps
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir uvicorn[standard] hypercorn \
    && pip install --no-cache-dir -r requirements.txt

# Remove build tools (smaller + cleaner)
RUN apt-get purge -y gcc build-essential \
    && apt-get autoremove -y

# Copy app
COPY . .

EXPOSE 8000

# Keep your runner
CMD ["python", "app_runner.py"]