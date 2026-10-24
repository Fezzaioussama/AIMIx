import { Layers, Users } from 'lucide-react';

import type { MissionTemplate } from '../../core/api/types';
import { Spinner } from '../../core/ui/Spinner';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { templateIcon } from './templateIcons';

interface TemplateCardProps {
  template: MissionTemplate;
  /** This template is being turned into a pipeline. */
  busy: boolean;
  /** Some template is: no other one can be used meanwhile. */
  disabled: boolean;
  onUse: (template: MissionTemplate) => void;
}

function count(amount: number, noun: string): string {
  return `${amount} ${noun}${amount === 1 ? '' : 's'}`;
}

const USE_BUTTON =
  'inline-flex w-full items-center justify-center gap-2 rounded-xl border border-sky-400/30 bg-sky-400/10 px-4 py-2.5 text-sm font-semibold text-sky-100 transition-colors not-disabled:hover:border-sky-300/50 not-disabled:hover:bg-sky-400/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50';

/** One template in the gallery: what it does, what it asks for, how big the team is. */
export function TemplateCard({ template, busy, disabled, onUse }: TemplateCardProps) {
  const Icon = templateIcon(template.slug);
  const provided = template.inputs.map((field) => field.label || field.name).join(', ');

  return (
    <SpotlightCard className="flex h-full flex-col p-6" spotlightColor="rgba(129, 140, 248, 0.14)">
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="grid size-11 place-items-center rounded-xl bg-gradient-to-br from-sky-400/20 via-indigo-500/20 to-purple-500/25 ring-1 ring-white/10">
          <Icon aria-hidden="true" className="size-5 text-sky-200" />
        </span>
        <span className="rounded-full border border-white/10 px-2.5 py-0.5 text-xs font-medium text-slate-300">
          {template.category}
        </span>
      </div>
      <h2 className="text-lg font-semibold text-white">{template.title}</h2>
      <p className="mt-2 text-sm text-slate-300">{template.description}</p>
      {provided && (
        <p className="mt-4 text-sm text-slate-400">
          <span className="font-medium text-slate-200">You provide:</span> {provided}
        </p>
      )}
      <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <Users aria-hidden="true" className="size-3.5" />
          {count(template.step_count, 'agent')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Layers aria-hidden="true" className="size-3.5" />
          {count(template.stage_count, 'stage')}
        </span>
      </p>
      <div className="mt-auto pt-6">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onUse(template)}
          className={USE_BUTTON}
        >
          {busy && <Spinner decorative className="size-4" />}
          {busy ? 'Creating…' : 'Use this template'}
          <span className="sr-only">: {template.title}</span>
        </button>
      </div>
    </SpotlightCard>
  );
}
