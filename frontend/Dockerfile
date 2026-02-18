# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files FIRST (this layer is cached unless package.json changes)
COPY package.json package-lock.json* ./

# Install dependencies AND types in ONE RUN command
# This prevents cache invalidation from the extra npm install
RUN npm install && npm install --save-dev @types/node

# Copy source code (cache preserved if package files unchanged)
COPY . .

# Build for production
RUN npm run build


# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]