// Types and loader for one precomputed scenario (engine output in /data/<site>/<scenario>/).
import type { FeatureCollection, LineString } from "geojson";

export const DIMS = ["temperature", "capacity", "timing", "seasonality", "continuity", "proximity", "equity"] as const;
export type Dim = (typeof DIMS)[number];
export const DIM_LABEL: Record<Dim, string> = {
  temperature: "Temperature", capacity: "Capacity", timing: "Timing", seasonality: "Seasonality",
  continuity: "Continuity", proximity: "Proximity", equity: "Equity",
};
export const DIM_HELP: Record<Dim, string> = {
  temperature: "Heat-pump COP at the building's required supply temperature (CoolProp cycle model)",
  capacity: "Annual heat demand (measured LL84 fuel → useful heat), log scale",
  timing: "Load factor: steady 24/7 demand matches a steady data-center source",
  seasonality: "Summer demand vs annual average — hot water keeps heat useful year-round",
  continuity: "Long-term anchor stability of the owner/occupant type",
  proximity: "Distance from the data center",
  equity: "CDC Social Vulnerability Index of the tract; NYCHA public housing = 1.0",
};

export type Status = "connected" | "rejected" | "not_shortlisted";

export interface Offtaker {
  id: string; name: string; rank: number; ll84_type: string | null; address: string | null; primary_fuel: string;
  heat_mwh: number; peak_mw: number; units_res: number; units_source: string; is_nycha: boolean; svi: number | null;
  distance_m: number; t_req_avg_c: number; cop_at_building: number; needs_steam_conversion: boolean;
  total_score: number; fit_score: number; rationale: string; lon: number; lat: number; bins: string[];
  status: Status; reason: string | null;
  s_temperature: number; s_capacity: number; s_timing: number; s_seasonality: number; s_continuity: number;
  s_proximity: number; s_equity: number;
  avoided_cost_per_mwh?: number; hp_elec_cost_per_mwh?: number; dc_cooling_savings_per_mwh?: number;
  ll97_value_per_mwh?: number; equity_value_per_mwh?: number; net_value_per_mwh?: number;
  annual_value_usd?: number; delivered_mwh?: number; conn_capex_usd?: number;
}

export interface Screened { id: string; name: string; ll84_type: string | null; heat_mwh: number; screen_reason: string }

export interface Results {
  scenario: { id: string; cooling: string; it_growth: number; equity_weight: number };
  it_load: { value: number; low: number; high: number; method: string; source: string; confidence: string; steps?: Record<string, number> };
  supply: { it_load_mw_mean: number; q_src_mw_mean: number; q_src_gwh: number; t_src_in_c: number; t_src_out_c: number };
  design: { hp_mw: number; hp_max_mw: number; solve_seconds: number; status: string; mip_gap: number; graph_nodes: number;
    graph_edges: number; candidates: number; binaries: number; pipe_km: number };
  economics: {
    capex_usd: Record<"total" | "pipes" | "heat_pump" | "connections", number>;
    annual_usd: Record<string, number>;
    energy_mwh: Record<string, number>;
    kpis: Record<string, number>;
  };
  validation: { development: string; months: number[]; modeled_mwh: number[]; metered_mwh: number[]; r2: number;
    annual_modeled_mwh: number; annual_metered_mwh: number; steam_price_usd_per_mmbtu: number; source: string };
  cop: { avg: number; min: number; max: number };
  counts: { candidates_scored: number; eligible: number; screened_out: number; shortlisted_for_milp: number };
}

export interface ScenarioBundle {
  results: Results;
  offtakers: Offtaker[];
  screened: Screened[];
  network: FeatureCollection<LineString, { flow_mw: number; dn: string; length_m: number }>;
}

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url} (HTTP ${r.status})`);
  return (await r.json()) as T;
}

export async function loadScenario(siteId: string, scenarioId: string): Promise<ScenarioBundle> {
  const base = `${import.meta.env.BASE_URL}data/${siteId}/${scenarioId}/`;
  const [results, off, network] = await Promise.all([
    getJSON<Results>(base + "results.json"),
    getJSON<{ offtakers: Offtaker[]; screened_out: Screened[] }>(base + "offtakers.json"),
    getJSON<ScenarioBundle["network"]>(base + "network.geojson"),
  ]);
  return { results, offtakers: off.offtakers, screened: off.screened_out, network };
}
