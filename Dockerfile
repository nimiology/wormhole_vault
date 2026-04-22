FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Use Iranian mirrors for apt
RUN sed -i 's|deb.debian.org|mirror.arvancloud.ir|g' /etc/apt/sources.list.d/* /etc/apt/sources.list 2>/dev/null || true && \
    sed -i 's|security.debian.org|mirror.arvancloud.ir|g' /etc/apt/sources.list.d/* /etc/apt/sources.list 2>/dev/null || true

# Install system deps: SSH client + pg_dump (version 15 to match production)
RUN apt-get update -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends \
       openssh-client \
       gzip \
       curl \
       gnupg2 \
    && rm -rf /var/lib/apt/lists/*

# Add PostgreSQL 15 apt repo and install pg_dump
RUN curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends postgresql-client-15 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Prepare directories
RUN mkdir -p /app/backups /app/ssh_keys /app/staticfiles

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
