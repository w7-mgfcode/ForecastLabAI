import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true, // = 0.0.0.0 (LAN elérés)
    port: 5173,
    proxy: {
      // Proxy API requests to backend during development
      "/api": {
        target: "http://localhost:8123",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
    // Ha telefonról megnyitva nincs HMR (auto-reload), add hozzá:
    // hmr: { host: "10.0.0.226" }, // ide a géped LAN IP-je
  },
})