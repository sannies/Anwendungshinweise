import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Kleine Demo-Konfiguration. Die API-URL kommt zur Laufzeit aus
// /config.json (im Deployment vom CDK gesetzt) oder aus VITE_API_BASE_URL
// für die lokale Entwicklung (.env-Datei).
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
  },
})
