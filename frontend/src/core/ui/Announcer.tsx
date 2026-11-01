import { createPortal } from 'react-dom';

interface AnnouncerProps {
  /** What to say; '' says nothing. */
  message: string;
}

/**
 * A polite status line for screen readers, rendered into `document.body` so it is
 * heard even while the panel that owns it is hidden (a tab not shown, a pane at
 * `display:none`). Mount it empty: a live region only speaks about changes.
 */
export function Announcer({ message }: AnnouncerProps) {
  return createPortal(
    <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {message}
    </p>,
    document.body,
  );
}
