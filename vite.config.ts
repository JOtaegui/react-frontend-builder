import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Todas las rutas /api/* y /__health van al backend FastAPI
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Sin rewrite — el backend ya espera /api/osint
      },
      "/__health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});