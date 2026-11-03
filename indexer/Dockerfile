FROM python:3.12.11-slim-bookworm AS builder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm
# OCR needs system packages, not only pip ones (handout 3.1)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng poppler-utils \
 && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
COPY --from=builder /opt/venv /opt/venv
WORKDIR /srv
COPY pipeline ./pipeline
USER 10001
CMD ["python", "-m", "pipeline.run"]
