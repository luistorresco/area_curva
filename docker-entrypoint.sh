#!/bin/sh
set -eu

sed -i \
  -e "s|__BACKEND_URL__|http://127.0.0.1:8000|g" \
  -e "s|__PORT__|${PORT:-80}|g" \
  /etc/nginx/conf.d/default.conf

uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers &

exec nginx -g 'daemon off;'
