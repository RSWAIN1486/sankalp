import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

const apiTarget = process.env.SANKALP_DEV_API_TARGET || "http://127.0.0.1:8766";

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      "/api": apiTarget
    }
  }
});
