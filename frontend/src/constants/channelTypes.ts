// src/constants/channelTypes.ts
// ─────────────────────────────────────────────────────────────────────────────
// Static channel-type definitions, colour palette, WhatsApp field configs, and
// status display helpers.  Extracted from ChannelsPage so any other consumer
// (e.g. MessageLogPage, SettingsPage) can import without a circular dep or
// duplicating 150 lines of config.
// ─────────────────────────────────────────────────────────────────────────────

import type { FC } from 'react';
import {
    Smartphone, Slack, Mail, MessageCircle, Radio,
    Hash, Globe, Users, Send, Grid,
} from 'lucide-react';
import type { ChannelTypeSlug } from '@/types';

// ─── Colour palette ───────────────────────────────────────────────────────────

export type ColorKey =
    | 'green' | 'purple' | 'blue' | 'red'  | 'indigo'
    | 'gray'  | 'cyan'   | 'teal' | 'orange' | 'pink' | 'slate';

export const colorMap: Record<ColorKey, { bg: string; darkBg: string; text: string; darkText: string }> = {
    green:  { bg: 'bg-green-100',  darkBg: 'dark:bg-green-500/10',  text: 'text-green-600',  darkText: 'dark:text-green-400'  },
    purple: { bg: 'bg-purple-100', darkBg: 'dark:bg-purple-500/10', text: 'text-purple-600', darkText: 'dark:text-purple-400' },
    blue:   { bg: 'bg-blue-100',   darkBg: 'dark:bg-blue-500/10',   text: 'text-blue-600',   darkText: 'dark:text-blue-400'   },
    red:    { bg: 'bg-red-100',    darkBg: 'dark:bg-red-500/10',    text: 'text-red-600',    darkText: 'dark:text-red-400'    },
    indigo: { bg: 'bg-indigo-100', darkBg: 'dark:bg-indigo-500/10', text: 'text-indigo-600', darkText: 'dark:text-indigo-400' },
    gray:   { bg: 'bg-gray-100',   darkBg: 'dark:bg-gray-500/10',   text: 'text-gray-600',   darkText: 'dark:text-gray-400'   },
    cyan:   { bg: 'bg-cyan-100',   darkBg: 'dark:bg-cyan-500/10',   text: 'text-cyan-600',   darkText: 'dark:text-cyan-400'   },
    teal:   { bg: 'bg-teal-100',   darkBg: 'dark:bg-teal-500/10',   text: 'text-teal-600',   darkText: 'dark:text-teal-400'   },
    orange: { bg: 'bg-orange-100', darkBg: 'dark:bg-orange-500/10', text: 'text-orange-600', darkText: 'dark:text-orange-400' },
    pink:   { bg: 'bg-pink-100',   darkBg: 'dark:bg-pink-500/10',   text: 'text-pink-600',   darkText: 'dark:text-pink-400'   },
    slate:  { bg: 'bg-slate-100',  darkBg: 'dark:bg-slate-500/10',  text: 'text-slate-600',  darkText: 'dark:text-slate-400'  },
};

// ─── Field definition ─────────────────────────────────────────────────────────

export interface ChannelField {
    name: string;
    label: string;
    type: string;
    placeholder: string;
    required?: boolean;
    help?: string;
}

// ─── Channel-type definition ──────────────────────────────────────────────────

export interface ChannelTypeDefinition {
    id: ChannelTypeSlug;
    name: string;
    Icon: FC<{ className?: string }>;
    description: string;
    color: ColorKey;
    fields: ChannelField[];
    note?: string;
    providerSelector?: boolean;
}

// ─── WhatsApp provider field sets ─────────────────────────────────────────────

export const whatsAppCloudFields: ChannelField[] = [
    { name: 'phone_number_id', label: 'Phone Number ID', type: 'text',     placeholder: '123456789012345',   required: true, help: 'From Meta Business Manager'            },
    { name: 'access_token',    label: 'Access Token',    type: 'password', placeholder: 'EAAxxxxx...',       required: true, help: 'Permanent token from Meta'             },
    { name: 'verify_token',    label: 'Verify Token',    type: 'text',     placeholder: 'my_verify_secret',             help: 'Custom secret for webhook verification' },
    { name: 'app_secret',      label: 'App Secret',      type: 'password', placeholder: 'Optional',                     help: 'For webhook signature verification'     },
];

// Web Bridge requires no user-supplied fields; bridge_url/bridge_token are
// injected server-side from env vars when the channel is created.
export const whatsAppBridgeFields: ChannelField[] = [];

// ─── All channel type definitions ─────────────────────────────────────────────

