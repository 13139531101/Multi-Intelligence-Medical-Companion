import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  envPrefix: "VITE_",
  server: {
    host: "0.0.0.0",
    port: 5174,
    proxy: {
      // 阶段48-25: CopilotKit runtime + API 全部代理到 hostapi (docker 13002)
      "/api": {
        target: "http://localhost:13002",
        changeOrigin: true,
      },
      "/v2": {
        target: "http://localhost:13002",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://localhost:13002",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:13002",
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    // 阶段48-25: @a2ui/web_core 用 ES2025 import attribute (`with { type: 'json' }`),
    // 旧版 esbuild 不支持. 我们不用它 (只 react-core + react-ui), 排除掉.
    exclude: ["@a2ui/web_core"],
  },
});
