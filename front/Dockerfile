FROM node:24.22.2-slim AS compilacion

# Vite escribe este valor en el código al compilar: cambiarlo exige reconstruir la imagen
ARG VITE_API_URL

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.30.6-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=compilacion /app/dist /usr/share/nginx/html

EXPOSE 5173
