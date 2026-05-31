FROM docker.io/openvino/model_server:2026.2-gpu@sha256:fdc34725b35d79cde23cff1967f90efb40237b7cf5545a70460209056f3da733

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/rerank-api-venv \
    PATH=/opt/rerank-api-venv/bin:$PATH

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt

RUN python3 -m venv "${VIRTUAL_ENV}" \
 && pip install -U pip wheel setuptools \
 && pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    torch \
 && pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 5405
ENTRYPOINT []
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5405"]
