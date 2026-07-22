import { describe, it, expect } from 'vitest';
import {
  getPageTitle,
  getVisibleGroups,
  getAllVisibleItems,
  NAV_GROUPS,
  PAGE_LABELS,
} from '../navConfig';

describe('navConfig', () => {
  it('returns the exact label for a known path', () => {
    expect(getPageTitle('/agents')).toBe('Agents');
    expect(getPageTitle('/')).toBe('Dashboard');
  });

  it('falls back to "Agentium" for a path with no nav entry', () => {
    expect(getPageTitle('/workflows/123')).toBe('Agentium');
  });

  it('lists every non-admin nav item exactly once, in order', () => {
    const paths = getAllVisibleItems(false).map((i) => i.path);
    expect(paths).toEqual([
      '/', '/chat', '/agents', '/tasks',
      '/voting', '/constitution', '/monitoring',
      '/models', '/channels', '/message-log',
      '/voice-bridge',
      '/settings',
    ]);
  });

  it('appends Sovereign Control only for admins', () => {
    expect(getAllVisibleItems(false).some((i) => i.path === '/sovereign')).toBe(false);
    expect(getAllVisibleItems(true).some((i) => i.path === '/sovereign')).toBe(true);
  });

  it('gates A/B Testing behind admin', () => {
    const nonAdmin = getVisibleGroups(false).flatMap((g) => g.items);
    const admin = getVisibleGroups(true).flatMap((g) => g.items);
    expect(nonAdmin.some((i) => i.path === '/ab-testing')).toBe(false);
    expect(admin.some((i) => i.path === '/ab-testing')).toBe(true);
  });

  it('groups items into Workspace / Governance / Integrations / Voice / System', () => {
    expect(NAV_GROUPS.map((g) => g.id)).toEqual([
      'workspace', 'governance', 'integrations', 'voice', 'system',
    ]);
  });

  it('exposes a label for every route rendered by App.tsx', () => {
    const routes = ['/', '/chat', '/agents', '/tasks', '/monitoring', '/voting',
      '/constitution', '/models', '/channels', '/message-log', '/ab-testing',
      '/settings', '/sovereign'];
    for (const r of routes) expect(PAGE_LABELS[r]).toBeTruthy();
  });
});
