import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
    watch: {
      // Polling keeps a CPU core busy; only needed on network drives / WSL2
      // cross-filesystem setups. Opt in with VITE_USE_POLLING=1 if HMR misses changes.
      usePolling: !!process.env.VITE_USE_POLLING,
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: [
        'node_modules',
        'src/test-setup.ts',
        '**/*.test.{ts,tsx}',
        '**/*.d.ts',
      ],
    },
  },
} as import('vite').UserConfigExport)
