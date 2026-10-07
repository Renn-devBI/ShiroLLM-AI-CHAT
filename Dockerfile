# Dockerfile untuk SHIRO v5 LLMA

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    llama-cpp-python==0.2.90 --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories yang dibutuhkan
RUN mkdir -p model profile venv

# Expose port yang digunakan Flask
EXPOSE 7474

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:7474 || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Run web.py
CMD ["python", "web.py"]
