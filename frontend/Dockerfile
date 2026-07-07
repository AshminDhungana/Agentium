# ═════════════════════════════════════════════════════════════════
# Agentium Frontend Dockerfile ━━ Multi-Stage Hardened
# ═════════════════════════════════════════════════════════════════

# Global ARGs (must come before first FROM to be usable in FROM lines)
ARG NODE_DIGEST=sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293
ARG NGINX_DIGEST=sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa

# ── Build stage ──
FROM node:20-alpine@${NODE_DIGEST} AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install && npm install --save-dev @types/node

COPY . .
RUN npm run build


# ── Production stage ──
FROM nginx:alpine@${NGINX_DIGEST}

# Create non-root user for nginx (keep UID 101 to match nginx:alpine default user UID)
RUN adduser -S -G www-data -u 101 agentium-nginx 2>/dev/null || true && \
    mkdir -p /var/cache/nginx /var/log/nginx /run && \
    chown -R 101:www-data /var/cache/nginx /var/log/nginx /usr/share/nginx/html /run

# Copy built files from builder
COPY --from=builder --chown=101:www-data /app/dist /usr/share/nginx/html

# Copy nginx config
COPY --from=builder --chown=101:www-data /app/nginx.conf /etc/nginx/conf.d/default.conf

# Set worker processes to auto and pid path for non-root
RUN sed -i 's/user  nginx;/user agentium-nginx;/g' /etc/nginx/nginx.conf && \
    sed -i '/^pid/d' /etc/nginx/nginx.conf && \
    echo 'pid /tmp/nginx.pid;' >> /etc/nginx/nginx.conf

USER 101

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
