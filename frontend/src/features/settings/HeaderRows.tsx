import { emptyHeader, keepsSavedValue } from './integrationDraft';
import type { HeaderDraft } from './integrationDraft';
import { fieldClass } from './ProviderCard';

interface HeaderRowsProps {
  idBase: string;
  rows: HeaderDraft[];
  /** The server address changed: saved values must be typed again. */
  moved: boolean;
  onChange: (rows: HeaderDraft[]) => void;
}

function savedNote(row: HeaderDraft, moved: boolean): string | null {
  if (!row.saved) return null;
  if (moved) return 'Enter the value again for the new server address.';
  if (!keepsSavedValue(row) && row.value.trim()) return 'Saving replaces the saved value.';
  if (!keepsSavedValue(row)) return 'Renamed: enter its value again.';
  const ending = row.saved.hint ? ` ending in ${row.saved.hint}` : '';
  return `Saved value${ending}. Leave it empty to keep it.`;
}

interface HeaderRowProps {
  id: string;
  row: HeaderDraft;
  position: number;
  note: string | null;
  onChange: (patch: Partial<HeaderDraft>) => void;
  onRemove: () => void;
}

function HeaderRow({ id, row, position, note, onChange, onRemove }: HeaderRowProps) {
  const noteId = `${id}-note`;
  return (
    <li className="space-y-1">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={row.name}
          aria-label={`Header ${position} name`}
          placeholder="Authorization"
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => onChange({ name: event.target.value })}
          className={`${fieldClass} sm:w-2/5`}
        />
        <div className="flex flex-1 gap-2">
          {/* A password field, so the value is masked and the browser does not offer to save it. */}
          <input
            type="password"
            value={row.value}
            aria-label={`Header ${position} value`}
            aria-describedby={note ? noteId : undefined}
            placeholder={row.saved ? 'Saved value hidden' : 'Bearer your-key'}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => onChange({ value: event.target.value })}
            className={fieldClass}
          />
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove header ${position}`}
            className="shrink-0 rounded-md px-2 text-lg leading-none text-slate-400 transition-colors hover:text-red-400 focus-visible:outline-2 focus-visible:outline-sky-400"
          >
            &times;
          </button>
        </div>
      </div>
      {note && (
        <p id={noteId} className="text-xs text-slate-400">
          {note}
        </p>
      )}
    </li>
  );
}

/** The headers sent to the server, e.g. its API key. Values are typed, never shown. */
export function HeaderRows({ idBase, rows, moved, onChange }: HeaderRowsProps) {
  function patch(index: number, change: Partial<HeaderDraft>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  }

  return (
    <fieldset>
      <legend className="mb-1 text-xs text-slate-400">Headers</legend>
      <p className="mb-2 text-xs text-slate-400">
        Most services ask for a key in a header, such as Authorization: Bearer followed by your key.
        Values are encrypted and never shown again, only their last four characters.
      </p>
      {rows.length > 0 && (
        <ul className="mb-2 space-y-3">
          {rows.map((row, index) => (
            <HeaderRow
              key={index}
              id={`${idBase}-header-${index}`}
              row={row}
              position={index + 1}
              note={savedNote(row, moved)}
              onChange={(change) => patch(index, change)}
              onRemove={() => onChange(rows.filter((_, i) => i !== index))}
            />
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => onChange([...rows, emptyHeader()])}
        className="w-full rounded-md border border-dashed border-white/20 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-sky-400/40 hover:text-sky-300 focus-visible:outline-2 focus-visible:outline-sky-400"
      >
        + Add a header
      </button>
    </fieldset>
  );
}
