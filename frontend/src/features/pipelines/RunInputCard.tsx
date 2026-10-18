import { GlowButton } from '../../core/ui/GlowButton';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';

interface RunInputCardProps {
  input: string;
  isRunning: boolean;
  /** Unsaved edits: the server runs the stored version, so running waits for a save. */
  dirty: boolean;
  /** The pipeline exists on the server — only then is "save to run" the fix to suggest. */
  isSaved: boolean;
  message: string;
  onInputChange: (value: string) => void;
  onRun: () => void;
}

/** The builder's "Run Execution" panel: the initial input and the run button. */
export function RunInputCard({
  input,
  isRunning,
  dirty,
  isSaved,
  message,
  onInputChange,
  onRun,
}: RunInputCardProps) {
  return (
    <SpotlightCard className="mt-8 p-8">
      <h2 className="mb-4 text-xl font-semibold">Run Execution</h2>
      <textarea
        value={input}
        disabled={isRunning}
        placeholder="Enter your initial input here..."
        onChange={(event) => onInputChange(event.target.value)}
        className="mb-4 h-28 w-full resize-y rounded-xl border border-white/10 bg-slate-950/60 p-4 text-sm transition-[border-color,box-shadow] outline-none focus:border-sky-400/60 focus:shadow-[0_0_0_4px_rgba(56,189,248,0.1)]"
      />
      <GlowButton size="lg" onClick={onRun} busy={isRunning} disabled={!input.trim() || dirty}>
        {isRunning ? 'Executing…' : 'Run Pipeline'}
      </GlowButton>
      {dirty && isSaved && (
        <p className="mt-3 text-xs text-sky-300">Save your changes to run this version.</p>
      )}
      {message && <p className="mt-4 text-sm text-amber-300">{message}</p>}
    </SpotlightCard>
  );
}
