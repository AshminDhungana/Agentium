import type { Meta, StoryObj } from '@storybook/react';
import { ErrorBoundary } from '../common/ErrorBoundary';
import React from 'react';

/**
 * ErrorBoundary stories — renders a component that intentionally throws errors
 * to demonstrate both widget and page fallback UIs.
 */

const BrokenComponent = () => { throw new Error('Intentional crash for Storybook!'); };

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
