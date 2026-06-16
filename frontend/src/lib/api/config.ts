import { apiRequest } from "./client";
import type { AppConfig } from "./types";

export const getConfig = () => apiRequest<AppConfig>("/api/config");
