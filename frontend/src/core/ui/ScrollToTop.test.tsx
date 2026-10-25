import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ScrollToTop } from './ScrollToTop';

function renderApp() {
  return render(
    <MemoryRouter initialEntries={['/runs']}>
      <ScrollToTop />
      <nav>
        <Link to="/runs/7">One run</Link>
        <Link to="/files">Files</Link>
      </nav>
      <Routes>
        <Route path="*" element={null} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ScrollToTop', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens a new screen at its top', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    const { getByRole } = renderApp();
    scrollTo.mockClear();

    await userEvent.click(getByRole('link', { name: 'Files' }));

    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalledWith({ top: 0 });
  });

  it('keeps the position while moving within one screen', async () => {
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    const { getByRole } = renderApp();
    scrollTo.mockClear();

    await userEvent.click(getByRole('link', { name: 'One run' }));

    expect(scrollTo).not.toHaveBeenCalled();
  });
});
