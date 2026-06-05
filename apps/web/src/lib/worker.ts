// Re-export dal modulo centrale lib/worker-config (fonte unica).
// Mantenuto per gli importatori esistenti (home.ts, dashboard.ts, ecc.).
export { WORKER_URL, WORKER_TIMEOUT_MS, workerGet } from "./worker-config";
