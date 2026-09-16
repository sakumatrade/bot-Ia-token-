/**
 * Talks only to the Broker Sakuma Local API. This is the sole network
 * boundary in the whole extension — nothing here (or anywhere else in
 * this codebase) calls a blockchain RPC, a DEX API, or any endpoint
 * outside what `manifest.json`'s `host_permissions` explicitly allow
 * (see tests/structural.test.js, which asserts that list stays narrow).
 * Spec section 39: "Safari Extension -> Local API -> Security -> Risk ->
 * Execution. Nunca: Safari -> Solana diretamente."
 */

import type { BotSummary, DashboardSummary, OpportunitySummary, ResearchReportSummary } from "./types";

export interface ExtensionSettings {
  baseUrl: string;
  apiKey: string;
}

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const DEFAULT_BASE_URL = "http://127.0.0.1:8765";

export async function loadSettings(): Promise<ExtensionSettings> {
  const stored = await browser.storage.local.get(["baseUrl", "apiKey"]);
  return {
    baseUrl: typeof stored.baseUrl === "string" && stored.baseUrl.length > 0 ? stored.baseUrl : DEFAULT_BASE_URL,
    apiKey: typeof stored.apiKey === "string" ? stored.apiKey : "",
  };
}

export async function saveSettings(settings: ExtensionSettings): Promise<void> {
  await browser.storage.local.set({ baseUrl: settings.baseUrl, apiKey: settings.apiKey });
}

async function request<T>(settings: ExtensionSettings, path: string): Promise<T> {
  if (!settings.apiKey) {
    throw new ApiError("Nenhuma chave de API configurada. Abra as Configurações da extensão.");
  }

  let response: Response;
  try {
    response = await fetch(`${settings.baseUrl}${path}`, {
      headers: { "X-API-Key": settings.apiKey },
    });
  } catch {
    throw new ApiError("Não foi possível conectar ao Broker Sakuma. O backend está rodando?");
  }

  if (response.status === 401) {
    throw new ApiError("Chave de API inválida.", 401);
  }
  if (!response.ok) {
    throw new ApiError("O Broker Sakuma não conseguiu consultar a informação agora.", response.status);
  }

  return (await response.json()) as T;
}

export function fetchDashboard(settings: ExtensionSettings): Promise<DashboardSummary> {
  return request<DashboardSummary>(settings, "/api/dashboard");
}

export function fetchBots(settings: ExtensionSettings): Promise<BotSummary[]> {
  return request<BotSummary[]>(settings, "/api/bots");
}

export function fetchOpportunities(settings: ExtensionSettings): Promise<OpportunitySummary[]> {
  return request<OpportunitySummary[]>(settings, "/api/opportunities");
}

export function fetchResearch(settings: ExtensionSettings): Promise<ResearchReportSummary[]> {
  return request<ResearchReportSummary[]>(settings, "/api/research");
}
