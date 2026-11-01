/**
 * The workspace files a run may have saved (pure). Files carry no run id, and a run's tool
 * calls only their name and status, so "saved during this run" means saved while it
 * worked: modified inside its time window, give or take a little clock slack.
 */
import type { Run, WorkspaceFile } from '../../../core/api/types';
import { isPicture } from '../../files/fileFormat';

/**
 * The built-in tools that save files to the workspace. Mirrors SAVE_ARTIFACT,
 * GENERATE_IMAGE, FIND_OBJECTS and RUN_PYTHON in backend/api/services/toolbox/tools.py.
 */
export const FILE_SAVING_TOOLS: readonly string[] = [
  'save_artifact',
  'generate_image',
  'find_objects',
  'run_python',
];

/** How far a file's time may sit outside the run's window and still count. */
const WINDOW_SLACK_MS = 2000;

/** Whether the run has started and some step may use a tool that saves files (null: all). */
export function mayHaveSavedFiles(run: Run): boolean {
  if (run.started_at === null) return false;
  return run.definition.steps.some(
    (step) =>
      step.allowed_tools === null ||
      step.allowed_tools.some((tool) => FILE_SAVING_TOOLS.includes(tool)),
  );
}

/**
 * The files modified while the run worked, pictures first, then newest first. The window
 * stays open while the run works: the files' times are the server's, and the browser's
 * clock may run behind it.
 */
export function savedDuringRun(files: WorkspaceFile[], run: Run): WorkspaceFile[] {
  if (run.started_at === null) return [];
  const from = Date.parse(run.started_at) - WINDOW_SLACK_MS;
  const until = run.finished_at === null ? Infinity : Date.parse(run.finished_at) + WINDOW_SLACK_MS;
  return files
    .filter((file) => {
      const modified = Date.parse(file.modified_at);
      return modified >= from && modified <= until;
    })
    .sort(
      (a, b) =>
        Number(isPicture(b.type)) - Number(isPicture(a.type)) ||
        Date.parse(b.modified_at) - Date.parse(a.modified_at),
    );
}
