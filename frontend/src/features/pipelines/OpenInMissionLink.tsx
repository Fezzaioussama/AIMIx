import { Rocket } from 'lucide-react';
import { Link } from 'react-router-dom';

import { missionPath } from '../../core/routes';
import { SECONDARY_BUTTON } from './buttonStyles';

interface OpenInMissionLinkProps {
  /** The open pipeline's id; none until it is saved. */
  pipelineId: number | undefined;
  /** Edits not yet saved: the mission view opens the saved version, so they would be lost. */
  dirty: boolean;
}

/** From the builder (the advanced mode) to the same pipeline as a mission. */
export function OpenInMissionLink({ pipelineId, dirty }: OpenInMissionLinkProps) {
  if (pipelineId === undefined) return null;
  if (dirty) {
    return <p className="text-xs text-slate-400">Save your changes to open this as a mission.</p>;
  }
  return (
    <Link to={missionPath(pipelineId)} className={SECONDARY_BUTTON}>
      <Rocket aria-hidden="true" className="size-4" />
      Open in mission view
    </Link>
  );
}
