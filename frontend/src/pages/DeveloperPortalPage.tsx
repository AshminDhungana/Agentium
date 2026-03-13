import React, { useState } from 'react';
import {
    Code2,
    BookOpen,
    TerminalSquare,
    Zap,
    Copy,
    Check,
    Lock,
    Webhook
} from 'lucide-react';

type TabType = 'overview' | 'python' | 'typescript' | 'curl' | 'webhooks';

const ENDPOINTS = [
  { method: 'GET', path: '/api/v1/agents', desc: 'List all agents' },
  { method: 'GET', path: '/api/v1/agents/:id', desc: 'Get agent by ID' },
  { method: 'POST', path: '/api/v1/agents/create', desc: 'Create agent' },
  { method: 'GET', path: '/api/v1/tasks', desc: 'List tasks' },
  { method: 'POST', path: '/api/v1/tasks', desc: 'Create task' },
  { method: 'GET', path: '/api/v1/constitution', desc: 'Get constitution' },
  { method: 'POST', path: '/api/v1/constitution/update', desc: 'Update constitution' },
  { method: 'GET', path: '/api/v1/voting/proposals', desc: 'List proposals' },
  { method: 'POST', path: '/api/v1/voting/proposals/:id/vote', desc: 'Cast vote' },
  { method: 'POST', path: '/api/v1/chat/send', desc: 'Send chat message' },
  { method: 'GET', path: '/api/v1/webhooks/subscriptions', desc: 'List webhooks' },
  { method: 'POST', path: '/api/v1/webhooks/subscriptions', desc: 'Create webhook' },
  { method: 'DELETE', path: '/api/v1/webhooks/subscriptions/:id', desc: 'Delete webhook' },
];

const WEBHOOK_EVENTS = [
  { event: 'task.created', desc: 'A new task has been created' },
  { event: 'task.completed', desc: 'A task completed successfully' },
  { event: 'task.failed', desc: 'A task execution failed' },
  { event: 'vote.started', desc: 'A new voting proposal has begun' },
  { event: 'vote.resolved', desc: 'A vote has been resolved' },
  { event: 'constitution.amended', desc: 'The constitution was amended' },
  { event: 'agent.spawned', desc: 'A new agent was spawned' },
  { event: 'agent.terminated', desc: 'An agent was terminated' },
];

const PYTHON_SAMPLE = `from agentium_sdk import AgentiumClient

async with AgentiumClient(
    "http://localhost:8000",
    api_key="sk-your-key-here",
) as client:
    # Health check
    health = await client.health()
    print(f"Status: {health.status}")

    # List agents
    agents = await client.list_agents()
    for agent in agents:
        print(f"  {agent.agentium_id} — {agent.role}")

    # Create a task
    task = await client.create_task(
        title="Summarize report",
        description="Q4 financial summary",
    )
    print(f"Task: {task.id}")

    # Register a webhook
    webhook = await client.create_webhook_subscription(
        url="https://your-server.com/webhook",
        events=["task.completed", "vote.resolved"],
    )
    print(f"Webhook: {webhook.id}")`;

const TS_SAMPLE = `import { AgentiumClient } from '@agentium/sdk';

const client = new AgentiumClient({
  baseUrl: 'http://localhost:8000',
  apiKey: 'sk-your-key-here',
});

// Health check
const health = await client.health();
console.log(\`Status: \${health.status}\`);

// List agents
const agents = await client.listAgents();
agents.forEach(a =>
  console.log(\`  \${a.agentium_id} — \${a.role}\`),
);

// Create a task
const task = await client.createTask({
  title: 'Summarize report',
  description: 'Q4 financial summary',
});
console.log(\`Task: \${task.id}\`);

// Register a webhook
const webhook = await client.createWebhookSubscription({
  url: 'https://your-server.com/webhook',
  events: ['task.completed', 'vote.resolved'],
});
console.log(\`Webhook: \${webhook.id}\`);`;

const CURL_SAMPLE = `# Health check
curl -s http://localhost:8000/api/health | jq

# List agents
curl -s -H "X-API-Key: sk-your-key" \\
  http://localhost:8000/api/v1/agents | jq

# Create a task
curl -s -X POST \\
  -H "X-API-Key: sk-your-key" \\
  -H "Content-Type: application/json" \\
  -d '{"title":"Summarize report","description":"Q4 financials"}' \\
  http://localhost:8000/api/v1/tasks | jq

# Register a webhook
curl -s -X POST \\
  -H "X-API-Key: sk-your-key" \\
  -H "Content-Type: application/json" \\
  -d '{"url":"https://your-server.com/hook","events":["task.completed"]}' \\
  http://localhost:8000/api/v1/webhooks/subscriptions | jq`;

