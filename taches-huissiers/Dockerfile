FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY app.py .
COPY templates/ templates/
ENV DB_PATH=/data/taches.db
ENV PORT=5003
EXPOSE 5003
VOLUME /data
CMD ["python", "app.py"]
