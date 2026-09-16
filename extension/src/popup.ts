import { ApiError, fetchDashboard, loadSettings } from "./apiClient";
import type { DashboardSummary } from "./types";

const STATE_LABELS: Record<string, string> = {
  ONLINE: "Funcionando normalmente",
  PAUSED: "Pausado",
  SAFE_HALT: "Parado por segurança",
  EMERGENCY_STOP: "Parada de emergência",
  UNKNOWN: "Estado desconhecido",
};

function escapeHtml(input: string): string {
  const div = document.createElement("div");
  div.textContent = input;
  return div.innerHTML;
}

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function renderDashboard(dashboard: DashboardSummary): string {
  const stateLabel = STATE_LABELS[dashboard.system_state] ?? dashboard.system_state;
  return `
    <div class="status-line">${escapeHtml(stateLabel)}</div>
    <dl class="metrics">
      <dt>Capital operacional</dt><dd>${formatUsd(dashboard.capital_operational_usd)}</dd>
      <dt>Reserva</dt><dd>${formatUsd(dashboard.reserve_usd)}</dd>
      <dt>P&amp;L do dia</dt><dd>${formatUsd(dashboard.daily_pnl_usd)}</dd>
      <dt>P&amp;L total</dt><dd>${formatUsd(dashboard.total_pnl_usd)}</dd>
      <dt>Bots ativos</dt><dd>${dashboard.active_bots}</dd>
      <dt>Bots mortos</dt><dd>${dashboard.dead_bots}</dd>
    </dl>
  `;
}

async function render(): Promise<void> {
  const root = document.getElementById("root");
  if (!root) return;

  const settings = await loadSettings();
  if (!settings.apiKey) {
    root.innerHTML = `<p class="hint">Configure a chave da API nas Configurações da extensão.</p>`;
    return;
  }

  try {
    const dashboard = await fetchDashboard(settings);
    root.innerHTML = renderDashboard(dashboard);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Ocorreu um problema inesperado.";
    root.innerHTML = `<p class="error">${escapeHtml(message)}</p>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void render();

  document.getElementById("open-dashboard")?.addEventListener("click", () => {
    void loadSettings().then((settings) => browser.tabs.create({ url: `${settings.baseUrl}/docs` }));
  });

  document.getElementById("open-settings")?.addEventListener("click", () => {
    void browser.tabs.create({ url: "options.html" });
  });
});
