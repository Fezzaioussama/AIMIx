import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MissionTabs } from './MissionTabs';

describe('MissionTabs', () => {
  it('lists the three panes as tabs, only the chosen one reachable by Tab', () => {
    render(<MissionTabs active="team" onChange={() => {}} runStatus={null} />);

    const tabs = screen.getAllByRole('tab');

    expect(screen.getByRole('tablist', { name: 'Mission' })).toBeInTheDocument();
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Conversation', 'Team', 'Results']);
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Conversation' })).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveAttribute(
      'aria-controls',
      'mission-team-panel',
    );
  });

  it('shows the newest run’s status on the Results tab, and only there', () => {
    const { rerender } = render(<MissionTabs active="chat" onChange={() => {}} runStatus={null} />);
    expect(screen.getByRole('tab', { name: 'Results' })).toBeInTheDocument();

    rerender(<MissionTabs active="chat" onChange={() => {}} runStatus="running" />);

    expect(screen.getByRole('tab', { name: 'Results, run running' })).toHaveTextContent('Running');
    expect(screen.getByRole('tab', { name: 'Conversation' })).not.toHaveTextContent('Running');
  });

  it('chooses a pane by click', async () => {
    const onChange = vi.fn();
    render(<MissionTabs active="chat" onChange={onChange} runStatus={null} />);

    await userEvent.click(screen.getByRole('tab', { name: 'Results' }));

    expect(onChange).toHaveBeenCalledWith('results');
  });

  it('moves between tabs with the arrow keys, wrapping, and with Home and End', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<MissionTabs active="chat" onChange={onChange} runStatus={null} />);
    screen.getByRole('tab', { name: 'Conversation' }).focus();

    await user.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenLastCalledWith('team');
    expect(screen.getByRole('tab', { name: 'Team' })).toHaveFocus();

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(onChange).toHaveBeenLastCalledWith('results');
    expect(screen.getByRole('tab', { name: 'Results' })).toHaveFocus();

    await user.keyboard('{Home}');
    expect(onChange).toHaveBeenLastCalledWith('chat');
    await user.keyboard('{End}');
    expect(onChange).toHaveBeenLastCalledWith('results');
  });

  it('leaves other keys alone', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<MissionTabs active="chat" onChange={onChange} runStatus={null} />);
    screen.getByRole('tab', { name: 'Conversation' }).focus();

    await user.keyboard('a{ArrowDown}');

    expect(onChange).not.toHaveBeenCalled();
  });
});
