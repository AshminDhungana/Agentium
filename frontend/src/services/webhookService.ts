/**
 * Frontend service for managing outbound webhook subscriptions.
 */

import { api } from './api';

export interface WebhookSubscription {
  id: string;
  url: string;
  events: string[];
  description?: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  secret?: string;
}

export interface WebhookDelivery {
  id: string;
  subscription_id: string;
  delivery_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  status_code?: number;
  attempts: number;
  max_attempts: number;
  delivered_at?: string;
  next_retry_at?: string;
  failed_at?: string;
  error?: string;
  created_at?: string;
}

export interface CreateWebhookParams {
  url: string;
  events: string[];
  secret?: string;
  description?: string;
}

export interface UpdateWebhookParams {
  url?: string;
  events?: string[];
  description?: string;
  is_active?: boolean;
}

// ═══════════════════════════════════════════════════════════
// API Calls
// ═══════════════════════════════════════════════════════════

export const listWebhookSubscriptions = async (): Promise<WebhookSubscription[]> => {
  const { data } = await api.get('/webhooks/subscriptions');
  return data.subscriptions || [];
};

export const getWebhookSubscription = async (id: string): Promise<WebhookSubscription> => {
  const { data } = await api.get(`/webhooks/subscriptions/${id}`);
  return data;
};

export const createWebhookSubscription = async (params: CreateWebhookParams): Promise<WebhookSubscription> => {
  const { data } = await api.post('/webhooks/subscriptions', params);
  return data;
};

export const updateWebhookSubscription = async (
  id: string,
  params: UpdateWebhookParams,
): Promise<WebhookSubscription> => {
  const { data } = await api.put(`/webhooks/subscriptions/${id}`, params);
  return data;
};

export const deleteWebhookSubscription = async (id: string): Promise<void> => {
  await api.delete(`/webhooks/subscriptions/${id}`);
};

export const getWebhookDeliveries = async (
  subscriptionId: string,
  limit = 50,
): Promise<WebhookDelivery[]> => {
  const { data } = await api.get(`/webhooks/subscriptions/${subscriptionId}/deliveries`, {
    params: { limit },
  });
  return data.deliveries || [];
};

export const testWebhook = async (
  subscriptionId: string,
): Promise<{ status: string; delivery_id: string; status_code?: number; error?: string }> => {
  const { data } = await api.post(`/webhooks/subscriptions/${subscriptionId}/test`);
  return data;
};

export const listSupportedEvents = async (): Promise<string[]> => {
  const { data } = await api.get('/webhooks/events');
  return data.events || [];
};
