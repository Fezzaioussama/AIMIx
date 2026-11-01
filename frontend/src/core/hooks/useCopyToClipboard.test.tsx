import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useCopyToClipboard } from './useCopyToClipboard';

/** jsdom has no ClipboardItem: this one keeps what it was given. */
class FakeClipboardItem {
  constructor(readonly items: Record<string, Blob>) {}
}

/** jsdom's Blob has no text(); FileReader reads it (with real timers). */
function textOf(blob: Blob): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });
}

const CONTENT = { html: '<p><strong>Draft</strong></p>', text: 'Draft' };

let clipboard: { write: ReturnType<typeof vi.fn>; writeText: ReturnType<typeof vi.fn> };

beforeEach(() => {
  vi.useFakeTimers();
  clipboard = { write: vi.fn().mockResolvedValue(undefined), writeText: vi.fn() };
  clipboard.writeText.mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true });
  vi.stubGlobal('ClipboardItem', FakeClipboardItem);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'clipboard');
});

describe('useCopyToClipboard', () => {
  it('copies formatted and plain text in one item, then goes back to idle', async () => {
    const { result } = renderHook(() => useCopyToClipboard());
    expect(result.current.status).toBe('idle');

    await act(() => result.current.copyRich(CONTENT));

    expect(clipboard.write).toHaveBeenCalledTimes(1);
    const [items] = clipboard.write.mock.calls[0] as [FakeClipboardItem[]];
    expect(items).toHaveLength(1);
    const { 'text/html': html, 'text/plain': text } = items[0].items;
    expect(html.type).toBe('text/html');
    expect(text.type).toBe('text/plain');
    expect(clipboard.writeText).not.toHaveBeenCalled();
    expect(result.current.status).toBe('copied');

    act(() => vi.advanceTimersByTime(1499));
    expect(result.current.status).toBe('copied');
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.status).toBe('idle');

    vi.useRealTimers();
    expect(await textOf(html)).toBe(CONTENT.html);
    expect(await textOf(text)).toBe('Draft');
  });

  it('copies the plain text where the browser has no ClipboardItem', async () => {
    vi.stubGlobal('ClipboardItem', undefined);
    const { result } = renderHook(() => useCopyToClipboard());

    await act(() => result.current.copyRich(CONTENT));

    expect(clipboard.write).not.toHaveBeenCalled();
    expect(clipboard.writeText).toHaveBeenCalledWith('Draft');
    expect(result.current.status).toBe('copied');
  });

  it('falls back to plain text when formatted content is refused', async () => {
    clipboard.write.mockRejectedValue(new DOMException('Denied', 'NotAllowedError'));
    const { result } = renderHook(() => useCopyToClipboard());

    await act(() => result.current.copyRich(CONTENT));

    expect(clipboard.writeText).toHaveBeenCalledWith('Draft');
    expect(result.current.status).toBe('copied');
  });

  it('says it failed when both are refused, and stays failed', async () => {
    clipboard.write.mockRejectedValue(new DOMException('Denied', 'NotAllowedError'));
    clipboard.writeText.mockRejectedValue(new DOMException('Denied', 'NotAllowedError'));
    const { result } = renderHook(() => useCopyToClipboard());

    await act(() => result.current.copyRich(CONTENT));

    expect(result.current.status).toBe('failed');
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current.status).toBe('failed');
  });

  it('says it failed when the page has no clipboard at all', async () => {
    Reflect.deleteProperty(navigator, 'clipboard');
    const { result } = renderHook(() => useCopyToClipboard());

    await act(() => result.current.copyRich(CONTENT));

    expect(result.current.status).toBe('failed');
  });

  it('copies plain text alone', async () => {
    const { result } = renderHook(() => useCopyToClipboard());

    await act(() => result.current.copy('Notes'));

    expect(clipboard.writeText).toHaveBeenCalledWith('Notes');
    expect(result.current.status).toBe('copied');
  });

  it('clears its timer on unmount', async () => {
    const { result, unmount } = renderHook(() => useCopyToClipboard());
    await act(() => result.current.copyRich(CONTENT));
    expect(vi.getTimerCount()).toBe(1);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });

  it('starts no timer when the copy finishes after unmount', async () => {
    let finish = () => {};
    clipboard.write.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    const { result, unmount } = renderHook(() => useCopyToClipboard());
    const copying = result.current.copyRich(CONTENT);

    unmount();
    finish();
    await copying;

    expect(vi.getTimerCount()).toBe(0);
  });
});
