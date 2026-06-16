/** Provider id from config (ollama, openai, gemini, cursor, …) */
export type LLMProvider = string;

export type ModelOption = {
  id: string;
  provider: LLMProvider;
  model: string;
  label: string;
};

export function formatModelId(provider: LLMProvider, model: string): string {
  return `${provider}:${model}`;
}

export function parseModelId(id: string): { provider: LLMProvider; model: string } {
  const idx = id.indexOf(":");
  if (idx <= 0) {
    return { provider: "ollama", model: id };
  }
  return { provider: id.slice(0, idx), model: id.slice(idx + 1) };
}

export function buildModelOptions(
  providers: Array<{
    provider: LLMProvider;
    kind?: string;
    icon: string;
    label: string;
    model?: string;
    models: string[];
  }>,
  ollamaInstalled?: string[]
): ModelOption[] {
  const out: ModelOption[] = [];
  for (const p of providers) {
    if (p.kind === "ollama" && ollamaInstalled?.length) {
      for (const model of ollamaInstalled) {
        out.push({
          id: formatModelId(p.provider, model),
          provider: p.provider,
          model,
          label: `${p.icon} ${model}`,
        });
      }
      continue;
    }
    if (p.kind === "cursor") {
      const model = p.model ?? p.models[0] ?? "composer-2";
      out.push({
        id: formatModelId(p.provider, model),
        provider: p.provider,
        model,
        label: `${p.icon} Cursor Agent (${model})`,
      });
      continue;
    }
    if (p.kind === "bob_cli") {
      const model = p.model ?? p.models[0] ?? "bob-shell-local";
      out.push({
        id: formatModelId(p.provider, model),
        provider: p.provider,
        model,
        label: `${p.icon} Bob Shell (${model})`,
      });
      continue;
    }
    for (const model of p.models) {
      out.push({
        id: formatModelId(p.provider, model),
        provider: p.provider,
        model,
        label: `${p.icon} ${model}`,
      });
    }
  }
  return out;
}
