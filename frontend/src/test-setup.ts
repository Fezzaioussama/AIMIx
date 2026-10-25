import '@testing-library/jest-dom/vitest';

// jsdom has no canvas backend. Model a browser without WebGL or 2D canvas so the
// decorative effects (Aurora, ClickSpark) take their no-op path instead of logging.
HTMLCanvasElement.prototype.getContext = (() => null) as HTMLCanvasElement['getContext'];

// jsdom has no layout, so nothing ever scrolls into view. An inert observer lets the
// scroll-triggered reveals (motion's whileInView / useInView) mount without throwing;
// they simply never fire, which leaves their content in the DOM for the tests to query.
class InertObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return [];
  }
}
globalThis.IntersectionObserver ??= InertObserver as unknown as typeof IntersectionObserver;
globalThis.ResizeObserver ??= InertObserver as unknown as typeof ResizeObserver;

// jsdom has no layout and no scrolling: window.scrollTo only logs "not implemented".
window.scrollTo = (() => undefined) as typeof window.scrollTo;
