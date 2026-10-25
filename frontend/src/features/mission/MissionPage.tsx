import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';

import { HOME_PATH, missionPath } from '../../core/routes';
import { parseMissionId } from './missionAddress';
import { forgetMission, missionKey } from './missionStorage';
import { MissionWorkspace } from './MissionWorkspace';
import { useWorkspaceIdentity } from './useWorkspaceIdentity';

/**
 * `/mission` is a new mission and `/mission/<id>` reopens a saved one (a pipeline), with
 * its team and its newest run. The workspace is rebuilt when another mission is opened
 * (see useWorkspaceIdentity); an address that is not an id starts a new mission.
 */
export function MissionPage() {
  const { pipelineId } = useParams();
  const { state } = useLocation();
  const navigate = useNavigate();
  const routeId = parseMissionId(pipelineId);
  const identity = useWorkspaceIdentity(routeId ?? undefined, state);

  if (routeId === null) return <Navigate to={HOME_PATH} replace />;

  function startOver() {
    // A new mission's draft is kept for the tab; starting over means not wanting it back.
    forgetMission(missionKey());
    if (routeId === undefined) identity.restart();
    else navigate(missionPath());
  }

  return <MissionWorkspace key={identity.epoch} routeId={routeId} onStartOver={startOver} />;
}
