# WhatsApp Web Bridge (Baileys) ━━ Non-Root Hardened
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293

WORKDIR /app

# git is required by baileys (fetches deps from GitHub during npm install)
# python3/make/g++ are needed for native addon compilation
RUN apk add --no-cache git python3 make g++

# Install dependencies first (cached layer)
COPY package.json ./
RUN npm install --omit=dev

# Copy source
COPY index.js ./

# Create and switch to non-root user
RUN addgroup -g 1001 -S appgroup && adduser -u 1001 -S appuser -G appgroup && \
    mkdir -p /app/auth_info && \
    chown -R appuser:appgroup /app

USER appuser

# Auth data persisted via Docker volume
VOLUME /app/auth_info

EXPOSE 3001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3001/health || exit 1

CMD ["node", "index.js"]
