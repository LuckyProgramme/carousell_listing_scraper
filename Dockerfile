FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEAL_FINDER_LOG_DIR=/tmp/deal-finder \
    PORT=8080

WORKDIR /app

RUN addgroup --system dealfinder \
    && adduser --system --ingroup dealfinder --home /app dealfinder

COPY pyproject.toml README.md ./
COPY src ./src
COPY prompts ./prompts

RUN python -m pip install --no-cache-dir .

USER dealfinder
EXPOSE 8080

# Deploy this image as the service with the default command. Configure the Cloud
# Run Job to override the command with: python -m deal_finder.scan_job
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--access-logfile", "-", "deal_finder.dispatcher:create_app()"]
