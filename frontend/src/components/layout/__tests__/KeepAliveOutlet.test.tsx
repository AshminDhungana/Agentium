import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect } from 'vitest';
import { KeepAliveOutlet } from '../KeepAliveOutlet';

function Shell({ path }: { path: string }) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<KeepAliveOutlet />}>
          <Route index element={<div>Home page</div>} />
          <Route path="other" element={<div>Other page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('KeepAliveOutlet', () => {
  it('mounts the matched child route into the DOM', () => {
    render(<Shell path="/other" />);
    expect(screen.getByText('Other page')).toBeInTheDocument();
  });

  it('mounts the index child route', () => {
    render(<Shell path="/" />);
    expect(screen.getByText('Home page')).toBeInTheDocument();
  });
});
