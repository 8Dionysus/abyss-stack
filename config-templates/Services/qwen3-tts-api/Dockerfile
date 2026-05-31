FROM docker.io/library/python:3.14-slim@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# audio deps (sndfile + sox) + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg sox libsox-fmt-all \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt

# ставим CPU torch+torchaudio из официального индекса
RUN pip install -U pip wheel setuptools \
 && pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    torch torchaudio \
 && pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 5001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5001"]
