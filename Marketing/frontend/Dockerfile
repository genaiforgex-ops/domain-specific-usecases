# --- Build stage ---
FROM node:20-slim AS build

WORKDIR /app

# Install dependencies from lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# API base URL baked into the bundle at build time. Empty by default so the app
# issues same-origin relative requests (/api/...), which the ingress / Istio
# VirtualService routes to the backend. Override with
# --build-arg VITE_API_URL=https://host only if the API lives on another origin.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --- Serve stage ---
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
