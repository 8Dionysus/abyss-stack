FROM mcr.microsoft.com/playwright/python:v1.59.0-noble@sha256:d8d9811a0e7cfac967f0c2f55d12b739087ae4b0808577b794c2a29ed5124938
WORKDIR /app
COPY app.py /app/app.py
RUN python -m pip install --no-cache-dir fastapi uvicorn playwright==1.59.0
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8000"]
