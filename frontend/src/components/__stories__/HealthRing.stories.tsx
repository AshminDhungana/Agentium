import type { Meta, StoryObj } from '@storybook/react';
import { HealthRing } from '../ui/HealthRing';

/**
 * HealthRing stories -- demonstrates health score visualization
 * across the full 0-100 range and configurable sizes.
 */

const meta: Meta<typeof HealthRing> = {
  title: 'UI/HealthRing',
  component: HealthRing,
  tags: ['autodocs'],
  argTypes: {
    score: {
      control: { type: 'range', min: 0, max: 100, step: 1 },
      description: 'Health score (0-100)',
    },
    size: {
      control: { type: 'range', min: 24, max: 72, step: 4 },
      description: 'Diameter in pixels (default: 36)',
    },
  },
};
export default meta;

type Story = StoryObj<typeof HealthRing>;

export const Healthy: Story = { args: { score: 85 } };

export const Warning: Story = { args: { score: 55 } };

export const Critical: Story = { args: { score: 25 } };

export const Large: Story = { args: { score: 90, size: 48 } };

export const Small: Story = { args: { score: 100, size: 28 } };
