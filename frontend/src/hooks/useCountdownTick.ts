/**
 * useCountdownTick
 *
 * Provides a single shared 1-second tick counter via React context.
 * Replaces per-component setInterval calls — with N active voting cards,
 * the old approach created N independent timers. This hook uses one timer
 * shared across all consumers, eliminating the redundancy.
 *
 * Usage:
 *   1. Wrap VotingPage (or a parent) with <CountdownTickProvider>.
 *   2. In any child component call useCountdownTick() to get the current tick.
 *   3. Re-render is triggered on every second only for mounted consumers.
 */

import React, { createContext, useContext, useEffect, useState } from 'react';

// ── Context ───────────────────────────────────────────────────────────────────

const TickContext = createContext<number>(0);

// ── Provider ──────────────────────────────────────────────────────────────────

interface CountdownTickProviderProps {
    children: React.ReactNode;
}

export function CountdownTickProvider({ children }: CountdownTickProviderProps) {
    const [tick, setTick] = useState(0);

    useEffect(() => {
        const id = setInterval(() => setTick(t => t + 1), 1_000);
        return () => clearInterval(id);
    }, []);

    return (
        <TickContext.Provider value={tick}>
            {children}
        </TickContext.Provider>
    );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns the current tick counter (increments every second).
 * Must be used inside a <CountdownTickProvider>.
 */
export function useCountdownTick(): number {
    return useContext(TickContext);
}