// Loads precomputed site bundles from /data/<site>/ (same origin; never external).
import type { FeatureCollection, Geometry } from "geojson";

export interface RangedParam { value: number; low: number; high: number; confidence: string; source: string }

export interface Manifest {
  site: { id: string; name: string; kind: string; bbox: [number, number, number, number] };
  data_center: { name: string; lon: number; lat: number; it_load_mw: RangedParam; existing_cooling: string };
  layers: { buildings: string; streets: string; context: string };
  labels: Record<string, string>;
}

export interface BuildingProps {
  bin: string;
  address: string | null;
  height_m: number;
  units_res: number;
  is_nycha: boolean;
  is_dc: boolean;
  has_ll84: boolean;
  ll84_property: string | null;
  svi: number | null;
  energy_burden_pct: number | null;
  heat_fuel_mmbtu: number;
}

export interface SiteBundle {
  manifest: Manifest;
  buildings: FeatureCollection<Geometry, BuildingProps>;
  streets: FeatureCollection;
  context: FeatureCollection<Geometry, { kind: "water" | "park"; name: string | null }>;
}

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Failed to load ${url} (HTTP ${r.status})`);
  return (await r.json()) as T;
}

export async function loadSite(siteId: string): Promise<SiteBundle> {
  const base = `${import.meta.env.BASE_URL}data/${siteId}/`;
  const manifest = await getJSON<Manifest>(base + "manifest.json");
  const [buildings, streets, context] = await Promise.all([
    getJSON<SiteBundle["buildings"]>(base + manifest.layers.buildings),
    getJSON<FeatureCollection>(base + manifest.layers.streets),
    getJSON<SiteBundle["context"]>(base + manifest.layers.context),
  ]);
  return { manifest, buildings, streets, context };
}
