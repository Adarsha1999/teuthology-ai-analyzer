export type LLMProvider = string;

export interface ProviderConfig {
  provider: LLMProvider;
  kind: string;
  label: string;
  icon: string;
  tag: string;
  base_url: string;
  model: string;
  models: string[];
  request_timeout: number;
  has_api_key: boolean;
  requires_api_key: boolean;
  requires_base_url: boolean;
  api_key_env: string;
}

export interface AppConfig {
  default_provider: LLMProvider;
  providers: ProviderConfig[];
  pulpito_base: string;
}

export interface Connection {
  connected: boolean;
  provider?: LLMProvider;
  label?: string;
  icon?: string;
  model?: string;
}

export interface HistoryEntry {
  id: number;
  run_name: string;
  pass_count: number;
  fail_count: number;
  total: number;
  analyzed: boolean;
}

export interface AnalyzeResult {
  run_name: string;
  pulpito_url: string;
  metrics: {
    total: number;
    pass_count: number;
    fail_count: number;
    dead_count: number;
    queued_count: number;
    pass_rate: number;
  };
  jobs: Array<{
    job_id: string;
    description: string;
    status: string;
    machine: string;
    os_type: string;
    os_version: string;
  }>;
  failed_analyses: Array<{
    job: {
      job_id: string;
      description: string;
      status: string;
      machine: string;
      os_type: string;
      os_version: string;
    };
    failure_reason: string;
    log_url: string;
    log_empty: boolean;
    log_truncated: boolean;
    log_source?: "http" | "local";
    log_size_bytes?: number | null;
    digest: string | null;
    analysis: {
      summary: string;
      likely_root_cause: string;
      evidence: string[];
      next_steps: string[];
      confidence: number;
    };
  }>;
}

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};
