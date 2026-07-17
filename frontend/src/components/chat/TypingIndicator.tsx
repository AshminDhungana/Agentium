/**
 * TypingIndicator.tsx
 *
 * Three animated dots shown while the Head of Council is "thinking" (the
 * streaming placeholder exists but no delta has arrived yet). Theme-consistent
 * with the rest of the chat bubbles.
 */
export function TypingIndicator() {
    return (
        <div
            data-testid="typing-indicator"
            aria-hidden
            className="flex items-center gap-1.5"
        >
            <span className="w-2 h-2 rounded-full bg-gray-400 motion-safe:animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-2 h-2 rounded-full bg-gray-400 motion-safe:animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-2 h-2 rounded-full bg-gray-400 motion-safe:animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
    );
}
