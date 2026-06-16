import { apiRequest } from "./client";
import type { ChatMessage } from "./types";

export const assistantChat = (body: { messages: ChatMessage[] }) =>
  apiRequest<{ reply: string; docs_url: string }>("/api/assistant/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });
