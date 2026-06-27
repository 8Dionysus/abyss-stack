import { defineConfig } from "vite";

export default defineConfig({
  build: {
    manifest: false,
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/tos-graph.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/tos-graph[extname]",
      },
    },
  },
});
