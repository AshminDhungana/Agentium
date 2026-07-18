# ═════════════════════════════════════════════════════════════════
# Agentium Frontend Dockerfile ━━ Multi-Stage Hardened
# ═════════════════════════════════════════════════════════════════

# Global ARGs (must come before first FROM to be usable in FROM lines)
ARG NODE_BASE=node:20-alpine
ARG NGINX_BASE=nginx:alpine

# ── Build stage ──
FROM ${NODE_BASE} AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install && npm install --save-dev @types/node

COPY . .
RUN npm run build


# ── Production stage ──
FROM ${NGINX_BASE}

# Create non-root user for nginx (keep UID 101 to match nginx:alpine default user UID)
RUN adduser -S -G www-data -u 101 agentium-nginx 2>/dev/null || true && \
    mkdir -p /var/cache/nginx /var/log/nginx /run && \
    chown -R 101:www-data /var/cache/nginx /var/log/nginx /usr/share/nginx/html /run

# Copy built files from builder
COPY --from=builder --chown=101:www-data /app/dist /usr/share/nginx/html

# Copy nginx config
COPY --from=builder --chown=101:www-data /app/nginx.conf /etc/nginx/conf.d/default.conf

# Set worker processes to auto and pid path for non-root.
# The master process runs as non-root (USER 101), so nginx ignores any `user`
# directive and logs a warning. Remove it entirely rather than substituting.
RUN sed -i '/^user /d' /etc/nginx/nginx.conf && \
    sed -i '/^pid/d' /etc/nginx/nginx.conf && \
    echo 'pid /tmp/nginx.pid;' >> /etc/nginx/nginx.conf

USER 101

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
