import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    allowedHosts: ['pilgrim.keytickr.com', '.keytickr.com'], // prod subdomain üzerinden erişim
    watch: {
      usePolling: true, // Docker volume mount compatibility
    },
    proxy: {
      '/api': {
        target: 'http://pilgrim-api-1:8000',
        changeOrigin: true,
      },
    },
  },
});
