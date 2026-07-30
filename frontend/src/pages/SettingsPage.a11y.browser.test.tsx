// frontend/src/pages/SettingsPage.a11y.browser.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { auditRoute } from '@/test/a11yBrowser';
import { SettingsPage } from '@/pages/SettingsPage';
import { useAuthStore } from '@/store/authStore';
import { useWebSocketStore } from '@/store/websocketStore';

function formatViolations(violations: any[]) {
  return violations.map((v: any) => ({
    id: v.id,
    impact: v.impact,
    description: v.description,
    helpUrl: v.helpUrl,
    nodes: v.nodes.map((n: any) => ({
      html: n.html,
      target: n.target,
      impact: n.impact,
    })),
  }));
}

describe('SettingsPage color-contrast', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { isAuthenticated: true, username: 'test', is_admin: false, isSovereign: false },
      isLoading: false,
    });
    useWebSocketStore.setState({
      connectionPhase: 'active',
      isConnected: true,
      error: null,
      connectionStats: null,
      unreadCount: 0,
      messageHistory: [],
      lastMessage: null,
      genesisJustCompleted: false,
    } as any);
  });

  it('passes in light theme', async () => {
    const result = await auditRoute(<MemoryRouter><SettingsPage /></MemoryRouter>, 'light');
    if (result.violations.length > 0) {
      console.log('=== LIGHT THEME VIOLATIONS ===');
      console.log(JSON.stringify(formatViolations(result.violations), null, 2));
    }
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(<MemoryRouter><SettingsPage /></MemoryRouter>, 'dark');
    if (result.violations.length > 0) {
      console.log('=== DARK THEME VIOLATIONS ===');
      console.log(JSON.stringify(formatViolations(result.violations), null, 2));
    }
    expect(result).toHaveNoViolations();
  });
});