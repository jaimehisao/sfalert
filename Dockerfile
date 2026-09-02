FROM python:3.12-slim-bookworm

WORKDIR /app

COPY sfalert ./sfalert
COPY web ./web

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin sfalert \
    && mkdir -p /app/data \
    && chown -R sfalert:sfalert /app

USER sfalert
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8765
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/meta', timeout=4)"

CMD ["python", "-m", "sfalert", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]
