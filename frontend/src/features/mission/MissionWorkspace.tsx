import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type ReactNode,
} from 'react';

import type { PipelineStep } from '../../core/api/types';
import { useAgentTools } from '../../core/hooks/useAgentTools';
import { useModels } from '../../core/hooks/useModels';
import { BusyNotice } from '../../core/ui/BusyNotice';
import { FULL_SCREEN_HEIGHT } from '../../core/ui/screen';
import { ConversationPane } from './ConversationPane';
import {
  GRID,
  MAIN_PANES,
  mainPane,
  panePlace,
  paneIds,
  type Layout,
  type PaneId,
} from './missionPanes';
import { restoreMission } from './missionStorage';
import { MissionTabs } from './MissionTabs';
import { ResultsPane } from './ResultsPane';
import { StepDrawer } from './StepDrawer';
import { TeamPane } from './TeamPane';
import { useMission, type Mission } from './useMission';
import { useMissionLayout, type MissionLayout } from './useMissionLayout';
import { usePanes, type Panes } from './usePanes';
import { useStepDrawer, type StepDrawerState } from './useStepDrawer';

const NO_STEPS: PipelineStep[] = [];

interface PaneProps {
  pane: PaneId;
  shown: boolean;
  /** A tab names it (a tab panel); otherwise its own heading does (a region). */
  tabbed: boolean;
  /** Its look and grid cell in the layout. */
  className: string;
  children: ReactNode;
}

/**
 * One pane. All three stay mounted, so a typed message or a scroll position survives a
 * switch of tab or layout; the ones not on screen are only hidden. It clips (without
 * becoming scrollable) what decoration spills past its edge, e.g. the sparks around a
 * button, which would otherwise make the page taller.
 */
function Pane({ pane, shown, tabbed, className, children }: PaneProps) {
  const ids = paneIds(pane);
  return (
    <section
      id={ids.panel}
      role={tabbed ? 'tabpanel' : undefined}
      aria-labelledby={tabbed ? ids.tab : ids.heading}
      className={`min-h-0 min-w-0 flex-1 flex-col overflow-clip ${shown ? 'flex' : 'hidden'} ${className}`}
    >
      {children}
    </section>
  );
}

/** The drawer for the agent being edited, wired to the mission's team. */
function EditDrawer({ mission, drawer }: { mission: Mission; drawer: StepDrawerState }) {
  const { models, error: modelsError } = useModels();
  const { tools, error: toolsError } = useAgentTools();
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
      notice={modelsError ?? toolsError ?? undefined}
      onChange={(patch) => patchStep(step.order, patch)}
      onRemove={() => remove(step.order)}
      onClose={drawer.close}
      className="absolute inset-y-0 right-0 z-30 w-full xl:w-[22rem] 2xl:w-[26rem]"
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

interface PaneGridProps {
  mission: Mission;
  panes: Panes;
  shape: MissionLayout;
  onStartOver: () => void;
}

/**
 * The panes in the layout's grid, in reading order: the conversation, the main column's
 * tabs (two columns), then the team and the results. An agent selected on the team opens
 * in a drawer over the right of the grid.
 */
function PaneGrid({ mission, panes, shape, onStartOver }: PaneGridProps) {
  const { layout, settled } = shape;
  const drawer = useStepDrawer(mission.team.pipeline?.steps ?? NO_STEPS);
  const { dismiss } = drawer;
  const applied = appliedCount(mission);
  const twoUp = layout === 'twoUp';

  // An applied change can renumber the agents: the drawer must not point at another one.
  useEffect(() => dismiss(), [applied, dismiss]);

  // One row as tall as the screen: without it the row grows with the tallest pane's
  // content and the page scrolls, instead of each pane scrolling inside itself.
  return (
    <div className={`relative min-h-0 flex-1 ${GRID[layout]}`}>
      <Pane pane="chat" {...panePlace('chat', layout, panes.active)}>
        <ConversationPane mission={mission} showPane={panes.show} onStartOver={onStartOver} />
      </Pane>
      {twoUp && (
        <div className="col-start-2 row-start-1">
          <MissionTabs
            panes={MAIN_PANES}
            compact
            active={mainPane(panes.active)}
            onChange={panes.select}
            runStatus={mission.followed.run?.status ?? null}
          />
        </div>
      )}
      {layout === 'settling' && (
        <div className="col-start-2 grid place-items-center">
          <BusyNotice>Loading your mission…</BusyNotice>
        </div>
      )}
      <Pane pane="team" {...panePlace('team', layout, panes.active)}>
        <TeamPane
          mission={mission}
          tabbed={twoUp}
          selected={drawer.step?.order ?? null}
          onEditStep={drawer.open}
        />
      </Pane>
      <Pane pane="results" {...panePlace('results', layout, panes.active)}>
        <ResultsPane mission={mission} tabbed={twoUp} settled={settled} />
      </Pane>
      <EditDrawer mission={mission} drawer={drawer} />
    </div>
  );
}

/**
 * A change of layout (a zoom or a resize across the breakpoint) swaps one tab bar for the
 * other, and the focused tab goes with it. The focus moves to the same pane's tab in the
 * new bar, but only if it was on a tab and the swap dropped it. Returns the focus listener
 * for the workspace.
 */
function useTabFocusAcrossLayouts(layout: Layout, active: PaneId) {
  const onTab = useRef(false);
  const shown = useRef(layout);
  useLayoutEffect(() => {
    const swapped = shown.current !== layout;
    shown.current = layout;
    if (!swapped || !onTab.current || document.activeElement !== document.body) return;
    const pane = layout === 'twoUp' ? mainPane(active) : active;
    document.getElementById(paneIds(pane).tab)?.focus();
  }, [layout, active]);
  return (event: FocusEvent) => {
    onTab.current = event.target.getAttribute('role') === 'tab';
  };
}

interface MissionWorkspaceProps {
  /** The mission the address names; undefined for a new one. */
  routeId: number | undefined;
  /** "New mission": forget this one's draft and start afresh. */
  onStartOver: () => void;
}

/**
 * The mission workspace: the conversation with AIMIx, the team, and the results. A wide
 * screen shows them side by side until the team has run, then the conversation beside
 * the team or the results (tabs); a narrow screen shows one at a time, as tabs.
 */
export function MissionWorkspace({ routeId, onStartOver }: MissionWorkspaceProps) {
  const [seed] = useState(() => restoreMission(routeId));
  const mission = useMission(routeId, seed);
  const panes = usePanes();
  const shape = useMissionLayout(mission, panes);
  const noteFocus = useTabFocusAcrossLayouts(shape.layout, panes.active);

  // The screen is exactly as tall as the window: each pane scrolls inside itself, and
  // nothing may make the page scroll. Hidden text (`sr-only` is absolutely positioned)
  // is contained by the scrolling areas, decoration is clipped by the panes, and the
  // root clips what is left.
  return (
    <div
      onFocus={noteFocus}
      className={`flex min-h-0 flex-col overflow-clip text-slate-50 ${FULL_SCREEN_HEIGHT}`}
    >
      <h1 className="sr-only">Missions</h1>
      {shape.layout === 'tabs' && (
        <MissionTabs
          active={panes.active}
          onChange={panes.select}
          runStatus={mission.followed.run?.status ?? null}
        />
      )}
      <PaneGrid mission={mission} panes={panes} shape={shape} onStartOver={onStartOver} />
    </div>
  );
}
