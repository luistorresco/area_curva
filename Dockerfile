FROM node:18-alpine AS frontend-build

WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim AS backend-build
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/main.py .

FROM python:3.11-slim AS final
RUN apt-get update && apt-get install -y --no-install-recommends nginx && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default
COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY --from=backend-build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-build /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY backend/main.py /app/main.py
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
WORKDIR /app
EXPOSE 80
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 & nginx -g 'daemon off;'"]
