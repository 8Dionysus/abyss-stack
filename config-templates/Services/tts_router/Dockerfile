FROM docker.io/library/python@sha256:fa48eefe2146644c2308b909d6bb7651a768178f84fc9550dcd495e4d6d84d01
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py /app/app.py
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5201"]
