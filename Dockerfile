FROM python:3.12-slim
ARG APP_VERSION=1.2.1
LABEL org.opencontainers.image.title="Social Cockpit" org.opencontainers.image.version=$APP_VERSION org.opencontainers.image.source="https://github.com/xyciasav/social-cockpit"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates ./templates
COPY static ./static
RUN mkdir -p /app/data && chown -R nobody:nogroup /app
USER nobody
EXPOSE 3000
CMD ["gunicorn","--bind","0.0.0.0:3000","--workers","2","--timeout","330","app:app"]
