import type { Meta, StoryObj } from '@storybook/react';
import { useToast } from '../../hooks/useToast';
import React from 'react';

/**
 * Toast stories -- interactive demonstration of the toast notification system.
 * The project uses react-hot-toast via useToast.ts; these stories show each variant.
 */

const ToastDemo: React.FC = () => {
  const toast = useToast();
  return (
    <div className="flex flex-col gap-3 p-4">
      <button
        onClick={() => toast.success('Task completed successfully!')}
        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors"
      >
        Success Toast
      </button>
      <button
        onClick={() => toast.error('Task failed to execute')}
        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
      >
        Error Toast
      </button>
      <button
        onClick={() => toast.info('Agent is deliberating on the amendment')}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
      >
        Info Toast
      </button>
      <button
        onClick={() => toast.warning('Budget is approaching 80% threshold')}
        className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition-colors"
      >
        Warning Toast
      </button>
      <button
        onClick={() => toast.loading('Loading agent data...')}
        className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg transition-colors"
      >
        Loading Toast
      </button>
    </div>
  );
};

const meta: Meta<typeof ToastDemo> = {
  title: 'UI/Toast',
  component: ToastDemo,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        story: 'Click each button to trigger a toast notification. Ensure the Toaster is rendered in your app or preview wrapper.',
      },
    },
  },
};

export default meta;

type Story = StoryObj<typeof ToastDemo>;

export const ToastInteractions: Story = {};
