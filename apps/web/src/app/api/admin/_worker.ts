// Re-export dal modulo centrale lib/worker-config (fonte unica), piu' le
// costanti specifiche dell'impersonazione admin.
export {
  WORKER_URL,
  getToken,
  workerHeaders,
  unauthorized,
  forbidden,
  workerUnreachable,
} from "@/lib/worker-config";

export const IMPERSONATE_COOKIE = "oneflux_impersonate";
export const IMPERSONATE_BACKUP_COOKIE = "oneflux_session_backup";
