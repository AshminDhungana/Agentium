import React, { useState, useEffect, useCallback } from 'react';
import {
    Webhook,
    Plus,
    Trash2,
    Play,
    Pause,
    Activity,
    CheckCircle,
    XCircle,
    TerminalSquare,
    FileText,
    AlertCircle,
    Clock,
    X
} from 'lucide-react';
import {
  listWebhookSubscriptions,
  createWebhookSubscription,
  updateWebhookSubscription,
  deleteWebhookSubscription,
  getWebhookDeliveries,
  testWebhook,
  listSupportedEvents,
  WebhookSubscription,
  WebhookDelivery,
} from '../services/webhookService';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

const WebhookManagementPage: React.FC = () => {
  const [subscriptions, setSubscriptions] = useState<WebhookSubscription[]>([]);
  const [supportedEvents, setSupportedEvents] = useState<string[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedSub, setSelectedSub] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);

  // Form state
  const [formUrl, setFormUrl] = useState('');
  const [formEvents, setFormEvents] = useState<string[]>([]);
  const [formDescription, setFormDescription] = useState('');

  const loadSubscriptions = useCallback(async () => {
    try {
      setLoading(true);
      const [subs, events] = await Promise.all([
        listWebhookSubscriptions(),
        listSupportedEvents(),
      ]);
      setSubscriptions(subs);
      setSupportedEvents(events);
    } catch (err) {
      console.error('Failed to load webhooks:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubscriptions();
  }, [loadSubscriptions]);

  const handleCreate = async () => {
    if (!formUrl || formEvents.length === 0) return;
    try {
      const sub = await createWebhookSubscription({
        url: formUrl,
        events: formEvents,
        description: formDescription || undefined,
      });
      setCreatedSecret(sub.secret || null);
      setShowCreate(false);
      setFormUrl('');
      setFormEvents([]);
      setFormDescription('');
      await loadSubscriptions();
    } catch (err) {
      console.error('Failed to create webhook:', err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this webhook subscription?')) return;
    try {
      await deleteWebhookSubscription(id);
      await loadSubscriptions();
      if (selectedSub === id) setSelectedSub(null);
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const handleToggle = async (sub: WebhookSubscription) => {
    try {
      await updateWebhookSubscription(sub.id, { is_active: !sub.is_active });
      await loadSubscriptions();
    } catch (err) {
      console.error('Failed to toggle:', err);
    }
  };

  const handleTest = async (id: string) => {
    try {
      const result = await testWebhook(id);
      alert(`Test ${result.status}: HTTP ${result.status_code || 'N/A'}${result.error ? ` — ${result.error}` : ''}`);
      if (selectedSub === id) await loadDeliveries(id);
    } catch (err) {
      console.error('Test failed:', err);
    }
  };

  const loadDeliveries = async (subId: string) => {
    try {
      const d = await getWebhookDeliveries(subId);
      setDeliveries(d);
      setSelectedSub(subId);
    } catch (err) {
      console.error('Failed to load deliveries:', err);
    }
  };

  const toggleEvent = (event: string) => {
    setFormEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  };

  if (loading) {
      return (
          <div className="flex flex-col items-center justify-center p-16">
              <LoadingSpinner size="lg" />
              <p className="text-sm text-gray-500 dark:text-gray-400">Loading webhooks...</p>
          </div>
      );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* ── Page Header ─────────────────────────────────────────────── */}
      <div className="mb-8">
          <div className="flex items-center gap-3 mb-1">
              <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-600 to-blue-600 dark:from-purple-400 dark:to-blue-400">
                  Webhook Management
              </h1>
          </div>
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            Manage outbound event webhooks. Agentium will POST events to your
            endpoints with HMAC-SHA256 signed payloads.
          </p>
      </div>

      {/* Created secret alert */}
      {createdSecret && (
        <div className="bg-yellow-50 dark:bg-yellow-500/10 border border-yellow-200 dark:border-yellow-500/20 rounded-xl p-4 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-yellow-800 dark:text-yellow-400 font-medium">
                <AlertCircle className="w-5 h-5"/>
                <span>Save your webhook secret — it won't be shown again:</span>
            </div>
            <code className="bg-yellow-100 dark:bg-yellow-500/20 px-3 py-2 rounded-lg text-yellow-900 dark:text-yellow-200 font-mono break-all text-sm">
                {createdSecret}
            </code>
            <button
                className="self-start mt-2 px-3 py-1.5 text-xs font-medium bg-yellow-100 hover:bg-yellow-200 dark:bg-yellow-500/20 dark:hover:bg-yellow-500/30 text-yellow-800 dark:text-yellow-400 rounded-lg transition-colors duration-150"
                onClick={() => setCreatedSecret(null)}
            >
                Dismiss
            </button>
        </div>
      )}

      {/* Actions bar */}
      <div className="flex items-center justify-between">
        <button
          className={`px-4 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 flex items-center gap-2 shadow-sm ${
            showCreate 
              ? 'bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347]' 
              : 'bg-purple-600 hover:bg-purple-700 dark:hover:bg-purple-500 text-white'
          }`}
          onClick={() => setShowCreate(!showCreate)}
        >
          {showCreate ? (
            <>
                <X className="w-4 h-4" /> Cancel
            </>
          ) : (
            <>
                <Plus className="w-4 h-4" /> New Webhook
            </>
          )}
        </button>
        <span className="text-gray-500 dark:text-gray-400 text-sm">
          {subscriptions.length} subscription{subscriptions.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-white dark:bg-[#161b27] rounded-xl border border-purple-200 dark:border-purple-500/20 shadow-sm dark:shadow-[0_2px_16px_rgba(0,0,0,0.25)] p-6 transition-colors duration-200">
          <h3 className="text-lg font-semibold text-purple-600 dark:text-purple-400 mb-4 flex items-center gap-2">
            <Webhook className="w-5 h-5" />
            New Webhook Subscription
          </h3>
          <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Endpoint URL</label>
                <input
                  className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                  type="url"
                  placeholder="https://your-server.com/webhook"
                  value={formUrl}
                  onChange={(e) => setFormUrl(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Description (optional)</label>
                <input
                  className="w-full px-4 py-2.5 border border-gray-200 dark:border-[#1e2535] rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500 bg-gray-50 dark:bg-[#0f1117] text-gray-900 dark:text-white text-sm transition-colors duration-150 outline-none"
                  placeholder="e.g., Production task notifications"
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Events</label>
                <div className="flex flex-wrap gap-2">
                  {supportedEvents.map((event) => {
                      const isSelected = formEvents.includes(event);
                      return (
                        <button
                          key={event}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors duration-150 flex items-center gap-1.5 ${
                              isSelected
                                ? 'bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/30'
                                : 'bg-gray-100 dark:bg-[#1e2535] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-[#2a3347] hover:bg-gray-200 dark:hover:bg-[#2a3347]'
                          }`}
                          onClick={() => toggleEvent(event)}
                        >
                          {isSelected && <CheckCircle className="w-3 h-3" />}
                          {event}
                        </button>
                      );
                  })}
                </div>
              </div>
              <div className="pt-2">
                  <button
                    className="px-4 py-2.5 bg-purple-600 hover:bg-purple-700 dark:hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors duration-150 shadow-sm flex items-center gap-2"
                    onClick={handleCreate}
                    disabled={!formUrl || formEvents.length === 0}
                  >
                    <Plus className="w-4 h-4"/>
                    Create Webhook
                  </button>
              </div>
          </div>
        </div>
      )}

      {/* Subscriptions list */}
      <div className="flex flex-col gap-4">
        {subscriptions.map((sub) => (
          <div key={sub.id} className="bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm hover:border-gray-300 dark:hover:border-[#2a3347] transition-all duration-150 p-6 object-contain overflow-hidden flex flex-col gap-4">
            <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 text-xs font-medium rounded-full border ${
                        sub.is_active 
                            ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20'
                            : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20'
                    }`}
                  >
                    {sub.is_active ? 'Active' : 'Paused'}
                  </span>
                  <span className="font-mono text-sm text-gray-600 dark:text-gray-400 break-all bg-gray-50 dark:bg-[#0f1117] px-2 py-0.5 rounded border border-gray-100 dark:border-[#1e2535]">
                    {sub.url}
                  </span>
                </div>
                {sub.description && (
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {sub.description}
                  </p>
                )}
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {(sub.events || []).map((evt) => (
                    <span key={evt} className="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md bg-blue-100 text-blue-700 border border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20">
                      {evt}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                <button
                  className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                  onClick={() => handleTest(sub.id)}
                  title="Send test event"
                >
                  <Activity className="w-3.5 h-3.5"/> Test
                </button>
                <button
                  className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                  onClick={() => handleToggle(sub)}
                >
                  {sub.is_active ? <><Pause className="w-3.5 h-3.5"/> Pause</> : <><Play className="w-3.5 h-3.5"/> Resume</>}
                </button>
                <button
                  className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 dark:bg-[#1e2535] dark:hover:bg-[#2a3347] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-[#2a3347] rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                  onClick={() => loadDeliveries(sub.id)}
                >
                  <FileText className="w-3.5 h-3.5"/> Logs
                </button>
                <button
                  className="px-3 py-1.5 text-xs font-medium bg-red-50 hover:bg-red-100 dark:bg-red-500/10 dark:hover:bg-red-500/20 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/20 rounded-lg transition-colors duration-150 flex items-center gap-1.5"
                  onClick={() => handleDelete(sub.id)}
                >
                  <Trash2 className="w-3.5 h-3.5" /> Delete
                </button>
              </div>
            </div>

            {/* Delivery logs (expanded) */}
            {selectedSub === sub.id && (
              <div className="mt-2 pt-4 border-t border-gray-100 dark:border-[#1e2535]">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                  Recent Deliveries
                </h4>
                {deliveries.length === 0 ? (
                  <div className="bg-gray-50 dark:bg-[#0f1117] rounded-lg p-4 text-center border border-gray-200 dark:border-[#1e2535]">
                     <p className="text-sm text-gray-500 dark:text-gray-400">No deliveries yet.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                      {deliveries.slice(0, 20).map((d) => (
                        <div key={d.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-200 dark:border-[#1e2535] text-sm">
                          <div className="flex items-center gap-3">
                            <span className={`w-2 h-2 rounded-full shrink-0 ${d.delivered_at ? 'bg-green-500' : 'bg-red-500'}`} />
                            <span className="font-mono text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400">
                                {d.event_type}
                            </span>
                            <span className={`font-medium ${d.delivered_at ? 'text-gray-600 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400'}`}>
                              {d.status_code ? `HTTP ${d.status_code}` : 'Pending'}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 mt-2 sm:mt-0 text-xs">
                            <span className="text-gray-500 dark:text-gray-400">
                              Attempts: {d.attempts}/{d.max_attempts}
                            </span>
                            {d.error && (
                              <span className="text-red-500 dark:text-red-400 max-w-[200px] truncate" title={d.error}>
                                  {d.error}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
                <div className="mt-4 flex justify-end">
                    <button
                        className="px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                        onClick={() => setSelectedSub(null)}
                    >
                        Close Logs
                    </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {subscriptions.length === 0 && !showCreate && (
        <div className="text-center py-16 bg-white dark:bg-[#161b27] rounded-xl border border-gray-200 dark:border-[#1e2535] shadow-sm">
            <div className="w-14 h-14 bg-purple-100 dark:bg-purple-500/10 border border-purple-200 dark:border-purple-500/20 rounded-xl flex items-center justify-center mx-auto mb-4">
                <Webhook className="w-6 h-6 text-purple-600 dark:text-purple-400" />
            </div>
            <p className="text-gray-900 dark:text-white font-medium mb-1">
                No webhook subscriptions yet
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
                Create one to receive real-time event notifications.
            </p>
        </div>
      )}
    </div>
  );
};

export default WebhookManagementPage;
