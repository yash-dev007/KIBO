import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, "electron/main/index.ts"),
      },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, "electron/preload/index.ts"),
        output: {
          // Electron sandboxed preload requires CommonJS — override the ESM
          // default forced by "type":"module" in package.json.
          format: "cjs",
          entryFileNames: "[name].js",
        },
      },
    },
  },
  renderer: {
    root: resolve(__dirname),
    plugins: [react(), tailwindcss()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, "index.html"),
      },
    },
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      fs: {
        // Allow /@fs/ routes to reach the shared assets folder outside frontend/
        allow: [resolve(__dirname, "..")],
      },
    },
  },
});
