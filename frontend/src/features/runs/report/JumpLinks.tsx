import { DOTTED } from './dotted';
import { useJump } from './jump';
import { reportIds, type DeliverableView } from './reportModel';
import { TEXT_LINK } from './textStyles';

interface JumpLinksProps {
  runId: number;
  deliverables: DeliverableView[];
}

/**
 * "In this result: Blog post · LinkedIn post": a way down to each deliverable from the
 * header, once there is more than one. Each link scrolls to its deliverable and gives its
 * title the focus; on a touch screen the links get a line of their own, under the words.
 */
export function JumpLinks({ runId, deliverables }: JumpLinksProps) {
  const jump = useJump();
  if (deliverables.length < 2) return null;
  const ids = reportIds(runId);
  return (
    <nav
      aria-label="Deliverables in this result"
      className="mt-3 flex flex-wrap items-center gap-x-3 text-sm pointer-coarse:block"
    >
      <span className="text-slate-400">In this result:</span>
      <div className={`min-w-48 flex-1 ${DOTTED.frame}`}>
        <ul className={DOTTED.row}>
          {deliverables.map((view) => {
            const order = view.step.step_order;
            return (
              <li key={order} className={DOTTED.item}>
                <a
                  href={`#${ids.deliverable(order)}`}
                  onClick={(event) => {
                    event.preventDefault();
                    jump(ids.deliverable(order), ids.title(order));
                  }}
                  className={TEXT_LINK}
                >
                  {view.title}
                </a>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
