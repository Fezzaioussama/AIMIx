import { useEffect, useRef } from 'react';

import { DOCUMENTS_INPUT_NAME } from '../../core/api/pipelines';
import type { Pipeline } from '../../core/api/types';
import { inputLabel } from '../pipelines/pipelineInputs';
import { RunInputCard } from '../pipelines/RunInputCard';
import { Bubble } from './Bubble';
import type { ViewProps } from './messageContext';
import type { InputsState } from './missionMessages';

/** How a run form reads once it is no longer the one to fill in. */
const DONE: Record<InputsState, string> = {
  open: 'This form was replaced by a newer one.',
  started: 'Inputs sent.',
  closed: 'This form was replaced by a newer one.',
};

/** What the form says when the input for documents is empty and nothing will fill it. */
function documentsAgain(team: Pipeline): string {
  const field = team.inputs.find((input) => input.name === DOCUMENTS_INPUT_NAME);
  const label = field ? inputLabel(field) : DOCUMENTS_INPUT_NAME;
  return (
    `Attach your documents again under “${label}”: ` +
    'AIMIx keeps only their names, not their text.'
  );
}

/**
 * The run's inputs, asked for in the conversation: the builder's run form as it is
 * (named inputs or one text field, each with "Attach a document"). Only the newest
 * open form can be filled in. The team is saved before the run starts, so the form
 * never asks for a save.
 */
export function InputsMessageView({ message, context }: ViewProps<'inputs'>) {
  const { team, run, runActive, focusComposer, runWaitsFor, documentsGone } = context;
  const form = useRef<HTMLDivElement>(null);
  const takesFocus = message.id === run.newFormId;

  // The "Run it" button went away as the form came: focus goes to the form's first field.
  // The log follows its new end in this same commit, after this effect; in the next frame,
  // before it is painted, the field is brought back into view with its label (its scroll
  // margin). Instantly on purpose, motion or not: a smooth scroll would show the end first.
  useEffect(() => {
    const field = takesFocus ? form.current?.querySelector('textarea') : null;
    if (!field) return;
    field.focus({ preventScroll: true });
    const frame = requestAnimationFrame(() => field.scrollIntoView?.({ block: 'nearest' }));
    return () => cancelAnimationFrame(frame);
  }, [takesFocus]);

  if (message.id !== run.formId || team === null) return <Bubble>{DONE[message.state]}</Bubble>;

  // The form is gone once the run starts, so focus goes back to the message box.
  async function start() {
    if (await run.start()) focusComposer();
  }

  return (
    <>
      <Bubble>
        <p>Here’s what your team needs to start. Fill it in, then run.</p>
        {documentsGone && <p className="mt-2">{documentsAgain(team)}</p>}
      </Bubble>
      {/* The form lays its fields out in two columns from the md breakpoint, but this
          pane is narrower than that whatever the screen: its grids stack, and it sits
          right under the bubble rather than a page section's distance away. */}
      <div ref={form} className="[&_.grid]:grid-cols-1 [&>div]:mt-0 [&>div]:p-5">
        <RunInputCard
          inputs={team.inputs}
          draft={run.draft}
          isRunning={run.starting || runActive}
          dirty={false}
          isSaved={team.id !== undefined}
          message={run.error}
          onDraftChange={run.setDraft}
          onRun={() => void start()}
          waitingFor={runWaitsFor}
        />
      </div>
    </>
  );
}
