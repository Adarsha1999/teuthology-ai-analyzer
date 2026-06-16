import type { AnalyzeResult } from "./api/types";

export type FailureCategory =
  | "product_bug"
  | "test_bug"
  | "infrastructure"
  | "environment"
  | "flaky_test"
  | "unknown";

export function formatConfidence(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

export function confidenceLevel(value: number): "high" | "medium" | "low" {
  const pct = value * 100;
  if (pct >= 80) return "high";
  if (pct >= 50) return "medium";
  return "low";
}

export function categoryLabel(cat: FailureCategory): string {
  const labels: Record<FailureCategory, string> = {
    product_bug: "Product Bug",
    test_bug: "Test Bug",
    infrastructure: "Infrastructure",
    environment: "Environment",
    flaky_test: "Flaky Test",
    unknown: "Unknown",
  };
  return labels[cat];
}

export function categoryIcon(cat: FailureCategory): string {
  const icons: Record<FailureCategory, string> = {
    product_bug: "🐛",
    test_bug: "🧪",
    infrastructure: "🖥",
    environment: "🌐",
    flaky_test: "🎲",
    unknown: "❓",
  };
  return icons[cat];
}

/** Lightweight heuristic until the API returns an explicit category. */
export function inferCategory(
  failureReason: string,
  summary: string,
  rootCause: string
): FailureCategory {
  const text = `${failureReason} ${summary} ${rootCause}`.toLowerCase();
  if (
    /flaky|intermittent|timing|race|eventually|retry.*pass/i.test(text)
  ) {
    return "flaky_test";
  }
  if (
    /apt-get|apt |dpkg|no space left|mirror|ansible|playbook|lock.*node|ssh|connection refused|timed out waiting|kernel install|yum |dnf /i.test(
      text
    )
  ) {
    return "infrastructure";
  }
  if (
    /teuthology|harness|workunit.*script|test_journal|test_cephfs|assertionerror|pytest|nose|cram|commandfailederror.*workunit/i.test(
      text
    ) &&
    !/ceph osd|ceph mon|mds rank|rados|bluestore|EINVAL.*cluster/i.test(text)
  ) {
    return "test_bug";
  }
  if (
    /ceph|mds |osd |mon |rbd |rados|erasure|bluestore|crimson|seastore|pg health|max_mds|EINVAL|health_err/i.test(
      text
    )
  ) {
    return "product_bug";
  }
  if (/environment|distro|kernel|centos|ubuntu|rocky/i.test(text)) {
    return "environment";
  }
  return "unknown";
}

export function analysisTitle(
  failureReason: string,
  summary: string,
  jobDescription: string
): string {
  const fromPulpito = failureReason.match(
    /Test failure:\s*(\S+)/i
  )?.[1];
  if (fromPulpito) {
    const suite = jobDescription.match(/tasks\/([^\s}]+)/)?.[1];
    return suite
      ? `${suite}: ${fromPulpito} failed`
      : `Teuthology test ${fromPulpito} failed`;
  }
  const first = summary.split(/[.!?]/)[0]?.trim();
  if (first && first.length > 12 && first.length < 120) return first;
  return summary.slice(0, 100) || "Teuthology job failure";
}

export function providerDisplayName(
  provider: string | undefined,
  label: string | undefined
): string {
  if (label) return label;
  if (!provider) return "AI";
  const map: Record<string, string> = {
    ollama: "Ollama",
    gemini: "Gemini",
    cursor: "Cursor",
    bob: "Bob Shell",
  };
  return map[provider] ?? provider;
}

type FailedItem = AnalyzeResult["failed_analyses"][number];

export function generateBugReport(
  item: FailedItem,
  runName: string,
  pulpitoUrl: string,
  providerName: string,
  category: FailureCategory
): string {
  const { job, analysis, failure_reason } = item;
  const lines = [
    `# Teuthology failure — job ${job.job_id}`,
    ``,
    `**Run:** ${runName}`,
    `**Pulpito:** ${pulpitoUrl}`,
    `**Category:** ${categoryLabel(category)}`,
    `**Provider:** ${providerName}`,
    `**Confidence:** ${formatConfidence(analysis.confidence)}`,
    ``,
    `## ${analysisTitle(failure_reason, analysis.summary, job.description)}`,
    ``,
    analysis.summary,
    ``,
  ];
  if (analysis.likely_root_cause) {
    lines.push(`## Root cause`, ``, analysis.likely_root_cause, ``);
  }
  if (failure_reason) {
    lines.push(`## Pulpito`, ``, failure_reason, ``);
  }
  if (analysis.evidence.length > 0) {
    lines.push(`## Evidence`, ``);
    for (const e of analysis.evidence) lines.push(`- ${e}`);
    lines.push(``);
  }
  if (analysis.next_steps.length > 0) {
    lines.push(`## Recommended actions`, ``);
    for (const s of analysis.next_steps) lines.push(`- ${s}`);
    lines.push(``);
  }
  lines.push(`## Job`, ``);
  lines.push(`- **ID:** ${job.job_id}`);
  lines.push(`- **Machine:** ${job.machine}`);
  lines.push(`- **OS:** ${job.os_type} ${job.os_version}`);
  lines.push(`- **Log:** ${item.log_url}`);
  if (item.log_truncated) {
    lines.push(`- _Note: digest built from tail of teuthology.log only._`);
  }
  return lines.join("\n");
}

export async function copyToClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}
