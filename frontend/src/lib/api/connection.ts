import { apiRequest } from "./client";
import type { Connection } from "./types";

export const getConnection = () => apiRequest<Connection>("/api/connection");

export const connect = (body: {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
  request_timeout: number;
}) =>
  apiRequest<Connection>("/api/connect", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const disconnect = () =>
  apiRequest<Connection>("/api/disconnect", { method: "POST" });
