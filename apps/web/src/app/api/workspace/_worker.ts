// Re-export dal modulo centrale lib/worker-config (fonte unica).
export {
  WORKER_URL,
  getToken,
  workerHeaders,
  unauthorized,
  workerFetch,
  workerUnreachable,
} from "@/lib/worker-config";
