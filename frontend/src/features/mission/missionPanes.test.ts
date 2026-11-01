import { describe, expect, it } from 'vitest';

import { GRID, layoutOf, mainPane, panePlace, PANE_ORDER, type PaneId } from './missionPanes';

const shown = (layout: Parameters<typeof panePlace>[1], active: PaneId) =>
  PANE_ORDER.filter((pane) => panePlace(pane, layout, active).shown);

describe('layoutOf', () => {
  it.each([
    [false, false, false, 'tabs'],
    [false, true, true, 'tabs'],
    [true, false, true, 'settling'],
    [true, true, false, 'three'],
    [true, true, true, 'twoUp'],
  ] as const)('wide %s, settled %s, a run %s: %s', (wide, settled, hasRun, layout) => {
    expect(layoutOf(wide, settled, hasRun)).toBe(layout);
  });
});

describe('panePlace', () => {
  it('shows the pane in front on a narrow screen, as a tab panel', () => {
    expect(shown('tabs', 'team')).toEqual(['team']);
    expect(panePlace('chat', 'tabs', 'chat')).toEqual({
      shown: true,
      tabbed: true,
      className: '',
    });
  });

  it('shows only the conversation while settling, and all three side by side', () => {
    expect(shown('settling', 'results')).toEqual(['chat']);
    expect(shown('three', 'chat')).toEqual(['chat', 'team', 'results']);
    expect(PANE_ORDER.map((pane) => panePlace(pane, 'three', 'chat').tabbed)).toEqual([
      false,
      false,
      false,
    ]);
  });

  it('puts the team or the results beside the conversation in two columns', () => {
    expect(shown('twoUp', 'chat')).toEqual(['chat', 'results']);
    expect(shown('twoUp', 'team')).toEqual(['chat', 'team']);
    expect(panePlace('chat', 'twoUp', 'team')).toMatchObject({ tabbed: false });
    expect(panePlace('chat', 'twoUp', 'team').className).toContain('row-span-2');
    for (const pane of ['team', 'results'] as const) {
      expect(panePlace(pane, 'twoUp', pane)).toMatchObject({
        tabbed: true,
        className: 'col-start-2 row-start-2',
      });
    }
  });

  it('sets the side panes off with a hairline only beside others', () => {
    expect(panePlace('chat', 'three', 'chat').className).toContain('border-r');
    expect(panePlace('results', 'three', 'chat').className).toContain('border-l');
    expect(panePlace('results', 'twoUp', 'results').className).not.toContain('border');
  });
});

describe('the layout grids', () => {
  it('keeps the conversation column as wide in two columns as beside three panes', () => {
    for (const layout of ['settling', 'twoUp'] as const) {
      expect(GRID[layout]).toContain('grid-cols-[20rem_minmax(0,1fr)]');
      expect(GRID[layout]).toContain('2xl:grid-cols-[24rem_minmax(0,1fr)]');
    }
    expect(GRID.three).toContain('grid-cols-[20rem_minmax(0,1fr)_22rem]');
    expect(GRID.tabs).toBe('flex');
  });

  it('shows the team in the main column only when it was picked', () => {
    expect(mainPane('team')).toBe('team');
    expect(mainPane('results')).toBe('results');
    expect(mainPane('chat')).toBe('results');
  });
});
