import { WidgetCard } from './WidgetCard';
import { useBackendStore } from '@/store/backendStore';
import { Shield } from 'lucide-react';

export function SystemHealth() {
  const status = useBackendStore((s) => s.status);
  const version = (status as any).constitutionVersion ?? '—';

  return (
    <WidgetCard title="System Health" icon={Shield} aria-label="System health">
      <dl className="divide-y divide-hairline">
        <Row label="Backend" value={status.status === 'connected' ? 'Connected' : 'Disconnected'} />
        <Row label="API Latency" value={`${status.latency ?? '—'} ms`} />
        <Row label="Constitution" value={version} />
      </dl>
    </WidgetCard>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-5 py-3 text-sm">
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="font-medium text-gray-900 dark:text-gray-100">{value}</dd>
    </div>
  );
}
