import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { MissionTemplate } from '../../core/api/types';
import { BrandMark } from '../../core/ui/BrandMark';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { PipelineNav } from '../pipelines/PipelineNav';
import { CategoryFilter } from './CategoryFilter';
import { TemplateCard } from './TemplateCard';
import { ALL_CATEGORIES, categoryChips, inCategory } from './templateFilters';
import { useTemplates } from './useTemplates';

const ALERT_CLASS = 'mb-6 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300';

function TemplatesHeader() {
  return (
    <header className="mb-8">
      <div className="mb-3 flex items-baseline gap-3">
        <BrandMark />
        <ShinyText className="text-sm text-slate-300/80">Templates</ShinyText>
      </div>
      <PipelineNav />
      <h1 className="mt-6 text-3xl font-extrabold tracking-tight">Start from a template</h1>
      <p className="mt-2 max-w-2xl text-sm text-slate-400">
        Ready-made agent teams for common work. Pick one and it opens in the builder as your own
        pipeline: fill in what it asks for, then run it. You can change any step.
      </p>
    </header>
  );
}

/** The template gallery: filter by category, then turn a template into a pipeline. */
export function TemplatesPage() {
  const navigate = useNavigate();
  const { templates, status, loadError, creating, createError, actions } = useTemplates();
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const shown = inCategory(templates, category);
  const creatingTitle = templates.find((template) => template.slug === creating)?.title;

  async function handleUse(template: MissionTemplate) {
    const created = await actions.create(template);
    // The builder opens a saved pipeline from router state, as after Auto Pipeline.
    if (created?.id !== undefined) navigate('/pipeline', { state: { pipelineId: created.id } });
  }

  return (
    <div className="min-h-[calc(100vh-60px)] px-4 py-10 text-slate-50 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <TemplatesHeader />

        <p aria-live="polite" className="sr-only">
          {creatingTitle ? `Creating your pipeline from ${creatingTitle}…` : ''}
        </p>
        {createError && (
          <p role="alert" className={ALERT_CLASS}>
            {createError}
          </p>
        )}

        {status === 'loading' && <BusyNotice className="py-16">Loading templates…</BusyNotice>}
        {status === 'failed' && (
          <div className={`flex flex-wrap items-center gap-3 ${ALERT_CLASS}`}>
            <p role="alert">{loadError}</p>
            <button
              type="button"
              onClick={actions.reload}
              className="rounded-lg border border-red-300/30 px-3 py-1 font-medium text-red-200 transition-colors hover:bg-red-500/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
            >
              Try again
            </button>
          </div>
        )}
        {status === 'ready' && (
          <>
            <CategoryFilter
              categories={categoryChips(templates)}
              value={category}
              onChange={setCategory}
            />
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {shown.map((template, index) => (
                <li key={template.slug}>
                  <AnimatedContent
                    distance={18}
                    delay={Math.min(index, 8) * 0.05}
                    className="h-full"
                  >
                    <TemplateCard
                      template={template}
                      busy={creating === template.slug}
                      disabled={creating !== null}
                      onUse={(chosen) => void handleUse(chosen)}
                    />
                  </AnimatedContent>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
