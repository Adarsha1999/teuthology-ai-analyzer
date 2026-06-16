from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LLMProvider = str


class ProviderConfigOut(BaseModel):
    provider: str
    kind: str
    label: str
    icon: str
    tag: str
    base_url: str = ""
    model: str
    models: list[str]
    request_timeout: int = 600
    has_api_key: bool = False
    requires_api_key: bool = False
    requires_base_url: bool = False
    api_key_env: str = ""


class ConfigOut(BaseModel):
    default_provider: str
    providers: list[ProviderConfigOut]
    pulpito_base: str


class ConnectIn(BaseModel):
    provider: str = "ollama"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    request_timeout: int = 600


class ConnectionOut(BaseModel):
    connected: bool
    provider: str | None = "ollama"
    label: str | None = "Ollama"
    icon: str | None = "🦙"
    model: str | None = None


class AnalyzeIn(BaseModel):
    run_url: str
    include_dead: bool = False
    max_failures: int = Field(default=10, ge=1, le=50)
    show_digest: bool = False


class AnalyzeLocalIn(BaseModel):
    run_path: str
    include_dead: bool = False
    max_failures: int = Field(default=10, ge=1, le=50)
    show_digest: bool = False
    job_ids: list[str] | None = None
    read_mode: Literal["full", "tail"] = "full"


class JobOut(BaseModel):
    job_id: str
    description: str
    status: str
    machine: str
    os_type: str
    os_version: str


class RunMetricsOut(BaseModel):
    total: int
    pass_count: int
    fail_count: int
    dead_count: int
    queued_count: int
    pass_rate: int


class AnalysisOut(BaseModel):
    summary: str
    likely_root_cause: str
    evidence: list[str]
    next_steps: list[str]
    confidence: float


class FailedJobOut(BaseModel):
    job: JobOut
    failure_reason: str
    log_url: str
    log_empty: bool
    log_truncated: bool
    log_source: str = "http"
    log_size_bytes: int | None = None
    digest: str | None = None
    analysis: AnalysisOut


class AnalyzeOut(BaseModel):
    run_name: str
    pulpito_url: str
    metrics: RunMetricsOut
    jobs: list[JobOut]
    failed_analyses: list[FailedJobOut]


class HistoryEntry(BaseModel):
    id: int
    run_name: str
    pass_count: int
    fail_count: int
    total: int
    analyzed: bool = False


class AssistantMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=32000)


class AssistantChatIn(BaseModel):
    messages: list[AssistantMessageIn] = Field(min_length=1, max_length=50)


class AssistantChatOut(BaseModel):
    reply: str
    docs_url: str = "https://docs.ceph.com/projects/teuthology/en/latest/README.html"
