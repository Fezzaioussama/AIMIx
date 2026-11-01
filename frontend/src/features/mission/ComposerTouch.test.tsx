import { render, screen } from '@testing-library/react';
import { useRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MissionComposer } from './MissionComposer';
import { useMissionDocuments } from './useMissionDocuments';

/** The message box with a team that can run, as the conversation pane holds it. */
function Composer() {
  const documents = useMissionDocuments();
  const field = useRef<HTMLTextAreaElement>(null);
  return (
    <MissionComposer
      ref={field}
      value=""
      onChange={vi.fn()}
      onSend={vi.fn()}
      hasTeam
      disabled={false}
      onRun={vi.fn()}
      documents={documents}
    />
  );
}

// jsdom matches no media query, so these read the classes that size each control on a
// touch screen (a coarse pointer); the browser check measures the pixels.
describe('MissionComposer on a touch screen', () => {
  it('makes “Run it” 44px tall for a finger, keeping its desktop size', () => {
    render(<Composer />);

    const run = screen.getByRole('button', { name: 'Run it' });
    expect(run).toHaveClass('pointer-coarse:min-h-11');
    expect(run).toHaveClass('px-4', 'py-2');
  });

  it('makes the box’s tools 44px square for a finger at every width', () => {
    render(<Composer />);

    const tools = [
      screen.getByTitle('Attach a document'),
      screen.getByRole('button', { name: 'Add a link' }),
      screen.getByRole('button', { name: 'Send' }),
    ];
    for (const tool of tools) {
      expect(tool).toHaveClass('size-11', 'sm:size-10', 'pointer-coarse:size-11');
    }
  });
});
