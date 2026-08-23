# Single stage: the backend has no build step. Pinned to the same Python the CI
# workflow uses — a mismatch there means CI passes and the container fails.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so an application-code edit does not invalidate the
# (slow) pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Migrations ship in the image: the deploy runs `alembic upgrade head` in a
# one-shot container built from this same image, before the app starts.
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000

# No --reload in production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
