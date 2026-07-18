/**
 * TypingIndicator.tsx
 *
 * Shown while the Head of Council is "thinking" (the streaming placeholder
 * exists but no delta has arrived yet). A soft shimmer — three rounded bars
 * with a gentle gradient sweep — reads as "composing a response" and feels
 * more professional than bouncing dots. Theme-consistent with the chat bubbles.
 * Vanishes the instant the first token renders (handled by ChatPage).
 */
import styles from './TypingIndicator.module.css';

export function TypingIndicator() {
    return (
        <div
            data-testid="typing-indicator"
            aria-hidden
            className={styles.shimmer}
        >
            <span className={styles.bar} />
            <span className={styles.bar} />
            <span className={styles.bar} />
        </div>
    );
}
