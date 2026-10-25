import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { MissionTemplate, Pipeline } from '../../core/api/types';
import { missionPath } from '../../core/routes';
import { Spinner } from '../../core/ui/Spinner';
import { templateIcon } from '../templates/templateIcons';
import { useTemplates } from '../templates/useTemplates';
import { countOf } from './teamBrief';
import { useRecentMissions } from './useRecentMissions';

/** Missions to start from; picking one fills the message box. */
export const MISSION_EXAMPLES = [
  'Research the three main competitors of my product and write a one-page comparison',
  'Turn my meeting notes into a short summary and a list of action items with owners',
  'Write a launch email and three social media posts for my new app',
  'Read a long report and pull out the key numbers, risks and next steps',
] as const;

const SECTION_TITLE = 'mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase';
const CHIP =
  'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-left text-sm text-slate-200 transition-colors not-disabled:hover:border-sky-300/40 not-disabled:hover:bg-sky-400/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50';

function ExampleMissions({ onPick }: { onPick: (example: string) => void }) {
  return (
    <section aria-labelledby="mission-examples" className="mt-6">
      <h4 id="mission-examples" className={SECTION_TITLE}>
        For example
      </h4>
      <ul className="space-y-2">
        {MISSION_EXAMPLES.map((example) => (
          <li key={example}>
            <button
              type="button"
              onClick={() => onPick(example)}
              className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2.5 text-left text-sm text-slate-200 transition-colors hover:border-sky-400/40 hover:bg-sky-400/[0.06] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
            >
              {example}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

type OnTemplate = (template: MissionTemplate, created: Pipeline) => void;

/** One click turns a template into the person's own mission (it is saved at once). */
function TemplateStarts({ onUse }: { onUse: OnTemplate }) {
  const { templates, status, creating, createError, actions } = useTemplates();
  if (status === 'failed' || (status === 'ready' && templates.length === 0)) return null;
  const creatingTitle = templates.find((template) => template.slug === creating)?.title;

  async function use(template: MissionTemplate) {
    const created = await actions.create(template);
    if (created !== null) onUse(template, created);
  }

  return (
    <section aria-labelledby="mission-templates" className="mt-6">
      <h4 id="mission-templates" className={SECTION_TITLE}>
        Or start from a template
      </h4>
      {status === 'loading' && <p className="text-sm text-slate-400">Loading templates…</p>}
      <ul className="flex flex-wrap gap-2">
        {templates.map((template) => {
          const Icon = templateIcon(template.slug);
          return (
            <li key={template.slug}>
              <button
                type="button"
                disabled={creating !== null}
                onClick={() => void use(template)}
                className={CHIP}
              >
                {creating === template.slug ? (
                  <Spinner decorative className="size-4" />
                ) : (
                  <Icon aria-hidden="true" className="size-4 text-sky-300" />
                )}
                {template.title}
              </button>
            </li>
          );
        })}
      </ul>
      <p aria-live="polite" className="sr-only">
        {creatingTitle ? `Creating your mission from ${creatingTitle}…` : ''}
      </p>
      {createError && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {createError}
        </p>
      )}
    </section>
  );
}

function RecentMissions() {
  const missions = useRecentMissions();
  if (missions.length === 0) return null;
  return (
    <nav aria-labelledby="mission-recent" className="mt-6">
      <h4 id="mission-recent" className={SECTION_TITLE}>
        Pick up where you left off
      </h4>
      <ul className="space-y-1.5">
        {missions.map((mission) => (
          <li key={mission.id}>
            <Link
              to={missionPath(mission.id)}
              className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-sm text-slate-200 transition-colors hover:bg-white/[0.05] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
            >
              <span className="min-w-0 flex-1 truncate">{mission.name}</span>
              <span className="shrink-0 text-xs text-slate-400">
                {countOf(mission.steps.length, 'agent')}
              </span>
              <ArrowUpRight aria-hidden="true" className="size-4 shrink-0 text-slate-400" />
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

interface MissionStartProps {
  onExample: (example: string) => void;
  onTemplate: OnTemplate;
}

/** The empty workspace: what to do, examples, template quick-starts and recent missions. */
export function MissionStart({ onExample, onTemplate }: MissionStartProps) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-5">
      <p className="text-xs font-semibold tracking-widest text-sky-300 uppercase">New mission</p>
      <h3 className="mt-1 text-2xl font-bold tracking-tight text-white">
        What do you want to get done?
      </h3>
      <p className="mt-2 text-sm text-slate-300">
        Describe it in your own words. AIMIx puts together a team of AI agents, shows it to you,
        and runs it when you’re ready.
      </p>
      <ExampleMissions onPick={onExample} />
      <TemplateStarts onUse={onTemplate} />
      <RecentMissions />
    </div>
  );
}
