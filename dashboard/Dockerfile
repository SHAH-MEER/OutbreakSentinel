# Build context must be the repo root (needs dashboard/ and .streamlit/):
#
#   docker build -f dashboard/Dockerfile -t outbreak-sentinel-dashboard .
#
# Runs as a long-lived server on App Runner (infra/app_runner.tf) — a
# different deployment shape from the request/response Lambdas in
# infra/docker/Dockerfile, so it gets its own image.
FROM python:3.12-slim

WORKDIR /app

COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard/ ./dashboard/
COPY .streamlit/ ./.streamlit/

EXPOSE 8501
ENV API_BASE_URL=""
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
