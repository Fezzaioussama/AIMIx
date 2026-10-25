import { RunInputCard } from '../pipelines/RunInputCard';
import { Bubble } from './Bubble';
import type { ViewProps } from './messageContext';
import type { InputsState } from './missionMessages';

/** How a run form reads once it is no longer the one to fill in. */
const DONE: Record<InputsState, string> = {
  open: 'This form was replaced by a newer one.',
  started: 'Run started. You can follow it under Results.',
  closed: 'This form was replaced by a newer one.',
};

/**
 * The run's inputs, asked for in the conversation: the builder's run form as it is
 * (named inputs or one text field, each with "Attach a document"). Only the newest
 * open form can be filled in. The team is saved before the run starts, so the form
 * never asks for a save.
 */
export function InputsMessageView({ message, context }: ViewProps<'inputs'>) {
  const { team, run, runActive } = context;
  if (message.id !== run.formId || team === null) return <Bubble>{DONE[message.state]}</Bubble>;
  return (
    <>
      <Bubble>Here’s what your team needs to start. Fill it in, then run.</Bubble>
      {/* The form lays its fields out in two columns from the md breakpoint, but this
          pane is narrower than that whatever the screen: its grids stack, and it sits
          right under the bubble rather than a page section's distance away. */}
      <div className="[&_.grid]:grid-cols-1 [&>*]:mt-0">
        <RunInputCard
          inputs={team.inputs}
          draft={run.draft}
          isRunning={run.starting || runActive}
          dirty={false}
          isSaved={team.id !== undefined}
          message={run.error}
          onDraftChange={run.setDraft}
          onRun={() => void run.start()}
        />
      </div>
    </>
  );
}
