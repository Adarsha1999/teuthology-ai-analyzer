import { apiRequest } from "./client";
import type { AnalyzeResult, HistoryEntry } from "./types";

export const getHistory = () => apiRequest<HistoryEntry[]>("/api/history");

export const getCachedAnalysis = (runName: string) =>
  apiRequest<AnalyzeResult>(
    `/api/history/${encodeURIComponent(runName)}/analysis`
  );

interface TaskResponse {
  task_id: string;
  status: "running" | "complete";
  result?: AnalyzeResult;
}

async function pollForResult(taskId: string, abortSignal?: AbortSignal): Promise<AnalyzeResult> {
  const POLL_INTERVAL_MS = 3000;
  const MAX_POLLS = 200;

  for (let i = 0; i < MAX_POLLS; i++) {
    if (abortSignal?.aborted) throw new Error("Analysis cancelled");

    const resp = await apiRequest<TaskResponse>(
      `/api/analyze/status/${taskId}`
    );

    if (resp.status === "complete" && resp.result) {
      return resp.result;
    }

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }

  throw new Error("Analysis timed out — please try again.");
}

export const analyze = async (body: {
  run_url: string;
  include_dead: boolean;
  max_failures: number;
  show_digest: boolean;
}): Promise<AnalyzeResult> => {
  const task = await apiRequest<TaskResponse>("/api/analyze", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return pollForResult(task.task_id);
};

export const analyzeLocal = async (body: {
  run_path: string;
  include_dead: boolean;
  max_failures: number;
  show_digest: boolean;
  job_ids?: string[];
  read_mode?: "full" | "tail";
}): Promise<AnalyzeResult> => {
  const task = await apiRequest<TaskResponse>("/api/analyze-local", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return pollForResult(task.task_id);
};
