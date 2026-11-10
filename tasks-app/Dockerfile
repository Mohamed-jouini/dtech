FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn requests werkzeug docker
COPY app.py .
COPY templates/ templates/
EXPOSE 5008
CMD ["gunicorn", "--bind", "0.0.0.0:5008", "--workers", "1", "--timeout", "60", "app:app"]
