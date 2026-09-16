/**
 * Mirrors the Local API's response shapes (backend/src/broker_sakuma/api/schemas.py).
 * Kept as plain data types — this extension never constructs or signs a
 * blockchain transaction, so there is nothing here beyond what the
 * dashboard displays.
 */

export type SystemState = "ONLINE" | "PAUSED" | "SAFE_HALT" | "EMERGENCY_STOP" | "UNKNOWN";

export interface DashboardSummary {
  system_state: SystemState;
  capital_operational_usd: number;
  reserve_usd: number;
  capital_borrowed_usd: number;
  daily_pnl_usd: number;
  total_pnl_usd: number;
  active_bots: number;
  dead_bots: number;
  resurrected_bots: number;
  new_theses: number;
  approved_theses: number;
  theses_in_research: number;
  simulated_trades: number;
  success_rate: number;
  max_drawdown_pct: number;
  unacknowledged_alerts: number;
}

export interface BotSummary {
  id: string;
  name: string;
  version: string;
  state: string;
  generation: number;
  parent_id: string | null;
  capital_operational_usd: number;
  reserve_usd: number;
  capital_borrowed_usd: number;
  cumulative_pnl_usd: number;
  drawdown_pct: number;
  trades_count: number;
  theses_tested_count: number;
}

export interface OpportunitySummary {
  id: string;
  source: string;
  classification: string;
  status: string;
  risk_score: number | null;
  description: string | null;
  created_at: string;
}

export interface ResearchReportSummary {
  id: string;
  title: string;
  status: string;
  summary: string | null;
  created_at: string;
}
