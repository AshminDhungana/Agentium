import styles from './TypingIndicator.module.css';

export function TypingIndicator({ thinking = false, toolCount }: { thinking?: boolean; toolCount?: number }) {
    return (
        <div data-testid="typing-indicator" aria-hidden className={styles.container}>
            <span className={styles.dot} />
            <span className={styles.dot} />
            <span className={styles.dot} />
            {toolCount != null && toolCount > 0 && (
                <span className={styles.toolCount} key={toolCount}>
                    +{toolCount}
                </span>
            )}
        </div>
    );
}
