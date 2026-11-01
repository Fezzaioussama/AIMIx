import { FOCUS_RING, TOUCH } from '../../../core/ui/focus';

/**
 * A link in the report's running text ("Open in Runs", "Read it above", "All files"):
 * sky words that underline on hover, a 40px target (44px under a finger) and the focus ring.
 */
export const TEXT_LINK = `inline-flex items-center rounded-sm text-sky-300 underline-offset-4 transition-colors duration-150 ease-out hover:text-sky-200 hover:underline ${TOUCH} ${FOCUS_RING}`;

/** A button that reads as words, like the bottom "Hide what it wrote" of a long text. */
export const TEXT_BUTTON = `inline-flex cursor-pointer items-center rounded-md text-sm font-medium text-sky-300 transition-colors duration-150 ease-out hover:text-sky-200 ${TOUCH} ${FOCUS_RING}`;
