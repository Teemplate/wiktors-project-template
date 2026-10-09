# Single stage: the backend has no build step. Pinned to the same Python the CI
# workflow uses — a mismatch there means CI passes and the container fails.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so an application-code edit does not invalidate the
# (slow) pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Everything .dockerignore lets through: app/, and with the postgres block
# alembic.ini + migrations/ — the deploy runs `alembic upgrade head` in a
# one-shot container built from this same image, before the app starts. One
# COPY rather than a line per path, because which paths exist depends on the
# project's blocks (docs/BLOCKS.md).
COPY . .

# One image, several services: api, worker and migrate each set their own
# `command:` in their compose fragment. This default is the api's.
# block:api
EXPOSE 8000
# The api's liveness, baked into the image so dev and e2e containers report it
# too, not only the deploy compose file. python, not curl: the slim image has no
# curl. The worker and the one-shot migrate share this image and override it in
# their compose fragments (a heartbeat check; `disable: true`).
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"]
# No --reload in production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# /block
