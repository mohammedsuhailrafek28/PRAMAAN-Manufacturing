# Manufacturing PRAMAAN: one container. Next.js is the only public listener; the Python manufacturing backend binds 127.0.0.1:4420 inside it.
# Synthetic demonstration data. The checkpoint is a self-exported demo reference, not independent custody or external anchoring.

FROM node:24-bookworm-slim AS web
WORKDIR /app/stitch-nextjs
ENV NEXT_TELEMETRY_DISABLED=1
COPY stitch-nextjs/package.json stitch-nextjs/package-lock.json ./
# prebuild needs the dev dependencies (Tailwind builds the landing CSS; three is vendored from node_modules)
RUN npm ci --include=dev
COPY stitch-nextjs/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NEXT_TELEMETRY_DISABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY integration/requirements.lock integration/requirements.lock
RUN pip install --no-cache-dir -r integration/requirements.lock
RUN useradd --uid 10001 --create-home app
COPY app.py ./
COPY application/ application/
COPY integration/ integration/
COPY recall-engine/ recall-engine/
COPY deploy/ deploy/
COPY --from=web /app/stitch-nextjs /app/stitch-nextjs
RUN chmod +x deploy/start.sh && chown -R app:app /app /home/app
USER app
# Render Free gives ~0.1 vCPU: one verification takes 1.2-2.7 s there (about 0.2 s on a laptop), so the 1.25 s default budget fails closed (503 VERIFYING) on its own. The budget only bounds how long a verification may run.
ENV PORT=3000 PRAMAAN_API_URL=http://127.0.0.1:4420 PRAMAAN_VERIFY_BUDGET_SECONDS=8
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 CMD ["python", "-c", "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/snapshot' % os.environ.get('PORT','3000'),timeout=8)"]
CMD ["/app/deploy/start.sh"]
