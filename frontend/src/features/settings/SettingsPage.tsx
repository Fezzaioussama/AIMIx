import { Link, Navigate, useParams } from 'react-router-dom';

import { LegalLinks } from '../../core/ui/LegalLinks';
import { Page, PageHeader } from '../../core/ui/Page';
import { AccountSection } from './AccountSection';
import { IntegrationsSection } from './IntegrationsSection';
import { MemorySection } from './MemorySection';
import { ProvidersSection } from './ProvidersSection';
import { UsageSection } from './UsageSection';
import { WebhooksSection } from './WebhooksSection';

/** Each tab by its address (/settings/<slug>, the first at /settings itself) and its section. */
const TABS = [
  { slug: '', label: 'Providers', Section: ProvidersSection },
  { slug: 'integrations', label: 'Integrations', Section: IntegrationsSection },
  { slug: 'memory', label: 'Memory', Section: MemorySection },
  { slug: 'webhooks', label: 'Webhooks', Section: WebhooksSection },
  { slug: 'usage', label: 'Usage', Section: UsageSection },
  { slug: 'account', label: 'Account', Section: AccountSection },
] as const;

const SETTINGS_PATH = '/settings';

const tabClass = (active: boolean) =>
  [
    '-mb-px border-b-2 px-1 pt-1 pb-2 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400',
    active
      ? 'border-sky-400 text-sky-200'
      : 'border-transparent text-slate-400 hover:text-slate-50',
  ].join(' ');

/** The tab row; on a phone it wraps onto a second line rather than widen the page. */
function SettingsTabs({ current }: { current: string }) {
  return (
    <nav
      aria-label="Settings sections"
      className="flex flex-wrap gap-x-5 gap-y-1 border-b border-white/10"
    >
      {TABS.map((tab) => (
        <Link
          key={tab.slug}
          to={tab.slug ? `${SETTINGS_PATH}/${tab.slug}` : SETTINGS_PATH}
          aria-current={tab.slug === current ? 'page' : undefined}
          className={tabClass(tab.slug === current)}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

/** Settings at /settings/:tab?: one tab at a time, an unknown tab sends you to the first. */
export function SettingsPage() {
  const slug = useParams().tab ?? '';
  const tab = TABS.find((entry) => entry.slug === slug);
  if (!tab) return <Navigate to={SETTINGS_PATH} replace />;
  const { Section } = tab;

  return (
    <Page>
      <PageHeader
        title="Settings"
        description="Your model providers, the services your agents can reach, what AIMIx keeps in mind for you, the webhooks that link your workflows to other apps, what your runs cost, and your account."
      />
      <SettingsTabs current={tab.slug} />
      <div className="max-w-3xl">
        <Section />
      </div>
      <LegalLinks className="mt-12" />
    </Page>
  );
}
