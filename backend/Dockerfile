# backend/Dockerfile
# Container for FastAPI + OpenCV validator

FROM python:3.11-slim

# Prevent python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps needed by opencv-python on Debian slim
# - libgl1 / libglib2.0-0 are common requirements for cv2 import
# - ffmpeg is optional but helpful for more video codec support
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps first (better layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the backend code
COPY . /app

# Ensure storage dirs exist inside container (optional; app also creates them)
RUN mkdir -p /app/storage/uploads /app/storage/metadata

EXPOSE 8000

# Production-ish command.
# (This is fine for a single-container setup behind a reverse proxy later.)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
