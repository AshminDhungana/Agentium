import type { Meta, StoryObj } from '@storybook/react';
import { LoadingSpinner } from '../ui/LoadingSpinner';

/**
 * LoadingSpinner stories — documents every size variant and the optional label state.
 */

const meta: Meta<typeof LoadingSpinner> = {
  title: 'UI/LoadingSpinner',
  component: LoadingSpinner,
  tags: ['autodocs'],
  argTypes: {
    size: {
      control: 'select',
      options: ['xs', 'sm', 'md', 'lg', 'xl'],
      description: 'Spinner diameter preset',
    },
    label: {
      control: 'text',
      description: 'Optional text shown beneath the spinner',
    },
    className: {
      control: 'text',
      description: 'Additional Tailwind classes to merge',
    },
  },
};
export default meta;

type Story = StoryObj<typeof LoadingSpinner>;

export const Default: Story = { args: {} };

export const ExtraSmall: Story = { args: { size: 'xs' } };
export const Small: Story = { args: { size: 'sm' } };
export const Medium: Story = { args: { size: 'md' } };
export const Large: Story = { args: { size: 'lg' } };
export const ExtraLarge: Story = { args: { size: 'xl' } };

export const WithLabel: Story = {
  args: { size: 'lg', label: 'Loading agents...' },
};

export const CustomClass: Story = {
  args: { size: 'md', className: 'text-blue-500', label: 'Downloading...' },
};
