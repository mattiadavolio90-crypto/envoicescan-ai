// Re-export dal modulo centrale lib/worker-config (fonte unica), piu' le
// costanti specifiche dell'impersonazione admin.
export {
  WORKER_URL,
  WORKER_TIMEOUT_MS,
  getToken,
  workerHeaders,
  unauthorized,
  forbidden,
  workerUnreachable,
  workerFetch,
} from "@/lib/worker-config";

export const IMPERSONATE_COOKIE = "oneflux_impersonate";
export const IMPERSONATE_BACKUP_COOKIE = "oneflux_session_backup";
