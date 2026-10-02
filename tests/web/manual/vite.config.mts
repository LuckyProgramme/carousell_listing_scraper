import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

// Isolated browser fixture. Never added to Next.js routes or deployed.
export default defineConfig({
  root: fileURLToPath(new URL("./", import.meta.url)),
  envDir: false,
  resolve: { alias: [
    { find: "@/lib/supabase/client", replacement: fileURLToPath(new URL("./mock-client.ts", import.meta.url)) },
    { find: "@", replacement: fileURLToPath(new URL("../../../", import.meta.url)) },
  ] },
  server: { host: "127.0.0.1", port: 3108, strictPort: true },
});
