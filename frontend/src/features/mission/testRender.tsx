import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { MissionPage } from './MissionPage';

/** Shows the router's location, for tests of where a screen sends the person. */
export function LocationProbe() {
  const { pathname, state } = useLocation();
  return (
    <output data-testid="location" data-state={JSON.stringify(state)}>
      {pathname}
    </output>
  );
}

/** The mission page at `path`, as the app routes it. */
export function renderMission(path = '/mission', extra: ReactNode = null) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/mission/:pipelineId?" element={<MissionPage />} />
        <Route path="*" element={null} />
      </Routes>
      <LocationProbe />
      {extra}
    </MemoryRouter>,
  );
}
