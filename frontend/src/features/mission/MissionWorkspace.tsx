import { useEffect, useState, type ReactNode } from 'react';

import type { AgentTool, PipelineStep } from '../../core/api/types';
import { useAgentTools } from '../../core/hooks/useAgentTools';
import { useMediaQuery } from '../../core/hooks/useMediaQuery';
import { useModels } from '../../core/hooks/useModels';
import { ConversationPane } from './ConversationPane';
import { WIDE_LAYOUT, paneIds, type PaneId } from './missionPanes';
import { restoreMission } from './missionStorage';
import { MissionTabs } from './MissionTabs';
import { ResultsPane } from './ResultsPane';
import { StepDrawer } from './StepDrawer';
import { TeamPane } from './TeamPane';
import { useMission, type Mission } from './useMission';
import { usePanes } from './usePanes';
import { useStepDrawer, type StepDrawerState } from './useStepDrawer';

const NO_STEPS: PipelineStep[] = [];

/** Each pane's own look on a wide screen: the side panes are set off by a hairline. */
const PANE_STYLES: Record<PaneId, string> = {
  chat: 'xl:border-r xl:border-white/[0.06] xl:bg-slate-950/50',
  team: '',
  results: 'xl:border-l xl:border-white/[0.06] xl:bg-slate-950/50',
};

interface PaneProps {
  pane: PaneId;
  active: boolean;
  /** Side by side (no tabs), so a pane is a labelled region rather than a tab panel. */
  wide: boolean;
  children: ReactNode;
}

/**
 * One pane. All three stay mounted, so a typed message or a scroll position survives a
 * switch of tab; a narrow screen only hides the ones not in front. It clips (without
 * becoming scrollable) what decoration spills past its edge, e.g. the sparks around a
 * button, which would otherwise make the page taller.
 */
function Pane({ pane, active, wide, children }: PaneProps) {
  const ids = paneIds(pane);
  return (
    <section
      id={ids.panel}
      role={wide ? undefined : 'tabpanel'}
      aria-labelledby={wide ? ids.heading : ids.tab}
      className={`min-h-0 min-w-0 flex-1 flex-col overflow-clip xl:flex ${active ? 'flex' : 'hidden'} ${PANE_STYLES[pane]}`}
    >
      {children}
    </section>
  );
}

interface EditDrawerProps {
  mission: Mission;
  drawer: StepDrawerState;
  models: string[];
  tools: AgentTool[];
  /** Why the models or tools could not be loaded, if they could not. */
  notice?: string;
}

/** The drawer for the agent being edited, wired to the mission's team. */
function EditDrawer({ mission, drawer, models, tools, notice }: EditDrawerProps) {
  const { step } = drawer;
  const { pipeline, patchStep, removeStep } = mission.team;
  if (step === null || pipeline === null) return null;

  function remove(order: number) {
    removeStep(order);
    drawer.close();
  }

  return (
    <StepDrawer
      step={step}
      steps={pipeline.steps}
      inputs={pipeline.inputs}
      models={models}
      tools={tools}
      canRemove={pipeline.steps.length > 1}
      notice={notice}
      onChange={(patch) => patchStep(step.order, patch)}
      onRemove={() => remove(step.order)}
      onClose={drawer.close}
      className="absolute inset-y-0 right-0 z-30 w-full xl:w-[26rem]"
    />
  );
}

/** How many change requests the conversation has applied: each can renumber the agents. */
function appliedCount(mission: Mission): number {
  return mission.conversation.messages.filter(
    (message) =>
      message.from === 'aimix' && message.kind === 'proposal' && message.state === 'applied',
  ).length;
}

interface MissionWorkspaceProps {
  /** The mission the address names; undefined for a new one. */
  routeId: number | undefined;
  /** "New mission": forget this one's draft and start afresh. */
  onStartOver: () => void;
}

/**
 * The mission workspace: the conversation with AIMIx, the team, and the results, side by
 * side on a wide screen and as tabs on a narrow one. An agent selected on the team opens
 * in a drawer over the results.
 */
export function MissionWorkspace({ routeId, onStartOver }: MissionWorkspaceProps) {
  const [seed] = useState(() => restoreMission(routeId));
  const mission = useMission(routeId, seed);
  const { models, error: modelsError } = useModels();
  const { tools, error: toolsError } = useAgentTools();
  const panes = usePanes();
  const wide = useMediaQuery(WIDE_LAYOUT);
  const drawer = useStepDrawer(mission.team.pipeline?.steps ?? NO_STEPS);
  const { dismiss } = drawer;
  const applied = appliedCount(mission);

  // An applied change can renumber the agents: the drawer must not point at another one.
  useEffect(() => dismiss(), [applied, dismiss]);

  // The screen is exactly as tall as the window: each pane scrolls inside itself, and
  // nothing may make the page scroll. Hidden text (`sr-only` is absolutely positioned)
  // is contained by the scrolling areas, decoration is clipped by the panes, and the
  // root clips what is left.
  return (
    <div className="flex h-[calc(100dvh-60px)] min-h-0 flex-col overflow-clip text-slate-50">
      <h1 className="sr-only">Missions</h1>
      {!wide && (
        <MissionTabs
          active={panes.active}
          onChange={panes.select}
          runStatus={mission.followed.run?.status ?? null}
        />
      )}
      {/* One row as tall as the screen: without it the row grows with the tallest pane's
          content and the page scrolls, instead of each pane scrolling inside itself. */}
      <div className="relative flex min-h-0 flex-1 xl:grid xl:grid-cols-[24rem_minmax(0,1fr)_26rem] xl:grid-rows-[minmax(0,1fr)]">
        <Pane pane="chat" active={panes.active === 'chat'} wide={wide}>
          <ConversationPane mission={mission} showPane={panes.show} onStartOver={onStartOver} />
        </Pane>
        <Pane pane="team" active={panes.active === 'team'} wide={wide}>
          <TeamPane
            mission={mission}
            selected={drawer.step?.order ?? null}
            onEditStep={drawer.open}
          />
        </Pane>
        <Pane pane="results" active={panes.active === 'results'} wide={wide}>
          <ResultsPane mission={mission} />
        </Pane>
        <EditDrawer
          mission={mission}
          drawer={drawer}
          models={models}
          tools={tools}
          notice={modelsError ?? toolsError ?? undefined}
        />
      </div>
    </div>
  );
}
