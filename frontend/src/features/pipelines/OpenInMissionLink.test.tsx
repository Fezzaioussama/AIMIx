import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { OpenInMissionLink } from './OpenInMissionLink';

function link(pipelineId: number | undefined, dirty: boolean) {
  return render(
    <MemoryRouter>
      <OpenInMissionLink pipelineId={pipelineId} dirty={dirty} />
    </MemoryRouter>,
  );
}

describe('OpenInMissionLink', () => {
  it('leads a saved pipeline to its mission', () => {
    link(7, false);

    expect(screen.getByRole('link', { name: 'Open in mission view' })).toHaveAttribute(
      'href',
      '/mission/7',
    );
  });

  it('offers nothing for a pipeline that was never saved', () => {
    const { container } = link(undefined, false);

    expect(container).toBeEmptyDOMElement();
  });

  it('asks to save first rather than lose edits the mission view would not show', () => {
    link(7, true);

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByText('Save your changes to open this as a mission.')).toBeInTheDocument();
  });
});
