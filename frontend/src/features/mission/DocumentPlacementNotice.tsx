import { formatCount } from '../../core/usageFormat';
import { ATTACH_CONTROL } from '../pipelines/attachStyles';
import { inputLabel, RUN_INPUT_MAX_LENGTH } from '../pipelines/pipelineInputs';
import type { DocumentPlacement } from './missionDocuments';

/** Why the box's documents are not in the open run form, naming them. */
export function placementText({ names, choices }: DocumentPlacement): string {
  const one = names.length === 1;
  const them = one ? 'it' : 'them';
  const left = `${names.join(', ')} ${one ? 'isn’t' : 'aren’t'} in the run form`;
  if (choices.length > 0) {
    return `${left}: your team has no input meant for documents. Put ${them} in:`;
  }
  return (
    `${left}: with ${them}, the run’s inputs would pass ` +
    `${formatCount(RUN_INPUT_MAX_LENGTH)} characters. ` +
    `${one ? 'It stays' : 'They stay'} here for your next run.`
  );
}

interface PlacementChoicesProps {
  placement: DocumentPlacement;
  /** The buttons go once the documents are placed, so focus must go somewhere. */
  onPlaced: () => void;
}

/** One button per input the documents can go in, for a team with none meant for them. */
export function PlacementChoices({ placement, onPlaced }: PlacementChoicesProps) {
  if (placement.choices.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5 px-1 text-xs">
      {placement.choices.map((field) => (
        <button
          key={field.name}
          type="button"
          onClick={() => {
            placement.place(field.name);
            onPlaced();
          }}
          className={ATTACH_CONTROL}
        >
          {inputLabel(field)}
        </button>
      ))}
    </div>
  );
}
