// Re-export dal modulo centrale lib/worker-config (fonte unica).
export {
  WORKER_URL,
  WORKER_TIMEOUT_MS,
  getToken,
  workerHeaders,
  unauthorized,
  workerFetch,
  workerUnreachable,
} from "@/lib/worker-config";
