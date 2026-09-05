import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// Writes straight into the directory FastAPI's StaticFiles already serves
// (airtag_sentry/web/app.py's STATIC_DIR) - same command for local dev builds
// and the Docker build stage, no separate copy step.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // injectManifest (not the simpler generateSW) so the custom
      // push/notificationclick handlers in src/sw.ts survive alongside
      // Workbox's auto-generated offline precache manifest.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      injectManifest: { injectionPoint: 'self.__WB_MANIFEST' },
      registerType: 'autoUpdate',
      manifest: {
        name: 'AirTagSentry',
        short_name: 'AirTagSentry',
        description: 'Standort-Historie und Bewegungs-Alarm für AirTags.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#000000',
        theme_color: '#0a84ff',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  build: {
    outDir: '../airtag_sentry/web/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/login': 'http://localhost:8000',
      '/logout': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    },
  },
})
