# Builder stage
FROM python:3.13-slim AS builder

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies and apply security updates
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    ca-certificates \
    && apt-get purge -y --auto-remove imagemagick libmagickcore-6.q16-6 libmagickwand-6.q16-6 libxslt1.1 || true \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory for better caching
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.13-slim AS production

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime dependencies only and apply security updates
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
    curl \
    && apt-get purge -y --auto-remove imagemagick libmagickcore-6.q16-6 libmagickwand-6.q16-6 libxslt1.1 || true \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create non-root user with specific UID for security
RUN groupadd --gid 1000 carma-ai && \
    useradd --create-home --shell /bin/bash --uid 1000 --gid 1000 carma-ai

# Set working directory
WORKDIR /home/carma-ai

# Copy application code with proper ownership
COPY --chown=carma-ai:carma-ai app/ ./app/
COPY --chown=carma-ai:carma-ai main.py ./

# Switch to non-root user
USER carma-ai

# Expose port
EXPOSE 8000

# Production command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]