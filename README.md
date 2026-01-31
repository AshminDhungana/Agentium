# 🏛️ Agentium

> A local-first AI governance platform where AI agents operate like a democratic government

Agentium transforms AI task management into a structured democracy. Your AI system mirrors a government hierarchy: a **Head of Council** (Prime Minister), **Council Members** (Parliament), and **Agents** (civil servants) work together to handle your tasks efficiently and transparently.


![Development Status](https://img.shields.io/badge/status-active--development-brightgreen)


---

## ✨ What Makes Agentium Special?

**Democratic AI Governance** — Tasks aren't just executed; they're deliberated, voted on, and approved through a multi-tier AI system that ensures accountability.

**Local-First Philosophy** — Run everything on your own hardware with full control over your data and models.

**Intelligent Scaling** — The system automatically spawns new agents and council members as workload increases.

**Universal Access** — Control everything from a sleek web dashboard accessible on any device.

---

## 🎯 Core Capabilities

### Hybrid AI Models
Run powerful local models (Kimi 2.5, GPT-4) or leverage API services (Anthropic, OpenAI, Gemini) based on your needs and resources.

### Hierarchical AI System

```
👑 You (The Sovereign)
    ↓
🏛️ Head of Council — Full authority, approves/rejects major decisions
    ↓
⚖️ Council Members — Deliberate and vote on proposals
    ↓
🎯 Lead Agents — Coordinate and delegate work
    ↓
🤖 Task Agents — Execute specific assignments
```

**Head of Council**  
- Ultimate decision-maker with full system access
- Approves/rejects task proposals
- Manages system configuration

**Council Members**  
- Vote on important tasks and decisions
- Partial system access with oversight powers
- Auto-scale: 1 new member per 10 tasks

**Lead Agents**  
- Coordinate task distribution
- Manage agent teams
- Monitor execution progress

**Task Agents**  
- Execute assigned work
- Restricted permissions for security
- Auto-spawn based on workload

### Comprehensive Features

**🌐 Multi-Channel Integration**  
Connect via WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, Microsoft Teams, and more.

**🎙️ Voice Interaction**  
Always-on speech recognition for macOS, iOS, and Android.

**🎨 Visual Workspace**  
Live canvas with agent-driven visual collaboration and A2UI support.

**🔧 Powerful Automation**  
- Browser control and automation
- Cron-scheduled tasks
- Webhook integrations
- Gmail Pub/Sub integration

**🔒 Enterprise Security**  
- Granular per-agent permissions
- Container sandboxing
- Complete audit logging
- Session management and pruning

**📊 Full Observability**  
- Real-time task monitoring
- Health checks and logging
- Performance metrics
- Audit trail for all actions

---

## 🏗️ Architecture

Agentium uses a containerized microservices architecture where each component runs in isolation:

```
┌─────────────────────────────────────────────┐
│  Web Dashboard (React + TypeScript)         │
│  Accessible from any browser/device         │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  API Gateway (FastAPI)                      │
│  WebSocket + REST endpoints                 │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Head of Council (AI Model)                 │
│  Full access • Decision authority           │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Council Members (AI Models)                │
│  Voting • Partial access                    │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Lead Agents (AI Models)                    │
│  Task coordination • Team management        │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Task Agents (AI Models)                    │
│  Execution • Restricted access              │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Database (SQLite/PostgreSQL/VectorDB)      │
│  Audit logs • Session data • Configurations │
└─────────────────────────────────────────────┘
```

---
## Internal  Documentation

### Constituion
- Start with the base template
- Defines The Sovereign Preference
- Defines Rules on What to do and What not to do
- Updated by voting of Council Members and approved by Head of Council
- Updated everyday
- The Constitution is updated read only for any other body then the Head of Council

### Individual Agent Ethos 
- Each Agent has its own Ethos
- Ethos is created by the higher authority of the Agent with default template.
- Defines Rules on What to do and What not to do
- Updated by Individual Agent and verified and updated by Lead Agent
- For Lead Agents, the Lead Agent Ethos is updated by Head of Council

### On Creation
- Each Head of Council/ Council Member/ Lead Agent/ Task Agent is created with a default Ethos
- The Ethos is created by the higher authority of the Agent with default template.
- The Created Head of Council/ Council Member/ Lead Agent/ Task Agent reads the Constitution
- The Created Head of Council/ Council Member/ Lead Agent/ Task Agent reads its own Ethos

### Termination
- Head of Council is never Teminated
- Council Member is terminated if it violates the Constitution
- Lead Agent is terminated if it violates the Constitution
- Task Agent is terminated if it violates the Constitution
- Agents are terminated after the assigned task is completed.

### Identification
- All Agents are identified with a identification number.
- Head of Council: 0xxxx
- Council Member: 1xxxx
- Lead Agent: 2xxxx 
- Task Agent: 3xxxx

---

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- 4GB+ RAM recommended
- Windows, macOS, or Linux

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentium.git
cd agentium

# Start the system
docker-compose up --build

# Access the dashboard
# Open http://localhost:3000 in your browser
# Default login: admin / admin
```

That's it! Your AI governance system is now running.

---

## 📖 Usage Guide

### Getting Started

1. **Login to Dashboard**  
   Navigate to `http://localhost:3000` and use the default credentials

2. **Configure API Keys**  
   Add your API keys for external AI services (optional)

3. **Send Your First Task**  
   Message the Head of Council through the chat interface

4. **Watch Democracy in Action**  
   - Head of Council receives your request
   - Council Members deliberate and vote
   - Lead Agents assign work
   - Task Agents execute
   - Results flow back to you

### Managing Your System

**Update Models**  
Switch between local and API models per role in `config/roles.json`

**Adjust Permissions**  
Control what each tier can access via the dashboard

**Monitor Activity**  
View real-time task status, votes, and execution logs

**Scale Resources**  
System auto-scales, but you can manually adjust limits

### Advanced Features

**Voice Commands**  
Enable always-on voice interaction for hands-free operation

**Browser Automation**  
Let agents interact with websites on your behalf

**Scheduled Tasks**  
Set up recurring jobs with cron syntax

**Multi-Channel**  
Connect messaging platforms for ubiquitous access

---

## ⚙️ Configuration

### Model Configuration

Edit `config/roles.json` to specify models for each role:

```json
{
  "head_of_council": {
    "model": "gpt-4",
    "type": "api"
  },
  "council_members": {
    "model": "kimi-2.5",
    "type": "local"
  }
}
```

### Permissions

Fine-grained access control per role:
- **Full Access**: Head of Council
- **Partial Access**: Council Members, Lead Agents
- **Restricted Access**: Task Agents

Update permissions dynamically through the dashboard.

### Messaging Channels

Configure integrations in `config/channels.json`:
- WhatsApp, Telegram, Slack
- Discord, Google Chat, Signal
- iMessage, Microsoft Teams
- Custom WebChat

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React, TypeScript |
| **Backend** | Python, FastAPI |
| **AI Models** | Local (Kimi 2.5, GPT-4) + API (Anthropic, OpenAI, Gemini) |
| **Database** | SQLite / PostgreSQL |
| **Containers** | Docker, docker-compose |
| **Communication** | WebSocket, REST API |
| **Deployment** | Local-first, Tailscale/SSH remote access |

---

## 🤝 Contributing

We welcome contributions! Here's how you can help:

- 🐛 Report bugs via GitHub Issues
- 💡 Suggest features and improvements
- 🔧 Submit pull requests
- 📖 Improve documentation
- 🌍 Add translations

Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting PRs.

---

## 📋 Roadmap

- [-] Project Development Ongoing
- [ ] Plugin marketplace for custom agents
- [ ] Mobile companion apps (iOS/Android)
- [ ] Advanced analytics dashboard
- [ ] Multi-user support with RBAC
- [ ] Integration with more AI providers
- [ ] Natural language config management

---

## 📄 License

This project is licensed - see the [LICENSE](LICENSE) file for details.

---



## 💬 Support

- 📚 [Documentation] (Coming Soon)
- 📧 Email: [EMAIL_ADDRESS]

---

<p align="center">
  <strong>Built with ❤️ and purpose by Ashmin Dhungana</strong>
</p>
