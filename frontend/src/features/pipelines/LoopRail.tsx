import { CONNECTOR_WIDTH, TERMINAL_WIDTH, columnWidth } from './graphLayout';
import type { GraphNode } from './pipelineGraph';
import type { StageGroup } from './stages';
import { timesWords, type ReviewLoop } from './stepFlow';

/**
 * The lines that show a reviewer sending work back: a row above the stages, one line from
 * the reviewer's stage back to the stage it goes to, ending in an arrow into that stage and
 * saying how many times at most. Purely decoration: a reviewer's node and its loop are also
 * described in words (its label, the legend), so the row is hidden from assistive technology.
 */

/** Where in a stage's column a loop's line starts, passes through or ends. */
type Part = 'target' | 'through' | 'reviewer';

const PART_SPAN: Record<Part, string> = {
  target: 'left-[20%] right-0',
  through: 'inset-x-0',
  reviewer: 'left-0 right-[20%]',
};

// The line is 12px down a 28px row; the stubs run on, past the 24px the stage labels use,
// to the top of the nodes.
const LINE = 'bg-purple-400/80';

function partOf(stage: number, loop: ReviewLoop): Part {
  if (stage === loop.first) return 'target';
  return stage === loop.last ? 'reviewer' : 'through';
}

function Stub({ side }: { side: string }) {
  return <span className={`absolute top-3 h-10 w-px ${LINE} ${side}`} />;
}

function ColumnLine({ part, loop }: { part: Part; loop: ReviewLoop }) {
  return (
    <>
      <span className={`absolute top-3 h-px ${LINE} ${PART_SPAN[part]}`} />
      {part === 'reviewer' && <Stub side="right-[20%]" />}
      {part === 'target' && (
        <>
          <Stub side="left-[20%]" />
          <span className="absolute top-[46px] left-[calc(20%-4px)] border-x-4 border-t-[6px] border-x-transparent border-t-purple-400" />
          <span className="absolute top-0 left-[calc(20%+8px)] text-[10px] leading-3 whitespace-nowrap text-purple-300">
            Back here up to {timesWords(loop.maxRounds)}
          </span>
        </>
      )}
    </>
  );
}

interface LoopRailProps {
  stages: StageGroup<GraphNode>[];
  loops: ReviewLoop[];
}

export function LoopRail({ stages, loops }: LoopRailProps) {
  return (
    <div className="flex h-7 min-w-max" aria-hidden="true">
      <div className={`${TERMINAL_WIDTH} shrink-0`} />
      {stages.map((stage) => {
        const loop = loops.find((item) => stage.stage >= item.first && stage.stage <= item.last);
        return (
          <div key={stage.stage} className="flex shrink-0">
            <div className={`relative ${CONNECTOR_WIDTH}`}>
              {loop && stage.stage > loop.first && (
                <span className={`absolute inset-x-0 top-3 h-px ${LINE}`} />
              )}
            </div>
            <div className={`relative ${columnWidth(stage.items.length > 1)}`}>
              {loop && <ColumnLine part={partOf(stage.stage, loop)} loop={loop} />}
            </div>
          </div>
        );
      })}
    </div>
  );
}
