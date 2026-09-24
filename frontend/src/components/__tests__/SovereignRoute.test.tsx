// frontend/src/components/__tests__/SovereignRoute.test.tsx
// 12.4.2 artifact: SovereignRoute enforces sovereign access —
// sovereign stays, non-sovereign → "/", unauthenticated → "/login".
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach } from 'vitest';
import { SovereignRoute } from '@/components/SovereignRoute';
import { useAuthStore } from '@/store/authStore';

function renderAt(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route
                    path="/sovereign"
                    element={<SovereignRoute><div>SOVEREIGN CONTENT</div></SovereignRoute>}
                />
                <Route path="/login" element={<div>LOGIN PAGE</div>} />
                <Route path="/" element={<div>MAIN DASHBOARD</div>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe('SovereignRoute', () => {
    beforeEach(() => {
        useAuthStore.setState({ user: null, isLoading: false });
    });

    it('renders children for a sovereign user', () => {
        useAuthStore.setState({
            user: { isAuthenticated: true, username: 'admin', is_admin: true, isSovereign: true } as never,
        });
        renderAt('/sovereign');
        expect(screen.getByText('SOVEREIGN CONTENT')).toBeInTheDocument();
    });

    it('redirects non-sovereign users to /', () => {
        useAuthStore.setState({
            user: { isAuthenticated: true, username: 'user', is_admin: false, isSovereign: false } as never,
        });
        renderAt('/sovereign');
        expect(screen.getByText('MAIN DASHBOARD')).toBeInTheDocument();
        expect(screen.queryByText('SOVEREIGN CONTENT')).not.toBeInTheDocument();
    });

    it('redirects unauthenticated users to /login', () => {
        renderAt('/sovereign');
        expect(screen.getByText('LOGIN PAGE')).toBeInTheDocument();
        expect(screen.queryByText('SOVEREIGN CONTENT')).not.toBeInTheDocument();
    });
});
