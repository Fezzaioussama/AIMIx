import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderMission } from './testRender';
import { COMMON_ROUTES, SAVED, routeFetch } from './testData';

const log = () => screen.getByRole('log', { name: 'Conversation with AIMIx' });

describe('the run form in the conversation', () => {
  // jsdom lays nothing out and has no scrollIntoView: record who asked to be shown.
  const shown: Element[] = [];
  const options: (ScrollIntoViewOptions | boolean | undefined)[] = [];

  beforeEach(() => {
    window.sessionStorage.clear();
    Element.prototype.scrollIntoView = vi.fn(function (
      this: Element,
      arg?: ScrollIntoViewOptions | boolean,
    ) {
      shown.push(this);
      options.push(arg);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
    shown.length = 0;
    options.length = 0;
  });

  it('shows the field it focuses, label included, once the log has followed its end', async () => {
    const user = userEvent.setup();
    routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': SAVED });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await user.click(screen.getByRole('button', { name: 'Run it' }));

    const field = await within(log()).findByLabelText(/Your company/);
    expect(field).toHaveFocus();
    // The log scrolls to its new end first; the field is shown after that, so it stays.
    await waitFor(() => expect(shown.at(-1)).toBe(field));
    expect(options.at(-1)).toEqual({ block: 'nearest' });
    // Its scroll margin keeps the label above it in view.
    expect(field.className).toMatch(/\bscroll-mt-\d+\b/);
  });
});
