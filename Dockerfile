FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so code changes don't invalidate the layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY weatherstation.py .

EXPOSE 80

CMD ["python", "weatherstation.py"]
