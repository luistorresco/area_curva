import { defineConfig } from 'astro/config';

export default defineConfig({
  trailingSlash: 'always',
  server: {
    port: 4321,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});