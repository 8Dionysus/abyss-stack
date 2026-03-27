FROM docker.io/library/python@sha256:fa48eefe2146644c2308b909d6bb7651a768178f84fc9550dcd495e4d6d84d01

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
