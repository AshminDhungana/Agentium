FROM node:20-alpine

WORKDIR /app

# git is required by baileys (fetches deps from GitHub during npm install)
# python3/make/g++ are needed for native addon compilation
RUN apk add --no-cache git python3 make g++

# Install dependencies first (cached layer)
COPY package.json ./
RUN npm install --omit=dev

# Copy source
COPY index.js ./

# Auth data persisted via Docker volume
VOLUME /app/auth_info

EXPOSE 3001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3001/health || exit 1

CMD ["node", "index.js"]