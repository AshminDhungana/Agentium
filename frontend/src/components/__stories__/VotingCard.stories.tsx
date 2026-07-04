import type { Meta, StoryObj } from '@storybook/react';
import { VotingCard } from '../voting/VotingCard';
import { AmendmentVoting, TaskDeliberation } from '../../services/voting';

/**
 * VotingCard stories -- demonstrates the summary card for a single
 * amendment or deliberation with status badge, vote tally, and countdown timer.
 */

const meta: Meta<typeof VotingCard> = {
  title: 'Voting/VotingCard',
  component: VotingCard,
  tags: ['autodocs'],
  argTypes: {
    item: { description: 'The voting item to display (amendment or deliberation)' },
    isSelected: { description: 'Whether this card is currently selected' },
    onClick: { description: 'Callback when the card is clicked' },
    isAmendment: { description: 'Whether this item is an amendment (true) or deliberation (false)' },
  },
};
export default meta;

type Story = StoryObj<typeof VotingCard>;

const baseAmendment: AmendmentVoting = {
  id: 'amend-1',
  agentium_id: 'A001',
  status: 'voting',
  title: 'Expand Knowledge Base Storage',
  sponsors: ['User A'],
  sponsors_needed: 3,
  eligible_voters: ['User A', 'User B', 'User C', 'User D'],
  votes_for: 2,
  votes_against: 0,
  votes_abstain: 1,
  started_at: new Date().toISOString(),
  ended_at: new Date(Date.now() + 86400000).toISOString(),
  created_at: new Date().toISOString(),
  discussion_thread: [
    { timestamp: new Date().toISOString(), agent: 'User A', message: 'This is a crucial upgrade for our data capacity.' },
  ],
};

export const AmendmentDefault: Story = {
  args: {
    item: baseAmendment,
    isSelected: false,
    onClick: () => {},
    isAmendment: true,
  },
};

export const AmendmentSelected: Story = {
  args: {
    item: baseAmendment,
    isSelected: true,
    onClick: () => {},
    isAmendment: true,
  },
};

export const AmendmentPassed: Story = {
  args: {
    item: { ...baseAmendment, status: 'passed', final_result: 'passed' },
    isSelected: false,
    onClick: () => {},
    isAmendment: true,
  },
};

const baseDeliberation: TaskDeliberation = {
  id: 'delib-1',
  agentium_id: 'D001',
  task_id: 'task-1',
  status: 'active',
  participating_members: ['User A', 'User B', 'User C'],
  votes_for: 2,
  votes_against: 1,
  votes_abstain: 0,
  started_at: new Date().toISOString(),
  ended_at: new Date(Date.now() + 43200000).toISOString(),
  created_at: new Date().toISOString(),
  discussion_thread: [],
};

export const DeliberationActive: Story = {
  args: {
    item: baseDeliberation,
    isSelected: false,
    onClick: () => {},
    isAmendment: false,
  },
};
