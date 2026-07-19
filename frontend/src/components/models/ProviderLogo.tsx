import React from 'react';
import { normaliseProviderId, ProviderFormIcon } from '@/constants/providerMeta';

const logoModules = import.meta.glob('@/assets/providers/*.svg', {
  eager: true,
}) as Record<string, { default: string }>;

const LOGO_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(logoModules).map(([path, mod]) => {
    const file = path.split('/').pop()!.replace(/\.svg$/, '');
    return [file, mod.default];
  }),
);

export const ProviderLogo: React.FC<{ provider: string; className?: string }> = ({
  provider,
  className = 'w-5 h-5',
}) => {
  const id = normaliseProviderId(provider);
  const src = LOGO_MAP[id];
  if (src) {
    return <img src={src} alt="" aria-hidden="true" className={`${className} dark:invert`} />;
  }
  return <ProviderFormIcon providerId={provider} className={className} />;
};

export default ProviderLogo;
