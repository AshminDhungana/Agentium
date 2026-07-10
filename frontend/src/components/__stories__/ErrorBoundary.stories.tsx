import type { Meta, StoryObj } from '@storybook/react';
import { ErrorBoundary } from '../common/ErrorBoundary';
import React, { Suspense, lazy } from 'react';

/**
 * ErrorBoundary stories — renders a component that intentionally throws errors
 * to demonstrate both widget and page fallback UIs.
 */

const BrokenComponent = () => { throw new Error('Intentional crash for Storybook!'); };

// Simulate a lazy component that fails to load
const FailingLazyComponent = lazy(() =>
  Promise.reject(new Error('Chunk load failed'))
);

const meta: Meta<typeof ErrorBoundary> = {
  title: 'Common/ErrorBoundary',
  component: ErrorBoundary,
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['page', 'widget'],
      description: 'Display size: page (full) or widget (compact card)',
    },
    fallbackHeading: {
      control: 'text',
      description: 'Heading text shown in the fallback UI',
    },
  },
};
export default meta;

type Story = StoryObj<typeof ErrorBoundary>;

export const WidgetFallback: Story = {
  args: {
    variant: 'widget',
    fallbackHeading: 'Widget Load Failed',
  },
  render: (args) => (
    <ErrorBoundary {...args}>
      <BrokenComponent />
    </ErrorBoundary>
  ),
};

export const PageFallback: Story = {
  args: {
    variant: 'page',
    fallbackHeading: 'Page Load Failed',
  },
  render: (args) => (
    <ErrorBoundary {...args}>
      <BrokenComponent />
    </ErrorBoundary>
  ),
};

// New story: Root-level error boundary (as used in main.tsx)
export const RootErrorFallback: Story = {
  args: {
    variant: 'page',
    fallbackHeading: 'Application Error',
  },
  render: (args) => (
    <ErrorBoundary {...args}>
      <BrokenComponent />
    </ErrorBoundary>
  ),
};

// New story: Widget error boundary for chunk loading (as used in MainLayout)
export const ChunkLoadErrorFallback: Story = {
  args: {
    variant: 'widget',
    fallbackHeading: 'Page Load Failed',
  },
  render: (args) => (
    <ErrorBoundary {...args}>
      <Suspense fallback={<div>Loading...</div>}>
        <FailingLazyComponent />
      </Suspense>
    </ErrorBoundary>
  ),
};
