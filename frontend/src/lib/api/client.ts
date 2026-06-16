const API_KEY = import.meta.env.VITE_API_KEY ?? "";

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  };

  const res = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    if (typeof detail === "string") {
      throw new Error(detail);
    }
    if (Array.isArray(detail)) {
      throw new Error(
        detail
          .map((d: { msg?: string; loc?: unknown[] }) => {
            const path = Array.isArray(d.loc) ? d.loc.slice(1).join(".") : "";
            return path ? `${path}: ${d.msg ?? "invalid"}` : (d.msg ?? "invalid");
          })
          .join("; ")
      );
    }
    throw new Error(JSON.stringify(err));
  }
  return res.json() as Promise<T>;
}
