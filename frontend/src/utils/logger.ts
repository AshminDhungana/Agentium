/**
 * Production-aware logger.
 * debug/info are no-ops to keep the console clean.
 * warn and error still forward to console so production issues are visible.
 */
const noOp = (...args: unknown[]) => {};

export const logger = {
  debug: (message: string, ...args: unknown[]) => {},
  info: (message: string, ...args: unknown[]) => {},
  warn: (message: string, ...args: unknown[]) => console.warn(message, ...args),
  error: (message: string, ...args: unknown[]) => console.error(message, ...args),
};
