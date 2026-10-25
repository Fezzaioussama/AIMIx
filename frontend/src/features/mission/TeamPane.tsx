import { Compass, SquareArrowOutUpRight, Users } from 'lucide-react';
import { Link } from 'react-router-dom';

import { HOME_PATH } from '../../core/routes';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { SECONDARY_BUTTON } from '../pipelines/buttonStyles';
import { PipelineGraph } from '../pipelines/PipelineGraph';
import { PaneHeader } from './PaneHeader';
import { countOf } from './teamBrief';
import type { Mission } from './useMission';
import type { MissionTeam } from './useMissionTeam';

interface TeamPaneProps {
  mission: Mission;
  /** The agent the drawer is editing, marked on the graph. */
  selected: number | null;
  onEditStep: (order: number) => void;
}

/** Where saving stands, in a few words. */
function saveNote(team: MissionTeam): string {
  if (team.status === 'saving') return 'Saving…';
  if (team.pipeline?.id === undefined) return 'Saved when you first run it';
  return team.unsaved ? 'Saving your changes…' : 'Saved';
}

function TeamEmpty() {
  return (
    <div className="mx-auto flex max-w-sm flex-col items-center py-16 text-center">
      <span className="grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-sky-400/20 via-indigo-500/20 to-purple-500/25 ring-1 ring-white/10">
        <Compass aria-hidden="true" className="size-7 text-sky-200" />
      </span>
      <h3 className="mt-5 text-lg font-semibold text-white">Your team will appear here</h3>
      <p className="mt-2 text-sm text-slate-300">
        Describe what you want done in the conversation. AIMIx builds a team of AI agents and shows
        who does what, so you can change it before anything runs.
      </p>
    </div>
  );
}

/** A mission that could not be opened (deleted, or not yours) leads back to a fresh start. */
function MissionMissing({ message }: { message: string }) {
  return (
    <div className="mx-auto max-w-sm py-16 text-center">
      <p role="alert" className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
        {message}
      </p>
      <Link to={HOME_PATH} className={`mt-4 ${SECONDARY_BUTTON}`}>
        Start a new mission
      </Link>
    </div>
  );
}

function TeamBody({ mission, selected, onEditStep }: TeamPaneProps) {
  const { team, followed, run } = mission;
  const { pipeline } = team;
  if (team.status === 'loading') {
    return <BusyNotice className="py-16">Loading your mission…</BusyNotice>;
  }
  if (pipeline === null)
    return team.error ? <MissionMissing message={team.error} /> : <TeamEmpty />;

  const stages = new Set(pipeline.steps.map((step) => step.stage)).size;
  // A run's own agents cannot be edited while it works; its snapshot would not change anyway.
  const editable = !followed.active && !run.starting;
  return (
    <>
      <h3 className="text-xl font-bold tracking-tight break-words text-white">{pipeline.name}</h3>
      <p className="mt-1 text-sm text-slate-400">
        {countOf(pipeline.steps.length, 'agent')} · {countOf(stages, 'stage')} ·{' '}
        <span role="status">{saveNote(team)}</span>
      </p>
      {team.error && (
        <p role="alert" className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {team.error}
        </p>
      )}
      <div className="mt-4">
        <PipelineGraph
          steps={pipeline.steps}
          inputs={pipeline.inputs}
          liveSteps={followed.shown?.steps}
          isRunning={followed.shownActive}
          input={followed.shown?.input ?? ''}
          selected={selected}
          onEditStep={editable ? onEditStep : undefined}
        />
      </div>
      <p className="mt-3 text-xs text-slate-400">
        {editable
          ? 'Select an agent to edit it, or ask for a change in the conversation.'
          : 'Your team is working. You can edit it again when the run ends.'}
      </p>
    </>
  );
}

/** The team at the centre: its graph (live while a run works) and "Open in builder". */
export function TeamPane(props: TeamPaneProps) {
  const { mission } = props;
  const { team } = mission;
  return (
    <>
      <PaneHeader pane="team" icon={Users}>
        {team.pipeline !== null && (
          <button
            type="button"
            disabled={team.status !== 'idle'}
            onClick={() => void mission.openInBuilder()}
            className={`${SECONDARY_BUTTON} px-3 py-1.5`}
          >
            <SquareArrowOutUpRight aria-hidden="true" className="size-3.5" />
            Open in builder
          </button>
        )}
      </PaneHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
        <TeamBody {...props} />
      </div>
    </>
  );
}