export const channelTypes: ChannelTypeDefinition[] = [
    {
        id: 'whatsapp',
        name: 'WhatsApp',
        Icon: Smartphone,
        description: 'Cloud API or Web Bridge (QR)',
        color: 'green',
        providerSelector: true,
        fields: [],
        note: 'Choose between official Meta Cloud API (business) or Web Bridge (personal/development)',
    },
    {
        id: 'slack',
        name: 'Slack',
        Icon: Slack,
        description: 'Slack Bot API integration',
        color: 'purple',
        fields: [
            { name: 'bot_token',      label: 'Bot Token',      type: 'password', placeholder: 'xoxb-...',   required: true },
            { name: 'signing_secret', label: 'Signing Secret', type: 'password', placeholder: 'abc123...' },
        ],
    },
    {
        id: 'telegram',
        name: 'Telegram',
        Icon: Send,
        description: 'Telegram Bot API',
        color: 'blue',
        fields: [
            { name: 'bot_token', label: 'Bot Token', type: 'password', placeholder: '123456789:ABC-DEF...', required: true },
        ],
    },
    {
        id: 'email',
        name: 'Email (SMTP)',
        Icon: Mail,
        description: 'SMTP send / IMAP receive',
        color: 'red',
        fields: [
            { name: 'smtp_host',  label: 'SMTP Host',  type: 'text',     placeholder: 'smtp.gmail.com',    required: true },
            { name: 'smtp_port',  label: 'Port',       type: 'number',   placeholder: '587'                              },
            { name: 'smtp_user',  label: 'Username',   type: 'email',    placeholder: 'user@domain.com',   required: true },
            { name: 'smtp_pass',  label: 'Password',   type: 'password', placeholder: '••••••••',          required: true },
            { name: 'from_email', label: 'From Email', type: 'email',    placeholder: 'noreply@domain.com'              },
        ],
    },
    {
        id: 'discord',
        name: 'Discord',
        Icon: Hash,
        description: 'Discord Bot API',
        color: 'indigo',
        fields: [
            { name: 'bot_token',      label: 'Bot Token',      type: 'password', placeholder: 'MTIz...',              required: true },
            { name: 'application_id', label: 'Application ID', type: 'text',     placeholder: '123456789012345678'                  },
        ],
    },
    {
        id: 'signal',
        name: 'Signal',
        Icon: Radio,
        description: 'signal-cli JSON-RPC daemon',
        color: 'gray',
        note: 'Requires signal-cli installed and registered on the server.',
        fields: [
            { name: 'number',   label: 'Registered Number', type: 'tel',    placeholder: '+14155552671', required: true },
            { name: 'rpc_host', label: 'RPC Host',           type: 'text',   placeholder: '127.0.0.1'                  },
            { name: 'rpc_port', label: 'RPC Port',           type: 'number', placeholder: '7583'                       },
        ],
    },
    {
        id: 'google_chat',
        name: 'Google Chat',
        Icon: MessageCircle,
        description: 'Google Chat Bot API',
        color: 'cyan',
        fields: [
            { name: 'webhook_url', label: 'Incoming Webhook URL (simple)', type: 'text', placeholder: 'https://chat.googleapis.com/v1/spaces/ ...' },
            { name: 'room_id',     label: 'Default Space/Room ID',         type: 'text', placeholder: 'spaces/AAAAxxxxxxx'                        },
        ],
        note: 'For full two-way: paste Service Account JSON in config after creation.',
    },
    {
        id: 'teams',
        name: 'Microsoft Teams',
        Icon: Users,
        description: 'Teams Incoming Webhook or Bot Framework',
        color: 'teal',
        fields: [
            { name: 'webhook_url',   label: 'Incoming Webhook URL',     type: 'text',     placeholder: 'https://xxxxx.webhook.office.com/webhookb2/ ...' },
            { name: 'tenant_id',     label: 'Tenant ID (Bot only)',     type: 'text',     placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'            },
            { name: 'client_id',     label: 'Client ID (Bot only)',     type: 'text',     placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'            },
            { name: 'client_secret', label: 'Client Secret (Bot only)', type: 'password', placeholder: '••••••••'                                        },
        ],
    },
    {
        id: 'zalo',
        name: 'Zalo',
        Icon: Globe,
        description: 'Zalo Official Account API',
        color: 'orange',
        fields: [
            { name: 'access_token', label: 'OA Access Token', type: 'password', placeholder: 'zalotoken...', required: true },
            { name: 'oa_id',        label: 'OA ID',           type: 'text',     placeholder: '1234567890'                  },
        ],
    },
    {
        id: 'matrix',
        name: 'Matrix',
        Icon: Grid,
        description: 'Matrix Client-Server API',
        color: 'pink',
        fields: [
            { name: 'homeserver_url', label: 'Homeserver URL',  type: 'text',     placeholder: 'https://matrix.org',    required: true },
            { name: 'access_token',   label: 'Access Token',    type: 'password', placeholder: 'syt_...',               required: true },
            { name: 'room_id',        label: 'Default Room ID', type: 'text',     placeholder: '!abcdef:matrix.org'                    },
        ],
    },
    {
        id: 'imessage',
        name: 'iMessage',
        Icon: MessageCircle,
        description: 'macOS only — AppleScript or BlueBubbles',
        color: 'slate',
        note: '⚠️ Requires macOS server with Messages.app (AppleScript) or BlueBubbles.',
        fields: [
            { name: 'backend',     label: 'Backend',          type: 'text',     placeholder: 'applescript  or  bluebubbles' },
            { name: 'bb_url',      label: 'BlueBubbles URL',  type: 'text',     placeholder: 'http://localhost:1234'        },
            { name: 'bb_password', label: 'BlueBubbles Pass', type: 'password', placeholder: '••••••••'                    },
        ],
    },
    {
        id: 'custom',
        name: 'Custom',
        Icon: Globe,
        description: 'Custom webhook integration',
        color: 'gray',
        fields: [
            { name: 'webhook_url', label: 'Webhook URL', type: 'text', placeholder: 'https://api.example.com/webhook', required: true },
        ],
    },
];

// ─── Status display config ────────────────────────────────────────────────────

export const statusConfig: Record<string, { dot: string; badge: string; label: string }> = {
    active:       { dot: 'bg-green-500',  badge: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',     label: 'Active'       },
    connected:    { dot: 'bg-green-500',  badge: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',     label: 'Connected'    },
    disconnected: { dot: 'bg-gray-400',   badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400',         label: 'Disconnected' },
    error:        { dot: 'bg-red-500',    badge: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',             label: 'Error'        },
    pending:      { dot: 'bg-yellow-500', badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/15 dark:text-yellow-400', label: 'Pending'      },
};

export const getStatus = (s: string) =>
    statusConfig[s] ?? { dot: 'bg-gray-400', badge: 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400', label: s };
