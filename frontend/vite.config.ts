import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    watch: {
      usePolling: true, // Docker volume mount compatibility
    },
    proxy: {
      '/api': {
        // Host-run dev/E2E override (e.g. VITE_API_PROXY=http://localhost:8011
        // for the pilgrim-e2e stack); container default stays 'api:8000'.
        target: process.env.VITE_API_PROXY || 'http://api:8000',
        changeOrigin: true,
      },
    },
  },
});
