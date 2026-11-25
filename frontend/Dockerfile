# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
ARG VITE_BACKEND_URL=http://localhost:8000
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
RUN npm run build

# Runtime stage: serve with lightweight nginx or static server
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config to handle SPA routing and port 3000
RUN cat << 'NGINX_CONF' > /etc/nginx/conf.d/default.conf
server {
    listen 3000;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files $uri $uri/ /index.html;
    }
}
NGINX_CONF

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
