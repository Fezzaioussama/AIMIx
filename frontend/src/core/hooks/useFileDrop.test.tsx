import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useFileDrop } from './useFileDrop';

function Zone({ onFiles, enabled }: { onFiles: (files: File[]) => void; enabled?: boolean }) {
  const drop = useFileDrop(onFiles, enabled);
  return <div {...drop.zone} data-testid="zone" data-dragging={drop.dragging} />;
}

function carrying(files: File[] = []) {
  return { dataTransfer: { types: ['Files'], files } };
}

const TEXT = { dataTransfer: { types: ['text/plain'], files: [] } };

describe('useFileDrop', () => {
  it('lights up while files are held over it and hands over the ones dropped', () => {
    const onFiles = vi.fn();
    render(<Zone onFiles={onFiles} />);
    const zone = screen.getByTestId('zone');

    fireEvent.dragOver(zone, carrying());
    expect(zone).toHaveAttribute('data-dragging', 'true');

    const file = new File(['x'], 'report.pdf');
    fireEvent.drop(zone, carrying([file]));
    expect(onFiles).toHaveBeenCalledWith([file]);
    expect(zone).toHaveAttribute('data-dragging', 'false');
  });

  it('leaves anything other than files to the browser', () => {
    const onFiles = vi.fn();
    render(<Zone onFiles={onFiles} />);
    const zone = screen.getByTestId('zone');

    expect(fireEvent.dragOver(zone, TEXT)).toBe(true);
    expect(zone).toHaveAttribute('data-dragging', 'false');
    fireEvent.drop(zone, TEXT);
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('takes no files and stays dark while it is not enabled', () => {
    const onFiles = vi.fn();
    render(<Zone onFiles={onFiles} enabled={false} />);
    const zone = screen.getByTestId('zone');

    fireEvent.dragOver(zone, carrying());
    expect(zone).toHaveAttribute('data-dragging', 'false');
    expect(fireEvent.drop(zone, carrying([new File(['x'], 'a.txt')]))).toBe(false);
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('keeps a file dropped beside the zone from replacing the page, while the zone is there', () => {
    const { unmount } = render(<Zone onFiles={vi.fn()} />);

    expect(fireEvent.dragOver(document.body, carrying())).toBe(false);
    expect(fireEvent.drop(document.body, carrying([new File(['x'], 'a.pdf')]))).toBe(false);
    expect(fireEvent.drop(document.body, TEXT)).toBe(true);

    unmount();
    expect(fireEvent.drop(document.body, carrying())).toBe(true);
  });
});
