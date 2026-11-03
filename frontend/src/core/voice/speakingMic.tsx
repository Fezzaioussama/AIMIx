/**
 * A test double of `MicButton` (the real one is covered in MicButton.test.tsx): pressing
 * it hands `onTranscript` the words `SPOKEN`, as a transcribed recording would. A test
 * swaps it in with `vi.mock('<path>/core/voice/MicButton', () => import('<path>/core/voice/speakingMic'))`.
 */
export const SPOKEN = 'then a reviewer checks it';

export function MicButton({
  label,
  onTranscript,
}: {
  label: string;
  onTranscript: (text: string) => void;
}) {
  return (
    <button type="button" onClick={() => onTranscript(SPOKEN)}>
      {label}
    </button>
  );
}
