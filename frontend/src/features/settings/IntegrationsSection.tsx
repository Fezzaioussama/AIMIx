import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { IntegrationCard } from './IntegrationCard';
import { IntegrationForm } from './IntegrationForm';
import { NoticeLine } from './NoticeLine';
import { useIntegrations } from './useIntegrations';

type IntegrationsState = ReturnType<typeof useIntegrations>;

function SectionIntro() {
  return (
    <>
      <h2 id="integrations-heading" className="text-2xl font-bold tracking-tight">
        Integrations
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        Connect a service that gives you an MCP server URL, such as your CRM, a database, your
        company&apos;s tools or an automation hub. Its tools become available to your agents in chat
        and pipelines. Only your account can use the integrations you add here.
      </p>
    </>
  );
}

type IntegrationListProps = Pick<IntegrationsState, 'tests' | 'editing' | 'actions'> & {
  integrations: NonNullable<IntegrationsState['integrations']>;
  busy: boolean;
};

/** Each integration as a card, or as its form while it is being edited. */
function IntegrationList({ integrations, tests, editing, busy, actions }: IntegrationListProps) {
  return integrations.map((integration, index) =>
    editing === integration.id ? (
      <IntegrationForm
        key={integration.id}
        saved={integration}
        busy={busy}
        onSave={(draft) => void actions.update(integration, draft)}
        onCancel={() => actions.startEditing(null)}
      />
    ) : (
      <AnimatedContent key={integration.id} distance={18} delay={index * 0.05}>
        <IntegrationCard
          integration={integration}
          test={tests[integration.id]}
          busy={busy}
          onToggle={(enabled) => void actions.setEnabled(integration, enabled)}
          onEdit={() => actions.startEditing(integration.id)}
          onDelete={() => void actions.remove(integration)}
          onTest={() => void actions.test(integration)}
        />
      </AnimatedContent>
    ),
  );
}

/** Settings → Integrations: the account's own MCP servers. */
export function IntegrationsSection() {
  const { integrations, tests, editing, status, notice, actions } = useIntegrations();
  const busy = status !== 'idle';

  return (
    <section
      aria-labelledby="integrations-heading"
      className="mt-12 border-t border-white/10 pt-10"
    >
      <SectionIntro />
      {status === 'loading' && <p className="text-sm text-slate-400">Loading integrations…</p>}
      {integrations && (
        <div className="space-y-4">
          {integrations.length === 0 && editing !== 'new' && (
            <p className="text-sm text-slate-400">No integrations yet.</p>
          )}
          <IntegrationList
            integrations={integrations}
            tests={tests}
            editing={editing}
            busy={busy}
            actions={actions}
          />
          {editing === 'new' ? (
            <IntegrationForm
              saved={null}
              busy={busy}
              onSave={(draft) => void actions.create(draft)}
              onCancel={() => actions.startEditing(null)}
            />
          ) : (
            <button
              type="button"
              onClick={() => actions.startEditing('new')}
              className="w-full rounded-xl border border-dashed border-white/20 px-4 py-3 text-sm text-slate-300 transition-colors hover:border-sky-400/40 hover:text-sky-300 focus-visible:outline-2 focus-visible:outline-sky-400"
            >
              + Add an integration
            </button>
          )}
        </div>
      )}
      {notice && (
        <div className="mt-4">
          <NoticeLine notice={notice} />
        </div>
      )}
    </section>
  );
}
