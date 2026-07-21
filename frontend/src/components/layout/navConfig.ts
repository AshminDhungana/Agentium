import {
  LayoutDashboard, Crown, Users, ClipboardList, Activity,
  Gavel, BookOpen, Cpu, Radio, Inbox, FlaskConical,
  Settings, Shield, Mic,
} from 'lucide-react';
import type { ComponentType } from 'react';

export type NavVariant = 'default' | 'danger';

export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  badge?: number;
  variant?: NavVariant;
  adminOnly?: boolean;
}

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

export const PAGE_LABELS: Record<string, string> = {
  '/': 'Dashboard',
  '/chat': 'Command Interface',
  '/agents': 'Agents',
  '/tasks': 'Tasks',
  '/monitoring': 'Monitoring',
  '/voting': 'Voting',
  '/constitution': 'Constitution',
  '/models': 'Models',
  '/channels': 'Channels',
  '/message-log': 'Message Log',
  '/ab-testing': 'A/B Testing',
  '/settings': 'Settings',
  '/voice-bridge': 'Voice Bridge',
  '/sovereign': 'Sovereign Control',
};

export function getPageTitle(pathname: string): string {
  if (PAGE_LABELS[pathname]) return PAGE_LABELS[pathname];
  const prefix = Object.keys(PAGE_LABELS)
    .filter((p) => p !== '/' && pathname.startsWith(p))
    .sort((a, b) => b.length - a.length)[0];
  return prefix ? PAGE_LABELS[prefix] : 'Agentium';
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'workspace',
    label: 'Workspace',
    items: [
      { path: '/', label: 'Dashboard', icon: LayoutDashboard },
      { path: '/chat', label: 'Command Interface', icon: Crown },
      { path: '/agents', label: 'Agents', icon: Users },
      { path: '/tasks', label: 'Tasks', icon: ClipboardList },
    ],
  },
  {
    id: 'governance',
    label: 'Governance',
    items: [
      { path: '/voting', label: 'Voting', icon: Gavel },
      { path: '/constitution', label: 'Constitution', icon: BookOpen },
      { path: '/monitoring', label: 'Monitoring', icon: Activity },
    ],
  },
  {
    id: 'integrations',
    label: 'Integrations',
    items: [
      { path: '/models', label: 'Models', icon: Cpu },
      { path: '/channels', label: 'Channels', icon: Radio },
      { path: '/message-log', label: 'Message Log', icon: Inbox },
    ],
  },
  {
    id: 'voice',
    label: 'Voice',
    items: [
      { path: '/voice-bridge', label: 'Voice Bridge', icon: Mic },
    ],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      { path: '/ab-testing', label: 'A/B Testing', icon: FlaskConical, adminOnly: true },
      { path: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export const SOVEREIGN_ITEM: NavItem = {
  path: '/sovereign',
  label: 'Sovereign Control',
  icon: Shield,
  variant: 'danger',
};

export function getVisibleGroups(isAdmin: boolean): NavGroup[] {
  return NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.adminOnly || isAdmin),
  }));
}

export function getAllVisibleItems(isAdmin: boolean): NavItem[] {
  const items = getVisibleGroups(isAdmin).flatMap((g) => g.items);
  if (isAdmin) items.push(SOVEREIGN_ITEM);
  return items;
}
