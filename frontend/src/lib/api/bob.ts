import { apiRequest } from "./client";

export type BobHealthResponse = {
  provider: string;
  configured: boolean;
  healthy: boolean;
  command: string | null;
  workdir: string;
  model_label: string;
  version: string | null;
  error: string | null;
};

export const getBobHealth = () =>
  apiRequest<BobHealthResponse>("/api/providers/bob/health");
