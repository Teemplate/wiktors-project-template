# Multi-stage. `target: dev` is used by compose/web.dev.yml, `target: prod` by
# compose/web.deploy.yml and compose/web.e2e.yml.

# ---------- deps ----------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# `npm ci` needs a lockfile; fall back on first run before one is committed.
RUN npm ci || npm install

# ---------- dev ----------
FROM deps AS dev
COPY . .
EXPOSE 5173
# Every container in this template reports health (scripts/check_healthchecks.py
# enforces it). The dev server has no /healthz; its index answering is the signal.
# 127.0.0.1, not localhost: Alpine resolves localhost to ::1 first and busybox
# wget does not fall back.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD wget -q -O /dev/null -T 4 http://127.0.0.1:5173/ || exit 1
CMD ["npm", "run", "dev"]

# ---------- build ----------
FROM deps AS build
# NOTE the order: source is copied, THEN node_modules is restored from `deps`.
# Doing it the other way round lets the host's node_modules (x86-64, if the
# .dockerignore ever fails) overwrite the image's arm64 install — the exact bug
# that has broken real deployments.
COPY . .
COPY --from=deps /app/node_modules ./node_modules
# VITE_* values are inlined into the bundle here, at build time.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---------- prod ----------
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
# SPA fallback + asset caching, plus the /api proxy snippet when the project has
# the api block. Kept as files rather than an inline printf so they stay
# readable and can be edited without touching the Dockerfile.
#
# Dropped into /etc/nginx/templates so the official image's entrypoint runs
# envsubst over them at start-up (subdirectories included) and fills in
# ${BACKEND_HOST}. That keeps the backend's container name -- which depends on
# the compose project name -- out of the image, so the same image works for
# dev, e2e, staging and production.
COPY nginx/ /etc/nginx/templates/
ENV BACKEND_HOST=backend
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d
# WITHOUT this filter, envsubst would also eat nginx's own runtime variables --
# $host, $remote_addr, $proxy_add_x_forwarded_for, $uri -- replacing them with
# empty strings and breaking the proxy headers and the SPA fallback. Restrict
# it to the one variable we actually template.
ENV NGINX_ENVSUBST_FILTER=BACKEND_HOST
EXPOSE 5173
# Baked into the image, not the compose file, so the container is checked however
# it is started (deploy, e2e, a bare `docker run`). /healthz is nginx's own answer
# (nginx/default.conf.template); the deploy gate waits for this to say healthy.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null -T 4 http://127.0.0.1:5173/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
