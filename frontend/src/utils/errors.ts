/**
 * frontend/src/utils/errors.ts
 *
 * Shared error-normalisation utilities.
 * Replaces `catch (err: any)` patterns with typed, consistent error extraction
 * across all pages and hooks.
 */

/**
 * Extracts a human-readable message from any thrown value.
 *
 * Priority order:
 *  1. Axios response body  → response.data.detail  (FastAPI validation errors)
 *  2. Standard Error       → err.message
 *  3. Plain string throws  → returned as-is
 *  4. Everything else      → generic fallback
 *
 * @example
 * } catch (err: unknown) {
 *   showToast.error(getErrorMessage(err));
 * }
 */
export function getErrorMessage(err: unknown): string {
    if (err === null || err === undefined) return 'An unknown error occurred';

    if (typeof err === 'string') return err;

    // Axios-style errors: err.response.data.detail (FastAPI standard format)
    if (typeof err === 'object') {
        const obj = err as Record<string, unknown>;

        // Try response.data.detail first (Axios + FastAPI)
        if (obj.response && typeof obj.response === 'object') {
            const resp = obj.response as Record<string, unknown>;
            if (resp.data && typeof resp.data === 'object') {
                const data = resp.data as Record<string, unknown>;
                if (typeof data.detail === 'string') return data.detail;
            }
        }

        // Fall back to .message (standard Error / Axios)
        if (typeof obj.message === 'string' && obj.message.length > 0) {
            return obj.message;
        }
    }

    return 'An unknown error occurred';
}