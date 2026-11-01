import { useJump } from './jump';
import { TEXT_BUTTON } from './textStyles';

/** A text longer than this gets a second "Hide …" at its end. */
const LONG_TEXT_CHARS = 1500;

interface BottomHideProps {
  /** The text the panel shows; a short one needs no second button. */
  text: string;
  label: string;
  /** Where the jump scrolls to, and the toggle that takes the focus back. */
  targetId: string;
  toggleId: string;
  onClose: () => void;
}

/**
 * The second "Hide …" at the end of a long text (the full check, an agent's own text):
 * back to its toggle first, since the panel turns inert as it closes, then closed.
 */
export function BottomHide({ text, label, targetId, toggleId, onClose }: BottomHideProps) {
  const jump = useJump();
  if (text.length <= LONG_TEXT_CHARS) return null;
  return (
    <button
      type="button"
      onClick={() => {
        jump(targetId, toggleId, 'nearest');
        onClose();
      }}
      className={`mt-3 ${TEXT_BUTTON}`}
    >
      {label}
    </button>
  );
}
