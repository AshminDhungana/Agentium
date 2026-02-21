## 🧠 Agent Cognitive Workflow — Ethos & Knowledge Lifecycle (Done) [Verify at the End]

### Core Concepts

- **Ethos** → The agent’s working memory.  
  A dynamic, minimal, continuously updated internal state that contains:
  - Current objective
  - Active plan
  - Relevant constitutional references
  - Temporary reasoning artifacts
  - Task progress markers

- **ChromaDB (Vector Database)** → The Knowledge Library.  
  A persistent semantic memory system that stores:
  - Constitution embeddings
  - Task learnings
  - Skills and capabilities
  - Best practices
  - Institutional knowledge

Ethos is short-term working cognition.  
ChromaDB is long-term institutional memory.

---

## 🏛️ Agent Lifecycle & Cognitive Process

### 1. Agent Creation

When an agent is instantiated:

1. First Startup, Constitution is created and stored in ChromaDB
2. Then three Agents are created Head of Council - 1 Nos and Council Members - 2 Nos
3. All Agents are initialized with a **base Ethos** containing:
   - Core operational rules
   - Role-based instructions
   - Hierarchical authority level
4. It immediately reads the **Constitution**.
5. It updates its Ethos with:
   - A summarized constitutional interpretation  
     OR
   - A reference pointer to relevant constitutional sections.

This ensures all actions are constitutionally aligned before execution begins.

---

### 2. Task Reception & Planning

Upon receiving a task: 0. The Head of Council will use its ethos as well as the chat content (That is recent chat history of last 2 days or the last 20 messages) if required can view entire chat history but that should be the last set of actions for better understanding of the task.

1. The agent generates a structured execution plan.
2. If anything is unclear the agent will ask for clarification from the above.
3. The hierarchy of clarification is as follows:
   - User The Soverigin
   - Head of Council
   - Council Members
   - Lead Agents
   - Task Agents
   - Code Critic Agents
   - Output Critic Agents
   - Plan Critic Agents
     Clarification follows the command structure of the agent.
     for example: If Council Member is not clear about something it will ask for clarification from Head of Council, And if Head of Council is not clear about something it will ask for clarification from User The Soverigin.
     Only the necessary Clarification will be asked from the user.
4. The plan is written into its Ethos.
5. If updating Ethos fails (conflict, corruption, inconsistency):
   - The planning phase is retried.
   - Ethos is corrected before proceeding.

No execution begins without a successfully updated Ethos.

---

### 3. Task Execution

During execution:

- The agent performs actions incrementally.
- After each completed sub-step:
  - Irrelevant or obsolete Ethos content is removed.
  - Only necessary state is retained.
- Ethos is continuously minimized to prevent cognitive bloat.

The agent maintains only what is required to complete the active task.

---

### 4. Skill & Knowledge Creation

When new knowledge or skills are generated:

1. The agent first searches **ChromaDB** (Vector Database):
   - If similar knowledge exists → retrieve, revise, and update.
   - Agent can also use self knowledge, web search to verify and update the knowledge.
   - If not → create a new semantic entry can use any means for researching about it.
2. Updated or new knowledge is embedded and stored.
3. The institutional memory remains deduplicated and curated.

No knowledge is stored blindly.  
All entries are revision-aware.

---

### 5. Task Completion

After completing the task:

1. The agent confirms task completion.
2. It updates its Ethos with:
   - Outcome summary
   - Lessons learned
   - Any relevant references
3. It summarizes and compresses its Ethos.
4. It resets its working state.
5. It re-reads the Constitution before accepting new tasks.

This ensures constitutional recalibration between tasks.

---

## 🏗️ Hierarchical Ethos Oversight

Agent hierarchy enforces structured governance:

- Higher-tier agents (e.g., Head, Council, Lead)  
  may:
  - View subordinate agent Ethos
  - Edit subordinate Ethos
  - Correct inconsistencies
  - Override unsafe reasoning

- Lower-tier agents cannot modify higher-tier Ethos.

This maintains supervisory integrity while preserving execution autonomy.

---

## 🔐 Design Principles

- **Working Memory Minimization**
- **Constitutional Alignment First**
- **Semantic Knowledge Persistence**
- **Revision Over Duplication**
- **Hierarchical Cognitive Oversight**
- **Explicit Completion Confirmation**
- **Post-Task Recalibration**

---

This workflow ensures:

- Cognitive discipline
- Constitutional compliance
- Knowledge continuity
- Hierarchical accountability
- Sustainable long-term operation
