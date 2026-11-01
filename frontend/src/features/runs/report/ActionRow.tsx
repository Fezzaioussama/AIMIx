import { useState, type ReactNode } from 'react';

import type { Run } from '../../../core/api/types';
import { DisclosureButton, Foldable } from '../../pipelines/FoldablePanel';
import { ResumeControl } from '../ResumeControl';
import { RUN_BUTTON } from '../runButtons';
import { isActive, isResumable } from '../runStatus';
import type { RunControls } from '../useRun';
import type { OutcomeKind } from './reportModel';

interface StateActionProps {
  run: Run;
  control: RunControls;
  /** Called as Stop or Resume is pressed, before the control it was goes away. */
  onAct: () => void;
}

/** Stop, which reads "Stopping…" until the stop has been answered. */
function StopButton({ control, onAct }: Omit<StateActionProps, 'run'>) {
  const [stopping, setStopping] = useState(false);
  function stop() {
    setStopping(true);
    onAct();
    void Promise.resolve(control.stop()).finally(() => setStopping(false));
  }
  return (
    <button
      type="button"
      onClick={stop}
      disabled={control.busy}
      aria-label={stopping ? undefined : 'Stop the run'}
      className={RUN_BUTTON.stop}
    >
      {stopping ? 'Stopping…' : 'Stop'}
    </button>
  );
}

/** The run's one action: Stop while it is active, Resume (or a higher limit) once it stopped. */
function StateAction({ run, control, onAct }: StateActionProps) {
  if (isActive(run.status)) return <StopButton control={control} onAct={onAct} />;
  if (!isResumable(run.status)) return null;
  return (
    <ResumeControl
      run={run}
      busy={control.busy}
      onResume={(budget) => {
        onAct();
        void control.resume(budget);
      }}
    />
  );
}

/** The service's own words on why the run failed, folded away under the plain sentence. */
function ServiceSaid({ id, open, detail }: { id: string; open: boolean; detail: string }) {
  return (
    <Foldable id={id} open={open} size="small" bodyClassName="pt-2">
      <p className="rounded-lg bg-white/[0.03] px-3 py-2 text-xs break-words whitespace-pre-wrap text-slate-300">
        {detail}
      </p>
    </Foldable>
  );
}

/** The service's words to fold under a failure's plain sentence; '' for any other outcome. */
function serviceDetail(run: Run, outcome: OutcomeKind): string {
  return outcome === 'failed' ? (run.error?.detail.trim() ?? '') : '';
}

interface ActionRowProps extends StateActionProps {
  outcome: OutcomeKind;
  /** More controls after the run's own action, e.g. Delete. */
  actions?: ReactNode;
}

/**
 * The header's action row: the state's action, the screen's own actions, "What the service
 * said" for a failure, and why the last action failed (the report's only alert).
 */
export function ActionRow({ run, control, onAct, outcome, actions }: ActionRowProps) {
  const [saidOpen, setSaidOpen] = useState(false);
  const detail = serviceDetail(run, outcome);
  const hasAction = isActive(run.status) || isResumable(run.status) || Boolean(actions);
  if (!hasAction && detail === '' && control.error === '') return null;
  const saidId = `run-${run.id}-service-said`;
  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-2">
        <StateAction run={run} control={control} onAct={onAct} />
        {actions}
        {detail !== '' && (
          <DisclosureButton
            open={saidOpen}
            controls={saidId}
            label="What the service said"
            onToggle={() => setSaidOpen((open) => !open)}
          />
        )}
      </div>
      {detail !== '' && <ServiceSaid id={saidId} open={saidOpen} detail={detail} />}
      {control.error && (
        <p role="alert" className="mt-3 text-sm text-amber-300">
          {control.error}
        </p>
      )}
    </div>
  );
}
