FROM docker.io/library/python@sha256:fa48eefe2146644c2308b909d6bb7651a768178f84fc9550dcd495e4d6d84d01

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ripgrep для быстрого поиска, ca-certificates для нормальных HTTPS при надобности
RUN apt-get update \
 && apt-get install -y --no-install-recommends ripgrep ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "-k", "gthread", "--threads", "8", "app:app"]
