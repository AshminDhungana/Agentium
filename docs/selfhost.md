# 🏛️ Agentium Self-Hosting Guide

> Quick setup guide for running Agentium in different environments.

Agentium runs using Docker and includes:

Core Services (7 containers) - Postgres - ChromaDB - Redis - Backend
(FastAPI) - Celery Worker - Celery Beat - Frontend

CI/CD Services (4 containers) - GitHub Runner - BuildKit - Registry
Cache - Deployment Controller

---

# 🚀 Choose Your Deployment Type

Use Case Recommended Setup

---

Local development Docker Compose
Small production (1 server) Single VM + Docker Compose
Scalable production Kubernetes / Swarm
Automated deployment Enable CI/CD stack

---

# 1️⃣ Local Development

Requirements: - Docker 20+ - Docker Compose v2+ - 8GB RAM minimum

Setup:

git clone https://github.com/AshminDhungana/Agentium.git cd Agentium cp
.env.example .env docker compose up -d

Access: - Frontend → http://localhost:3000 - Backend →
http://localhost:8000 - API Docs → http://localhost:8000/docs

Stop: docker compose down

---

# 2️⃣ Single Server (Production VM)

Recommended: - 4 vCPU - 16GB RAM - 80GB SSD

Setup:

curl -fsSL https://get.docker.com \| sh git clone
https://github.com/AshminDhungana/Agentium.git cd Agentium cp
.env.example .env \# Configure strong secrets inside .env docker compose
-f docker-compose.prod.yml up -d

Recommended additions: - Nginx reverse proxy - HTTPS via Let's Encrypt -
Daily Postgres backups - Firewall enabled

---

# 3️⃣ Scalable Deployment (Microservices)

Recommended platforms: - Kubernetes - Docker Swarm

Scaling Rules:

Service Scalable

---

Backend Yes
Celery Worker Yes
Frontend Yes
Postgres Single (or managed DB)
Redis Single / Sentinel
ChromaDB Single (stateful)
Celery Beat Single

Deploy using provided /k8s manifests or Helm charts.

---

# 4️⃣ CI/CD Deployment

CI/CD handles: - Build - Test - Push images (GHCR) - Deploy

Run CI/CD stack:

docker compose -f docker-compose.cicd.yml up -d

Deployment flow:

Git Push → Build → Test → Push → Deploy

---

# 🔐 Production Best Practices

- Never commit .env
- Use strong secrets
- Enable HTTPS
- Backup Postgres daily
- Avoid using latest tag in production

---

# 📌 Summary Commands

Local: docker compose up -d

Production VM: docker compose -f docker-compose.prod.yml up -d

CI/CD: docker compose -f docker-compose.cicd.yml up -d

Kubernetes: kubectl apply -f k8s/

---

Apache 2.0 License
