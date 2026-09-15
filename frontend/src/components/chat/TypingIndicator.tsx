import React, { useEffect, useState } from 'react';
import styles from './TypingIndicator.module.css';

interface TypingIndicatorProps {
    thinking?: boolean;
    toolCount?: number;
    toolNames?: string[];
}

export function TypingIndicator({ thinking = false, toolCount = 0, toolNames = [] }: TypingIndicatorProps) {
    const [displayText, setDisplayText] = useState('');
    const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

    useEffect(() => {
        if (toolNames.length > 0) {
            const truncated = toolNames.slice(0, 3).join(', ');
            const suffix = toolNames.length > 3 ? ` +${toolNames.length - 3} more` : '';
            setDisplayText(`🔧 Running: ${truncated}${suffix}`);
        } else if (toolCount > 0) {
            setDisplayText(`🔧 Running tools: ${toolCount}`);
        } else if (thinking) {
            setDisplayText('💭 Thinking...');
        } else {
            setDisplayText('');
        }
    }, [toolNames, toolCount, thinking]);

    useEffect(() => {
        const media = window.matchMedia('(prefers-reduced-motion: reduce)');
        setPrefersReducedMotion(media.matches);
        const listener = () => setPrefersReducedMotion(media.matches);
        media.addEventListener('change', listener);
        return () => media.removeEventListener('change', listener);
    }, []);

    if (!displayText && !thinking && toolCount === 0) {
        return (
            <div className={styles.container} data-testid="typing-dots" aria-hidden="true">
                <span className={styles.dot}></span>
                <span className={styles.dot}></span>
                <span className={styles.dot}></span>
            </div>
        );
    }

    return (
        <div className={styles.container} role="status" aria-live="polite">
            <span className={styles.icon}>{thinking && toolCount === 0 ? '💭' : '🔧'}</span>
            <span className={styles.text}>{displayText}</span>
            {!prefersReducedMotion && thinking && toolCount === 0 && (
                <span className={styles.dots} aria-hidden="true">
                    <span className={styles.dot}></span>
                    <span className={styles.dot}></span>
                    <span className={styles.dot}></span>
                </span>
            )}
        </div>
    );
}