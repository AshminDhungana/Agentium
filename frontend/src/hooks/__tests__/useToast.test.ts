import { describe, it, expect, vi, beforeEach } from 'vitest';
import toast from 'react-hot-toast';
import { showToast, useToast } from '../useToast';

// Mock react-hot-toast
vi.mock('react-hot-toast', () => {
  const mockToast = vi.fn();
  mockToast.success = vi.fn();
  mockToast.error = vi.fn();
  mockToast.loading = vi.fn();
  mockToast.dismiss = vi.fn();
  mockToast.promise = vi.fn();
  return { default: mockToast };
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe('showToast', () => {
  it('success() calls toast.success with 3s duration and green icon theme', () => {
    showToast.success('Saved!');
    expect(toast.success).toHaveBeenCalledWith('Saved!', expect.objectContaining({
      duration: 3000,
      iconTheme: { primary: '#22c55e', secondary: '#fff' },
    }));
  });

  it('error() calls toast.error with 5s duration and red icon theme', () => {
    showToast.error('Failed');
    expect(toast.error).toHaveBeenCalledWith('Failed', expect.objectContaining({
      duration: 5000,
      iconTheme: { primary: '#ef4444', secondary: '#fff' },
    }));
  });

  it('info() calls toast() with ℹ️ icon and 4s duration', () => {
    showToast.info('Note');
    expect(toast).toHaveBeenCalledWith('Note', expect.objectContaining({
      duration: 4000,
      icon: 'ℹ️',
    }));
  });

  it('warning() calls toast() with ⚠️ icon and 4s duration', () => {
    showToast.warning('Careful');
    expect(toast).toHaveBeenCalledWith('Careful', expect.objectContaining({
      duration: 4000,
      icon: '⚠️',
    }));
  });

  it('loading() calls toast.loading with dark style', () => {
    showToast.loading('Please wait...');
    expect(toast.loading).toHaveBeenCalledWith('Please wait...', expect.objectContaining({
      style: expect.objectContaining({ background: '#1f2937' }),
    }));
  });

  it('dismiss is toast.dismiss', () => {
    expect(showToast.dismiss).toBe(toast.dismiss);
  });

  it('promise is toast.promise', () => {
    expect(showToast.promise).toBe(toast.promise);
  });

  it('custom options override defaults', () => {
    showToast.success('Done', { duration: 8000 });
    expect(toast.success).toHaveBeenCalledWith('Done', expect.objectContaining({
      duration: 8000,
    }));
  });
});

describe('useToast', () => {
  it('returns the showToast object', () => {
    const result = useToast();
    expect(result).toBe(showToast);
  });
});
