# Dockerfile — SportZone (Python 3.12 + Gunicorn)
FROM python:3.12-slim

# --- Biến môi trường hệ thống ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- Phụ thuộc OS (cần cho PyMySQL cryptography) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Cài Python packages ---
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# --- Copy toàn bộ source ---
COPY . .

# --- Tạo thư mục log ---
RUN mkdir -p /app/logs

# --- User không phải root (bảo mật) ---
RUN addgroup --system sportzone && adduser --system --ingroup sportzone sportzone
RUN chown -R sportzone:sportzone /app
USER sportzone

# --- Port Gunicorn ---
EXPOSE 8000

# --- Healthcheck ---
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# --- Entrypoint ---
# Chạy Flask-Migrate migrate (an toàn khi DB đã up-to-date), rồi seed, rồi Gunicorn
CMD ["sh", "-c", \
     "flask db upgrade && python scripts/seed_dev.py && \
      gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 \
               --access-logfile - --error-logfile - wsgi:app"]
