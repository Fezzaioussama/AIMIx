import '@testing-library/jest-dom/vitest';

// jsdom has no canvas backend. Model a browser without WebGL or 2D canvas so the
// decorative effects (Aurora, ClickSpark) take their no-op path instead of logging.
HTMLCanvasElement.prototype.getContext = (() => null) as HTMLCanvasElement['getContext'];
