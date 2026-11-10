FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask werkzeug gunicorn
COPY app.py .
COPY templates/ templates/
EXPOSE 5011
CMD ["gunicorn", "--bind", "0.0.0.0:5011", "--workers", "1", "--timeout", "120", "app:app"]
