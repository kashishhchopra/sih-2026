FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for scientific wheels are covered by manylinux wheels; keep image slim.
# tesseract-ocr is the one real (non-Python) dependency: it powers itinerary
# photo/scan OCR (services/itinerary_extract.py). If this package is ever
# dropped from the image, that feature degrades gracefully to its
# "OCR unavailable" message rather than breaking the build or the app.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Train ML models at build time so the image ships ready-to-serve artifacts.
RUN python -m app.ml.train_all

# Non-root runtime user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Single worker: the in-memory rate limiter and WebSocket manager are per-process.
# For multi-worker scaling, back them with Redis (see README).
ENTRYPOINT ["./entrypoint.sh"]
