FROM python:3.11-slim

# Installer Tesseract + Arabic + Poppler (PDF→image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-ara \
    poppler-utils \
    libmagic1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    flask \
    gunicorn \
    pytesseract \
    pillow \
    pdf2image \
    werkzeug

COPY . .

EXPOSE 5006

CMD ["gunicorn", "--bind", "0.0.0.0:5006", "--workers", "2", "--timeout", "120", "app:app"]
