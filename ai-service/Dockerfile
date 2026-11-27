FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service
COPY pyproject.toml ./
COPY app/ ./app/
RUN python -m pip install --no-cache-dir . \
    && groupadd --gid 10001 ai-service \
    && useradd --uid 10001 --gid 10001 --no-create-home ai-service

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
