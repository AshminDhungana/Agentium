import { render } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';
import axe from 'axe-core';
import { MainLayout } from '../MainLayout';

vi.mock('@/components/VoiceIndicator', () => ({ VoiceIndicator: () => null }));

function renderMain() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<div>Dashboard page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('MainLayout accessibility', () => {
  it('has no detectable a11y violations (color-contrast disabled under jsdom)', async () => {
    const { container } = renderMain();
    const results = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(results).toHaveNoViolations();
  });
});
