import React, { createContext, useContext, useCallback, useRef, useState } from 'react';
import { Agent } from '../types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface DragDropState {
    draggingAgentId: string | null;
    dropTargetId:    string | null;
}

interface DragDropContextValue extends DragDropState {
    draggingAgent:   Agent | null;
    onDragStart:     (agent: Agent) => void;
    onDragEnd:       () => void;
    onDragEnter:     (targetId: string) => void;
    onDragLeave:     (targetId: string) => void;
    onDrop:          (newParentId: string) => void;
}

interface DragDropProviderProps {
    children:     React.ReactNode;
    /**
     * Called when a drop completes onto a valid target.
     * Receives the dragged agent and the new parent's agentium_id.
     */
    onDropCommit: (draggingAgent: Agent, newParentId: string) => void;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const DragDropContext = createContext<DragDropContextValue | null>(null);

export function useDragDrop(): DragDropContextValue {
    const ctx = useContext(DragDropContext);
    if (!ctx) throw new Error('useDragDrop must be used within a DragDropProvider');
    return ctx;
}

// ─── Provider ─────────────────────────────────────────────────────────────────

export const DragDropProvider: React.FC<DragDropProviderProps> = ({
    children,
    onDropCommit,
}) => {
    const [state, setState] = useState<DragDropState>({
        draggingAgentId: null,
        dropTargetId:    null,
    });

    // Ref tracks current dragging agent so drop handler never sees stale closure
    const draggingAgentRef = useRef<Agent | null>(null);

    // Counter correctly handles nested dragenter/dragleave pairs in DOM
    const enterCounter = useRef(0);

    const onDragStart = useCallback((agent: Agent) => {
        if (agent.agent_type === 'head_of_council') return;
        draggingAgentRef.current = agent;
        enterCounter.current = 0;
        setState({ draggingAgentId: agent.agentium_id, dropTargetId: null });
    }, []);

    const onDragEnd = useCallback(() => {
        draggingAgentRef.current = null;
        enterCounter.current = 0;
        setState({ draggingAgentId: null, dropTargetId: null });
    }, []);

    const onDragEnter = useCallback((targetId: string) => {
        const dragging = draggingAgentRef.current;
        if (!dragging || targetId === dragging.agentium_id) return;
        enterCounter.current += 1;
        setState(prev => ({ ...prev, dropTargetId: targetId }));
    }, []);

    const onDragLeave = useCallback((_targetId: string) => {
        enterCounter.current = Math.max(0, enterCounter.current - 1);
        if (enterCounter.current === 0) {
            setState(prev => ({ ...prev, dropTargetId: null }));
        }
    }, []);

    const onDrop = useCallback((newParentId: string) => {
        const dragging = draggingAgentRef.current;
        enterCounter.current = 0;
        // Clear state first so UI snaps back immediately
        draggingAgentRef.current = null;
        setState({ draggingAgentId: null, dropTargetId: null });

        if (!dragging || newParentId === dragging.agentium_id) return;
        onDropCommit(dragging, newParentId);
    }, [onDropCommit]);

    return (
        <DragDropContext.Provider value={{
            ...state,
            draggingAgent: draggingAgentRef.current,
            onDragStart, onDragEnd, onDragEnter, onDragLeave, onDrop,
        }}>
            {children}
        </DragDropContext.Provider>
    );
};