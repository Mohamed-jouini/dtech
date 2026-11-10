FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY app.py .
COPY audit_client.py .
COPY templates/ templates/
ENV DB_PATH=/data/archive.db
ENV PORT=5004
EXPOSE 5004
VOLUME /data
CMD ["python", "app.py"]
