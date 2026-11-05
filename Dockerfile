# ---------- build stage ----------
FROM python:3.12-slim AS build
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install ".[api]"

# ---------- runtime stage ----------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="aqi-forecaster" \
      org.opencontainers.image.description="Real-time AQI forecasting API"
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home appuser
# Lets the same image run unchanged on AWS Lambda (ignored everywhere else)
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
WORKDIR /app
COPY --from=build /install /usr/local
COPY src ./src
COPY api ./api
# Model is baked in when present (CI copies it in); otherwise it is downloaded from MODEL_URL at startup
COPY models ./models
RUN chown -R appuser /app
USER appuser
ENV PYTHONPATH=/app/src:/app PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:${PORT}/health || exit 1
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
