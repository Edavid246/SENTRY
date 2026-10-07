// Portable wrapper (npm scripts differ between cmd and sh): types from the live API.
import { spawnSync } from "node:child_process";

const api = process.env.API_URL || "http://localhost:8001";
const result = spawnSync(
  "npx",
  ["openapi-typescript", `${api}/openapi.json`, "-o", "src/lib/api-types.ts"],
  { stdio: "inherit", shell: true },
);
process.exit(result.status ?? 1);