const getMethodClasses = (method: string) => {
    switch (method) {
        case 'GET': return 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400';
        case 'POST': return 'bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400';
        case 'PUT': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400';
        case 'DELETE': return 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400';
        default: return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400';
    }
};

const DeveloperPortalPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [copiedStates, setCopiedStates] = useState<Record<string, boolean>>({});

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedStates(prev => ({ ...prev, [id]: true }));
    setTimeout(() => {
        setCopiedStates(prev => ({ ...prev, [id]: false }));
    }, 2000);
  };

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'API Reference', icon: <BookOpen className="w-4 h-4" /> },
    { key: 'python', label: 'Python SDK', icon: <Code2 className="w-4 h-4" /> },
    { key: 'typescript', label: 'TypeScript SDK', icon: <Code2 className="w-4 h-4" /> },
    { key: 'curl', label: 'cURL', icon: <TerminalSquare className="w-4 h-4" /> },
    { key: 'webhooks', label: 'Webhook Events', icon: <Webhook className="w-4 h-4" /> },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────── */}
      <div className="mb-8">
          <div className="flex items-center gap-3 mb-1">
              <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-purple-600 dark:from-blue-400 dark:to-purple-400">
                  Developer Portal
              </h1>
          </div>
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            API documentation, code samples, and webhook event reference for the Agentium platform.
          </p>
      </div>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-2 border-b border-gray-200 dark:border-[#1e2535] pb-4 mb-6">
        {tabs.map(({ key, label, icon }) => (
          <button
            key={key}
            className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 flex items-center gap-2 ${
                activeTab === key
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:text-gray-900 dark:hover:text-white border border-transparent'
            }`}
            onClick={() => setActiveTab(key)}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-6">
          {/* Overview tab */}
          {activeTab === 'overview' && (
            <>
              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <Zap className="w-5 h-5 text-blue-500" /> API Endpoints
                </h3>
                <div className="bg-gray-50 dark:bg-[#0f1117] p-4 rounded-lg border border-gray-200 dark:border-[#1e2535] mb-6 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-400">
                    <div>Base URL: <code className="text-blue-600 dark:text-blue-400 font-mono">http://localhost:8000</code></div>
                    <div className="hidden sm:block text-gray-300 dark:text-[#2a3347]">|</div>
                    <div>Interactive docs: <a href="/docs" className="text-blue-600 dark:text-blue-400 hover:underline">/docs</a></div>
                    <div className="hidden sm:block text-gray-300 dark:text-[#2a3347]">|</div>
                    <div>OpenAPI spec: <a href="/openapi.json" className="text-blue-600 dark:text-blue-400 hover:underline">/openapi.json</a></div>
                </div>

                <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                  {ENDPOINTS.map((ep, i) => (
                    <div key={i} className="py-3 flex flex-col sm:flex-row sm:items-center gap-3 hover:bg-gray-50 dark:hover:bg-[#0f1117] -mx-4 px-4 transition-colors">
                      <div className="w-20 shrink-0">
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold font-mono text-center w-full ${getMethodClasses(ep.method)}`}>
                              {ep.method}
                          </span>
                      </div>
                      <code className="text-sm text-gray-800 dark:text-gray-200 font-mono bg-gray-100 dark:bg-[#0f1117] px-2 py-0.5 rounded border border-gray-200 dark:border-[#2a3347]">
                          {ep.path}
                      </code>
                      <span className="text-sm text-gray-500 dark:text-gray-400 sm:ml-auto">
                          {ep.desc}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <Lock className="w-5 h-5 text-blue-500" /> Authentication
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  All API requests require authentication via one of:
                </p>
                <ul className="list-disc list-inside space-y-2 text-sm text-gray-700 dark:text-gray-300">
                  <li>
                    <strong>API Key:</strong> Send <code className="text-blue-600 dark:text-blue-400 font-mono bg-blue-50 dark:bg-blue-500/10 px-1 py-0.5 rounded">X-API-Key: sk-...</code> header
                  </li>
                  <li>
                    <strong>JWT Token:</strong> Send <code className="text-blue-600 dark:text-blue-400 font-mono bg-blue-50 dark:bg-blue-500/10 px-1 py-0.5 rounded">Authorization: Bearer &lt;token&gt;</code> header
                  </li>
                </ul>
              </div>
            </>
          )}

          {/* Python SDK tab */}
          {activeTab === 'python' && (
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <Code2 className="w-5 h-5 text-blue-500" /> Python SDK
                </h3>
                <div className="flex items-center gap-3 bg-gray-50 dark:bg-[#0f1117] p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535]">
                    <code className="text-sm text-gray-700 dark:text-gray-300 font-mono px-3 whitespace-nowrap">pip install agentium-sdk</code>
                    <button 
                        className="p-1.5 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded transition-colors"
                        onClick={() => copyToClipboard('pip install agentium-sdk', 'py-install')}
                        title="Copy install command"
                    >
                        {copiedStates['py-install'] ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                    </button>
                </div>
              </div>
              <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button 
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-400 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(PYTHON_SAMPLE, 'py-code')}
                          title="Copy Code"
                      >
                          {copiedStates['py-code'] ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                      </button>
                  </div>
                  <pre className="p-4 text-sm text-[#c9d1d9] font-mono overflow-auto leading-relaxed max-h-[500px]">
                    <code>{PYTHON_SAMPLE}</code>
                  </pre>
              </div>
            </div>
          )}

          {/* TypeScript SDK tab */}
          {activeTab === 'typescript' && (
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <Code2 className="w-5 h-5 text-blue-500" /> TypeScript SDK
                </h3>
                <div className="flex items-center gap-3 bg-gray-50 dark:bg-[#0f1117] p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535]">
                    <code className="text-sm text-gray-700 dark:text-gray-300 font-mono px-3 whitespace-nowrap">npm install @agentium/sdk</code>
                    <button 
                        className="p-1.5 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded transition-colors"
                        onClick={() => copyToClipboard('npm install @agentium/sdk', 'ts-install')}
                        title="Copy install command"
                    >
                        {copiedStates['ts-install'] ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                    </button>
                </div>
              </div>
              <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button 
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-400 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(TS_SAMPLE, 'ts-code')}
                          title="Copy Code"
                      >
                          {copiedStates['ts-code'] ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                      </button>
                  </div>
                  <pre className="p-4 text-sm text-[#c9d1d9] font-mono overflow-auto leading-relaxed max-h-[500px]">
                    <code>{TS_SAMPLE}</code>
                  </pre>
              </div>
            </div>
          )}

          {/* cURL tab */}
          {activeTab === 'curl' && (
            <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                  <TerminalSquare className="w-5 h-5 text-blue-500" /> cURL Examples
              </h3>
              <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button 
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-400 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(CURL_SAMPLE, 'curl-code')}
                          title="Copy Code"
                      >
                          {copiedStates['curl-code'] ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                      </button>
                  </div>
                  <pre className="p-4 text-sm text-[#c9d1d9] font-mono overflow-auto leading-relaxed max-h-[500px]">
                    <code>{CURL_SAMPLE}</code>
                  </pre>
              </div>
            </div>
          )}

          {/* Webhook Events tab */}
          {activeTab === 'webhooks' && (
            <div className="space-y-6">
              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                    <Webhook className="w-5 h-5 text-purple-500" /> Event Types
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6 leading-relaxed">
                  Register webhook subscriptions to receive real-time event
                  notifications. Each event is delivered as a POST request with an
                  HMAC-SHA256 signature in the <code className="text-purple-600 dark:text-purple-400 font-mono bg-purple-50 dark:bg-purple-500/10 px-1 py-0.5 rounded">X-Agentium-Signature</code> header.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {WEBHOOK_EVENTS.map((ev) => (
                    <div key={ev.event} className="bg-gray-50 dark:bg-[#0f1117] rounded-lg p-4 border border-gray-200 dark:border-[#1e2535] flex flex-col gap-1.5 hover:border-purple-200 dark:hover:border-purple-500/30 transition-colors">
                      <code className="text-sm text-purple-700 dark:text-purple-400 font-semibold font-mono">
                          {ev.event}
                      </code>
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        {ev.desc}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Lock className="w-5 h-5 text-gray-500" /> Verifying Signatures
                    </h3>
                </div>
                <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button 
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-400 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(`import hmac, hashlib

def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Verify Agentium webhook signature."""
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)`, 'verify-code')}
                          title="Copy Code"
                      >
                          {copiedStates['verify-code'] ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                      </button>
                  </div>
                  <pre className="p-4 text-sm text-[#c9d1d9] font-mono overflow-auto leading-relaxed">
                    <code>{`import hmac, hashlib

def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Verify Agentium webhook signature."""
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)`}</code>
                  </pre>
                </div>
              </div>
            </div>
          )}
      </div>
    </div>
  );
};

export default DeveloperPortalPage;
