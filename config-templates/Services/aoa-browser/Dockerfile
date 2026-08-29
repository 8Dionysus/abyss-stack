FROM mcr.microsoft.com/playwright/python:v1.62.0-noble@sha256:aa81288e738725378becba5b3e06cb0f3a7f012a610e87e8d767a090ea3f740d
WORKDIR /app
COPY app.py /app/app.py
RUN python -m pip install --no-cache-dir fastapi==0.136.3 uvicorn[standard]==0.48.0 playwright==1.62.0
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8000"]
