import { GeoJsonLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Feature, Geometry, LineString } from "geojson";
import type { BuildingProps, SiteBundle } from "../data";
import type { Offtaker, ScenarioBundle, Status } from "../results";
import { esc, fmtInt, nice } from "../format";

type RGBA = [number, number, number, number];
// Building status colors (validated for CVD separation on the dark map; identity also carried by legend + tooltips).
export const COLORS = {
  dc: [255, 107, 53, 255] as RGBA,
  connected: [242, 177, 52, 255] as RGBA,
  rejected: [157, 107, 216, 255] as RGBA,
  nycha: [64, 196, 170, 255] as RGBA,
  other: [58, 70, 88, 255] as RGBA,
  selected: [255, 255, 255, 255] as RGBA,
};

export interface MapCtx {
  site: SiteBundle;
  scenario: ScenarioBundle;
  selectedId: string | null;
}

/** BIN -> offtaker, so every footprint of a campus lights up together. */
export function indexByBin(offtakers: Offtaker[]): Map<string, Offtaker> {
  const m = new Map<string, Offtaker>();
  for (const o of offtakers) for (const b of o.bins) m.set(String(b), o);
  return m;
}

function buildingColor(p: BuildingProps, o: Offtaker | undefined, selectedId: string | null): RGBA {
  if (p.is_dc) return COLORS.dc;
  if (o && o.id === selectedId) return COLORS.selected;
  const s: Status | undefined = o?.status;
  if (s === "connected") return COLORS.connected;
  if (s === "rejected") return COLORS.rejected;
  if (p.is_nycha) return COLORS.nycha;
  return COLORS.other;
}

export function siteLayers(ctx: MapCtx, byBin: Map<string, Offtaker>) {
  const dc = ctx.site.manifest.data_center;
  const pipes = ctx.scenario.network.features as Feature<LineString, { flow_mw: number; dn: string }>[];
  return [
    new GeoJsonLayer({
      id: "context",
      data: ctx.site.context,
      filled: true,
      stroked: false,
      getFillColor: (f: Feature<Geometry, { kind: string }>) => (f.properties.kind === "water" ? [16, 38, 58, 255] : [20, 44, 32, 255]),
    }),
    new GeoJsonLayer({
      id: "streets",
      data: ctx.site.streets,
      stroked: true,
      getLineColor: [40, 52, 66, 255],
      getLineWidth: 6,
      lineWidthUnits: "meters",
    }),
    new ScatterplotLayer({
      id: "dc-glow",
      data: [dc],
      getPosition: (d: typeof dc) => [d.lon, d.lat],
      getRadius: 220,
      radiusUnits: "meters",
      getFillColor: [255, 107, 53, 45],
      stroked: false,
    }),
    // Pipes: a soft glow under a bright core, width by design flow. Drawn under the buildings' roofs but over streets.
    new PathLayer({
      id: "pipes-glow",
      data: pipes,
      getPath: (f: Feature<LineString>) => f.geometry.coordinates as [number, number][],
      getWidth: (f: Feature<LineString, { flow_mw: number }>) => 22 + f.properties.flow_mw * 1.2,
      widthUnits: "meters",
      getColor: [255, 140, 60, 90],
      capRounded: true,
      jointRounded: true,
    }),
    new PathLayer({
      id: "pipes",
      data: pipes,
      getPath: (f: Feature<LineString>) => f.geometry.coordinates as [number, number][],
      getWidth: (f: Feature<LineString, { flow_mw: number }>) => 6 + f.properties.flow_mw * 0.45,
      widthUnits: "meters",
      getColor: [255, 196, 120, 255],
      capRounded: true,
      jointRounded: true,
      pickable: true,
    }),
    new GeoJsonLayer<BuildingProps>({
      id: "buildings",
      data: ctx.site.buildings,
      extruded: true,
      filled: true,
      getElevation: (f: Feature<Geometry, BuildingProps>) => f.properties.height_m,
      getFillColor: (f: Feature<Geometry, BuildingProps>) => buildingColor(f.properties, byBin.get(String(f.properties.bin)), ctx.selectedId),
      material: { ambient: 0.35, diffuse: 0.6, shininess: 24, specularColor: [60, 64, 70] },
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 60],
      updateTriggers: { getFillColor: [ctx.selectedId, ctx.scenario.results.scenario.id] },
      transitions: { getFillColor: 400 },
    }),
  ];
}

export function tooltipHtml(p: BuildingProps, o: Offtaker | undefined): string {
  if (p.is_dc) return `<b>${esc(nice(p.ll84_property ?? p.address))}</b><br/><span class="tag dc">Data center — heat source</span>`;
  if (o) {
    const st = o.status === "connected" ? `<span class="tag ok">Connected</span>` : o.status === "rejected" ? `<span class="tag no">Not chosen</span>` : "";
    return `<b>${esc(nice(o.name))}</b> <span class="muted">#${o.rank}</span><br/>${st}${o.is_nycha ? ` <span class="tag nycha">NYCHA</span>` : ""}<br/>
      ${o.units_res ? `${fmtInt(o.units_res)} homes · ` : ""}${fmtInt(o.heat_mwh)} MWh/yr heat<br/><span class="muted">Click for details</span>`;
  }
  return [
    `<b>${esc(nice(p.ll84_property ?? p.address ?? "Building"))}</b>`,
    p.is_nycha ? `<span class="tag nycha">NYCHA public housing</span>` : "",
    p.units_res ? `${fmtInt(p.units_res)} homes` : "",
    p.heat_fuel_mmbtu ? `${fmtInt(p.heat_fuel_mmbtu)} MMBtu/yr heating fuel (LL84)` : "No LL84 disclosure",
  ].filter(Boolean).join("<br/>");
}
