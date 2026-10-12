FROM node:18-alpine AS base

WORKDIR /app

COPY frontend/package.json ./
RUN npm install

COPY frontend/ .

FROM base AS build
RUN npm run build

FROM nginx:alpine AS serve
RUN apk add --no-cache ca-certificates
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["sh", "-c", "BACKEND_URL=\"${BACKEND_URL:-http://backend:8000}\"; case \"$BACKEND_URL\" in http://*|https://*) ;; *) BACKEND_URL=\"https://$BACKEND_URL\" ;; esac; sed -i \"s|__BACKEND_URL__|$BACKEND_URL|g\" /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
