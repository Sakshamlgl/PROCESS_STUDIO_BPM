import { defineConfig } from "vite";
export default defineConfig({
  server: { host: "127.0.0.1", proxy: { "/api": "http://127.0.0.1:8765" } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/diagram-js")) return "diagram-engine";
          if (id.includes("/node_modules/bpmn-js/")) return "bpmn-editor";
          if (id.includes("/node_modules/bpmn-moddle/"))
            return "bpmn-metamodel";
          if (id.includes("/node_modules/")) return "vendor";
        },
      },
    },
  },
});
