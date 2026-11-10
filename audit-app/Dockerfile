FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY . .
EXPOSE 5010
CMD ["gunicorn", "--bind", "0.0.0.0:5010", "--workers", "2", "--timeout", "60", "app:app"]
