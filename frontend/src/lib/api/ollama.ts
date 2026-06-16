import { apiRequest } from "./client";

export type OllamaModel = {
  name: string;
  size?: string | null;
  modified_at?: string | null;
  recommended_for: string[];
};

export type OllamaModelsResponse = {
  models: OllamaModel[];
  default_model: string;
  selected_model: string;
  healthy: boolean;
  base_url: string;
};

export type OllamaHealthResponse = {
  healthy: boolean;
  base_url: string;
  error?: string | null;
};

export const getOllamaModels = () =>
  apiRequest<OllamaModelsResponse>("/api/ollama/models");

export const getOllamaHealth = () =>
  apiRequest<OllamaHealthResponse>("/api/ollama/health");
