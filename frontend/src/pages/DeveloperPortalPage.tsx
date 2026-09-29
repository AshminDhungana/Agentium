import React, { useState, useEffect, useCallback } from 'react';
import {
    Code2,
    BookOpen,
    TerminalSquare,
    Zap,
    Copy,
    Check,
    Lock,
    Webhook,
    Key,
    Plus,
    Trash2,
    RefreshCw,
    AlertTriangle,
    Eye,
    EyeOff,
    Shield
} from 'lucide-react';
import { apiKeysService, type KeyHealthInfo, type CreateKeyRequest } from '@/services/apiKeysService';

type TabType = 'overview' | 'python' | 'typescript' | 'curl' | 'webhooks' | 'api-keys';

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
    api_key="sk-your-key-here",  # pragma: allowlist secret
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
  console.log(\`  \${a.agentium_id} — \${a.role}\`)
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

const PROVIDERS = [
  'OPENAI', 'ANTHROPIC', 'GEMINI', 'GROQ', 'MISTRAL', 'COHERE',
  'TOGETHER', 'FIREWORKS', 'PERPLEXITY', 'DEEPSEEK', 'OPENROUTER',
  'AZURE_OPENAI', 'LOCAL', 'CUSTOM',
];

const getStatusClasses = (status: string) => {
  switch (status.toUpperCase()) {
    case 'HEALTHY': return 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400';
    case 'COOLDOWN': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/10 dark:text-yellow-400';
    case 'RATE_LIMITED': return 'bg-orange-100 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400';
    case 'ERROR': return 'bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400';
    default: return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400';
  }
};

const DeveloperPortalPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [copiedStates, setCopiedStates] = useState<Record<string, boolean>>({});

  // ── API Key management state ────────────────────────────────────────────────
  const [keys, setKeys] = useState<KeyHealthInfo[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdKeyId, setCreatedKeyId] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [formData, setFormData] = useState<CreateKeyRequest>({
    provider: 'OPENAI',
    api_key: '',
    config_name: '',
    model_name: '',
    monthly_budget_usd: 0,
    priority: 1,
    is_default: false,
  });

  const loadKeys = useCallback(async () => {
    setKeysLoading(true);
    setKeysError(null);
    try {
      const report = await apiKeysService.listKeys();
      const allKeys: KeyHealthInfo[] = [];
      for (const providerData of Object.values(report.providers)) {
        if (providerData.keys) {
          allKeys.push(...providerData.keys);
        }
      }
      setKeys(allKeys);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load keys';
      setKeysError(msg);
    } finally {
      setKeysLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'api-keys') {
      loadKeys();
    }
  }, [activeTab, loadKeys]);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    setCreatedKeyId(null);
    try {
      const result = await apiKeysService.createKey(formData);
      setCreatedKeyId(result.key_id);
      setShowCreateForm(false);
      setFormData({
        provider: 'OPENAI', api_key: '', config_name: '',
        model_name: '', monthly_budget_usd: 0, priority: 1, is_default: false,
      });
      await loadKeys();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create key';
      setCreateError(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKey = async (keyId: string) => {
    try {
      await apiKeysService.deleteKey(keyId, true);
      await loadKeys();
    } catch {
      // Errors shown via toast from the global interceptor
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedStates(prev => ({ ...prev, [id]: true }));
    setTimeout(() => {
        setCopiedStates(prev => ({ ...prev, [id]: false }));
    }, 2000);
  };

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'API Reference', icon: <BookOpen className="w-4 h-4" /> },
    { key: 'api-keys', label: 'API Keys', icon: <Key className="w-4 h-4" /> },
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
          <p className="text-gray-700 dark:text-white text-sm">
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
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-900 dark:text-white border border-blue-200 dark:border-blue-700 shadow-sm'
                    : 'text-gray-700 dark:text-white hover:bg-gray-50 dark:hover:bg-[#1e2535] hover:text-gray-900 dark:hover:text-white border border-transparent'
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
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <Zap className="w-5 h-5 text-blue-600" /> API Endpoints
                </h2>
                <div className="bg-gray-50 dark:bg-[#0f1117] p-4 rounded-lg border border-gray-200 dark:border-[#1e2535] mb-6 flex flex-wrap gap-4 text-sm text-gray-700 dark:text-gray-300">
                    <div>Base URL: <code className="text-blue-600 dark:text-blue-400 font-mono">http://localhost:8000</code></div>
                    <div className="hidden sm:block text-gray-300 dark:text-[#2a3347]">|</div>
                    <div>Interactive docs: <a href="/docs" className="text-blue-600 dark:text-blue-400 hover:underline underline underline-offset-2">/docs</a></div>
                    <div className="hidden sm:block text-gray-300 dark:text-[#2a3347]">|</div>
                    <div>OpenAPI spec: <a href="/openapi.json" className="text-blue-600 dark:text-blue-400 hover:underline underline underline-offset-2">/openapi.json</a></div>
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
                      <span className="text-sm text-gray-700 dark:text-gray-300 sm:ml-auto">
                          {ep.desc}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <Lock className="w-5 h-5 text-blue-600" /> Authentication
                </h2>
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
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
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <Code2 className="w-5 h-5 text-blue-600" /> Python SDK
                </h2>
                <div className="flex items-center gap-3 bg-gray-50 dark:bg-[#0f1117] p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535]">
                    <code className="text-sm text-gray-700 dark:text-gray-300 font-mono px-3 whitespace-nowrap">pip install agentium-sdk</code>
                    <button
                        className="p-1.5 text-gray-700 hover:text-blue-700 dark:text-gray-300 dark:hover:text-gray-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded transition-colors"
                        onClick={() => copyToClipboard('pip install agentium-sdk', 'py-install')}
                        title="Copy install command" aria-label="Copy install command"
                    >
                        {copiedStates['py-install'] ? <Check className="w-4 h-4 text-green-700" /> : <Copy className="w-4 h-4" />}
                    </button>
                </div>
              </div>
              <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-300 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(PYTHON_SAMPLE, 'py-code')}
                          title="Copy Code" aria-label="Copy Code"
                      >
                          {copiedStates['py-code'] ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
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
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <Code2 className="w-5 h-5 text-blue-600" /> TypeScript SDK
                </h2>
                <div className="flex items-center gap-3 bg-gray-50 dark:bg-[#0f1117] p-1.5 rounded-lg border border-gray-200 dark:border-[#1e2535]">
                    <code className="text-sm text-gray-700 dark:text-gray-300 font-mono px-3 whitespace-nowrap">npm install @agentium/sdk</code>
                    <button
                        className="p-1.5 text-gray-700 hover:text-blue-700 dark:text-gray-300 dark:hover:text-gray-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded transition-colors"
                        onClick={() => copyToClipboard('npm install @agentium/sdk', 'ts-install')}
                        title="Copy install command" aria-label="Copy install command"
                    >
                        {copiedStates['ts-install'] ? <Check className="w-4 h-4 text-green-700" /> : <Copy className="w-4 h-4" />}
                    </button>
                </div>
              </div>
              <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-300 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(TS_SAMPLE, 'ts-code')}
                          title="Copy Code" aria-label="Copy Code"
                      >
                          {copiedStates['ts-code'] ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
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
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-4">
                  <TerminalSquare className="w-5 h-5 text-blue-600" /> cURL Examples
              </h2>
              <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-300 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(CURL_SAMPLE, 'curl-code')}
                          title="Copy Code" aria-label="Copy Code"
                      >
                          {copiedStates['curl-code'] ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
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
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <Webhook className="w-5 h-5 text-purple-600" /> Event Types
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-300 mb-6 leading-relaxed">
                  Register webhook subscriptions to receive real-time event
                  notifications. Each event is delivered as a POST request with an
                  HMAC-SHA256 signature in the <code className="text-purple-600 dark:text-purple-400 font-mono bg-purple-50 dark:bg-purple-500/10 px-1 py-0.5 rounded">X-Agentium-Signature</code> header.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {WEBHOOK_EVENTS.map((ev) => (
                    <div key={ev.event} className="bg-gray-50 dark:bg-[#161b27] rounded-lg p-4 border border-gray-200 dark:border-[#1e2535] flex flex-col gap-1.5 hover:border-purple-200 dark:hover:border-purple-500/30 transition-colors">
                      <code className="text-sm text-purple-700 dark:text-purple-400 font-semibold font-mono">
                          {ev.event}
                      </code>
                      <span className="text-sm text-gray-600 dark:text-gray-300">
                        {ev.desc}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Lock className="w-5 h-5 text-gray-600" /> Verifying Signatures
                    </h2>
                </div>
                <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                          className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-300 hover:text-white rounded-lg shadow-sm transition-colors"
                          onClick={() => copyToClipboard(`import hmac, hashlib

def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Verify Agentium webhook signature."""
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)`, 'verify-code')}
                          title="Copy Code" aria-label="Copy Code"
                      >
                          {copiedStates['verify-code'] ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
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

          {/* API Keys tab */}
          {activeTab === 'api-keys' && (
            <div className="space-y-6">
              {/* Success banner after key creation */}
              {createdKeyId && (
                <div className="bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/30 rounded-xl p-4 flex items-start gap-3">
                  <Shield className="w-5 h-5 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-green-800 dark:text-green-300">API key created successfully</p>
                    <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                      Key ID: <code className="font-mono bg-green-100 dark:bg-green-500/20 px-1 py-0.5 rounded">{createdKeyId}</code>
                    </p>
                  </div>
                  <button
                    className="text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-200 transition-colors"
                    onClick={() => setCreatedKeyId(null)}
                    aria-label="Dismiss"
                  >
                    ×
                  </button>
                </div>
              )}

              {/* Header + actions */}
              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                      <Key className="w-5 h-5 text-blue-600" /> API Keys
                    </h2>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      Generate and manage API keys for programmatic access to the Agentium platform.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      className="px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-[#1e2535] border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors flex items-center gap-1.5"
                      onClick={loadKeys}
                      disabled={keysLoading}
                      aria-label="Refresh keys"
                    >
                      <RefreshCw className={`w-4 h-4 ${keysLoading ? 'animate-spin' : ''}`} />
                      Refresh
                    </button>
                    <button
                      className="px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors flex items-center gap-1.5 shadow-sm"
                      onClick={() => setShowCreateForm(!showCreateForm)}
                      id="generate-api-key-btn"
                    >
                      <Plus className="w-4 h-4" />
                      Generate New Key
                    </button>
                  </div>
                </div>

                {/* Create key form */}
                {showCreateForm && (
                  <form onSubmit={handleCreateKey} className="bg-gray-50 dark:bg-[#0f1117] rounded-xl border border-gray-200 dark:border-[#1e2535] p-5 mb-6 space-y-4">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                      <Shield className="w-4 h-4 text-blue-600" /> New API Key
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Provider */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Provider</label>
                        <select
                          className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                          value={formData.provider}
                          onChange={e => setFormData(prev => ({ ...prev, provider: e.target.value }))}
                          id="create-key-provider"
                        >
                          {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                      </div>

                      {/* Config name */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Config Name</label>
                        <input
                          type="text"
                          className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                          placeholder="e.g. Production GPT-4o"
                          value={formData.config_name}
                          onChange={e => setFormData(prev => ({ ...prev, config_name: e.target.value }))}
                          required
                          id="create-key-config-name"
                        />
                      </div>

                      {/* Model name */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Default Model</label>
                        <input
                          type="text"
                          className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                          placeholder="e.g. gpt-4o, claude-sonnet-4-20250514"
                          value={formData.model_name}
                          onChange={e => setFormData(prev => ({ ...prev, model_name: e.target.value }))}
                          required
                          id="create-key-model"
                        />
                      </div>

                      {/* API Key */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">API Key</label>
                        <div className="relative">
                          <input
                            type={showApiKey ? 'text' : 'password'}
                            className="w-full px-3 py-2 pr-10 text-sm rounded-lg border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors font-mono"
                            placeholder="sk-..."
                            value={formData.api_key}
                            onChange={e => setFormData(prev => ({ ...prev, api_key: e.target.value }))}
                            required
                            minLength={10}
                            id="create-key-api-key"
                          />
                          <button
                            type="button"
                            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                            onClick={() => setShowApiKey(!showApiKey)}
                            aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                          >
                            {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>

                      {/* Budget */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Monthly Budget (USD)</label>
                        <input
                          type="number"
                          className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                          placeholder="0 = unlimited"
                          value={formData.monthly_budget_usd || ''}
                          onChange={e => setFormData(prev => ({ ...prev, monthly_budget_usd: parseFloat(e.target.value) || 0 }))}
                          min={0}
                          step={0.01}
                          id="create-key-budget"
                        />
                      </div>

                      {/* Priority */}
                      <div>
                        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1.5">Priority (lower = higher)</label>
                        <input
                          type="number"
                          className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-[#2a3347] bg-white dark:bg-[#161b27] text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-colors"
                          value={formData.priority || 1}
                          onChange={e => setFormData(prev => ({ ...prev, priority: parseInt(e.target.value) || 1 }))}
                          min={1}
                          id="create-key-priority"
                        />
                      </div>
                    </div>

                    {/* Default checkbox */}
                    <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        className="rounded border-gray-300 dark:border-[#2a3347] text-blue-600 focus:ring-blue-500"
                        checked={formData.is_default}
                        onChange={e => setFormData(prev => ({ ...prev, is_default: e.target.checked }))}
                        id="create-key-default"
                      />
                      Set as default configuration for this provider
                    </label>

                    {createError && (
                      <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-lg px-3 py-2">
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                        {createError}
                      </div>
                    )}

                    <div className="flex items-center gap-3 pt-2">
                      <button
                        type="submit"
                        disabled={creating || !formData.api_key || !formData.config_name || !formData.model_name}
                        className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors shadow-sm flex items-center gap-1.5"
                        id="create-key-submit"
                      >
                        {creating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
                        {creating ? 'Creating...' : 'Create Key'}
                      </button>
                      <button
                        type="button"
                        className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                        onClick={() => { setShowCreateForm(false); setCreateError(null); }}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}

                {/* Keys list */}
                {keysError && (
                  <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-lg px-4 py-3 mb-4">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    {keysError}
                  </div>
                )}

                {keysLoading && keys.length === 0 ? (
                  <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                    <p className="text-sm">Loading keys…</p>
                  </div>
                ) : keys.length === 0 ? (
                  <div className="text-center py-12">
                    <Key className="w-8 h-8 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                    <p className="text-sm text-gray-500 dark:text-gray-400">No API keys configured yet.</p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Click "Generate New Key" to create your first key.</p>
                  </div>
                ) : (
                  <div className="divide-y divide-gray-100 dark:divide-[#1e2535]">
                    {keys.map((k) => (
                      <div key={k.id} className="py-3.5 flex flex-col sm:flex-row sm:items-center gap-3 hover:bg-gray-50 dark:hover:bg-[#0f1117] -mx-4 px-4 transition-colors rounded-lg group">
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold font-mono ${getStatusClasses(k.status)}`}>
                            {k.status}
                          </span>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-900 dark:text-white">{k.provider}</span>
                              <code className="text-xs text-gray-500 dark:text-gray-400 font-mono bg-gray-100 dark:bg-[#0f1117] px-1.5 py-0.5 rounded border border-gray-200 dark:border-[#2a3347] truncate max-w-[200px]">
                                {k.id}
                              </code>
                              <button
                                className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-all"
                                onClick={() => copyToClipboard(k.id, `key-${k.id}`)}
                                title="Copy key ID" aria-label="Copy key ID"
                              >
                                {copiedStates[`key-${k.id}`] ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                            <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                              <span>Priority: {k.priority}</span>
                              <span>Budget: ${k.monthly_budget_usd === 0 ? '∞' : k.monthly_budget_usd.toFixed(2)}</span>
                              <span>Spent: ${k.current_spend_usd.toFixed(2)}</span>
                              {k.budget_remaining_pct < 100 && k.monthly_budget_usd > 0 && (
                                <span className={k.budget_remaining_pct < 20 ? 'text-red-500' : 'text-yellow-500'}>
                                  {k.budget_remaining_pct.toFixed(0)}% remaining
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                        <button
                          className="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-all"
                          onClick={() => handleDeleteKey(k.id)}
                          title="Delete key" aria-label="Delete key"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Usage instructions */}
              <div className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm p-6">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                    <Lock className="w-5 h-5 text-blue-600" /> Using Your API Key
                </h2>
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
                  Include your API key in the <code className="text-blue-600 dark:text-blue-400 font-mono bg-blue-50 dark:bg-blue-500/10 px-1 py-0.5 rounded">X-API-Key</code> header
                  or use JWT-based authentication via the <code className="text-blue-600 dark:text-blue-400 font-mono bg-blue-50 dark:bg-blue-500/10 px-1 py-0.5 rounded">Authorization: Bearer &lt;token&gt;</code> header.
                </p>
                <div className="relative group rounded-xl overflow-hidden border border-gray-200 dark:border-[#1e2535] bg-[#0d1117]">
                  <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      className="p-2 bg-[#161b27] border border-[#2a3347] text-gray-300 hover:text-white rounded-lg shadow-sm transition-colors"
                      onClick={() => copyToClipboard(`curl -s -H "X-API-Key: sk-your-key" \\
  http://localhost:8000/api/v1/agents | jq`, 'usage-curl')}
                      title="Copy Code" aria-label="Copy Code"
                    >
                      {copiedStates['usage-curl'] ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  <pre className="p-4 text-sm text-[#c9d1d9] font-mono overflow-auto leading-relaxed">
                    <code>{`# Authenticate with API key header
curl -s -H "X-API-Key: sk-your-key" \\
  http://localhost:8000/api/v1/agents | jq

# Or use JWT Bearer token
curl -s -H "Authorization: Bearer <token>" \\
  http://localhost:8000/api/v1/agents | jq`}</code>
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
