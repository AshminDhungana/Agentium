import { describe, it } from 'vitest';
import { auditRoute } from '@/test/a11yBrowser';
import { ModelCard } from '@/components/models/ModelCard';
import type { ModelConfig } from '@/types';

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-white dark:bg-[#0f1117] p-6">{children}</div>
);

const mockConfig: ModelConfig = {
  id: 'cfg-1',
  provider: 'openai',
  config_name: 'OpenAI Default',
  default_model: 'gpt-4o',
  available_models: ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo', 'o1', 'o3-mini'],
  status: 'active',
  is_default: true,
  settings: { max_tokens: 4096, temperature: 0.7, top_p: 1, timeout: 60 },
  total_usage: { requests: 120, tokens: 45000, cost_usd: 0.32 },
  api_key_masked: 'sk-...1234',
  requests_per_minute: 60,
};

const noop = () => {};

describe('ModelCard color-contrast', () => {
  it('passes in light theme', async () => {
    const result = await auditRoute(
      <Shell>
        <ModelCard
          config={mockConfig}
          activeAction={null}
          pendingDeleteId={null}
          onTest={noop}
          onFetchModels={noop}
          onEdit={noop}
          onDelete={noop}
          onSetDefault={noop}
          onPendingDelete={noop}
        />
      </Shell>,
      'light'
    );
    expect(result).toHaveNoViolations();
  });

  it('passes in dark theme', async () => {
    const result = await auditRoute(
      <Shell>
        <ModelCard
          config={mockConfig}
          activeAction={null}
          pendingDeleteId={null}
          onTest={noop}
          onFetchModels={noop}
          onEdit={noop}
          onDelete={noop}
          onSetDefault={noop}
          onPendingDelete={noop}
        />
      </Shell>,
      'dark'
    );
    expect(result).toHaveNoViolations();
  });
});
