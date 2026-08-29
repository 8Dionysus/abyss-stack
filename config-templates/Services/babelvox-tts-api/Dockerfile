FROM docker.io/openvino/model_server:2026.3-gpu@sha256:2a52cd2bc62d984f35f12b1cf58bb5dffe5f5d57b6ef3349b1b37229a768806b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/babelvox-tts-api-venv \
    PATH=/opt/babelvox-tts-api-venv/bin:$PATH

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    libsndfile1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt

RUN python3 -m venv "${VIRTUAL_ENV}" \
 && pip install -U pip wheel setuptools \
 && pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 5102
ENTRYPOINT []
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5102"]
