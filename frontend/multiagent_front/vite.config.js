import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  envPrefix: "VITE_",
  server: {
    host: "0.0.0.0",
    port: 5174,
    proxy: {
      // 全部后端请求代理到 hostapi (docker 13002)
      "/api": { target: "http://localhost:13002", changeOrigin: true },
      "/v2": { target: "http://localhost:13002", changeOrigin: true },
      "/auth": { target: "http://localhost:13002", changeOrigin: true },
      "/health": { target: "http://localhost:13002", changeOrigin: true },
    },
  },
});
