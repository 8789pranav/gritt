# Base Python image
FROM python:3.11-slim

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# App Runner routes to the port configured on the service and also sets PORT.
# Honour it, and fall back to 8000 so a plain `docker run` still works.
ENV PORT=8000
EXPOSE 8000

# The speech lab spends money per call and takes no auth. It stays off unless
# SPEECH_LAB_ENABLED is set, and it must not be set in a deployed environment.
ENV SPEECH_LAB_ENABLED=""

# Python writes .pyc and buffers stdout by default; neither helps in a
# container, and unbuffered logs are what App Runner shows you.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
