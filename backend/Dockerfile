# --- build stage: compile/install wheels into an isolated prefix ---
FROM python:3.12-slim AS build
WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# --- runtime stage: just the interpreter, installed packages and app code ---
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
COPY --from=build /install /usr/local
COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data && chown appuser:appuser /data
# No VOLUME instruction: Railway rejects it. /data is mounted by the platform
# (Railway volume) or by docker-compose (named volume `appdata`).
EXPOSE 8000
# entrypoint.sh fixes /data ownership, then runs the app as the non-root appuser.
ENTRYPOINT ["/entrypoint.sh"]
# PORT is honoured so hosting platforms can inject their own.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
