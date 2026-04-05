FROM mcr.microsoft.com/playwright/python:v1.57.0-noble
WORKDIR /app
COPY app.py /app/app.py
RUN python -m pip install --no-cache-dir fastapi uvicorn playwright==1.57.0
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8000"]
