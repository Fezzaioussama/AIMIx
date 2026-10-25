import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// The dev server proxies /api to the FastAPI backend so the browser sees a single origin
// and no CORS or absolute backend URL ever reaches the client bundle.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 4200,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    css: true,
    // jsdom tests type into forms and load route chunks lazily: on a busy machine or a
    // two-core CI runner that takes longer than vitest's default 5 s.
    testTimeout: 20_000,
  },
});
