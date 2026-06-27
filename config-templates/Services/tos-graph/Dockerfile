FROM docker.io/library/node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS ui-builder

WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM docker.io/library/python:3.14-slim@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY --from=ui-builder /ui/dist ./app/static
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","5410"]
