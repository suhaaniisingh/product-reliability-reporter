import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Dev proxy: the browser only talks to the Vite dev server (:5173).
    // Any request under /api is forwarded server-to-server to FastAPI (:8000),
    // so the page and API look like one origin and no CORS is needed.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
