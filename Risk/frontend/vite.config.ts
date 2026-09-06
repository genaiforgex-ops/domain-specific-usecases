import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Under compose the API is a sibling container — "localhost" would be
        // this container — so the target is overridable with the service name.
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8002",
        changeOrigin: true,
      },
    },
  },
});
