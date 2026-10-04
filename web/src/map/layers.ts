import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Feature, Geometry } from "geojson";
import type { BuildingProps, SiteBundle } from "../data";

type RGBA = [number, number, number, number];
const BUILDING: RGBA = [58, 70, 88, 255];
const NYCHA: RGBA = [64, 196, 170, 255];
const DC_CORE: RGBA = [255, 107, 53, 255];

export function siteLayers(b: SiteBundle) {
  const dc = b.manifest.data_center;
  return [
    new GeoJsonLayer({
      id: "context",
      data: b.context,
      filled: true,
      stroked: false,
      getFillColor: (f: Feature<Geometry, { kind: string }>) => (f.properties.kind === "water" ? [16, 38, 58, 255] : [20, 44, 32, 255]),
    }),
    new GeoJsonLayer({
      id: "streets",
      data: b.streets,
      stroked: true,
      getLineColor: [40, 52, 66, 255],
      getLineWidth: 6,
      lineWidthUnits: "meters",
    }),
    new GeoJsonLayer<BuildingProps>({
      id: "buildings",
      data: b.buildings,
      extruded: true,
      wireframe: false,
      filled: true,
      getElevation: (f: Feature<Geometry, BuildingProps>) => f.properties.height_m,
      getFillColor: (f: Feature<Geometry, BuildingProps>) => (f.properties.is_dc ? DC_CORE : f.properties.is_nycha ? NYCHA : BUILDING),
      material: { ambient: 0.35, diffuse: 0.6, shininess: 24, specularColor: [60, 64, 70] },
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 60],
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
  ];
}

export function buildingTooltip(p: BuildingProps): string {
  const rows = [
    `<b>${p.ll84_property ?? p.address ?? "Building " + p.bin}</b>`,
    p.is_dc ? `<span class="tag dc">Data center heat source</span>` : "",
    p.is_nycha ? `<span class="tag nycha">NYCHA public housing</span>` : "",
    p.units_res ? `${Math.round(p.units_res).toLocaleString()} homes` : "",
    p.heat_fuel_mmbtu ? `${Math.round(p.heat_fuel_mmbtu).toLocaleString()} MMBtu/yr heating fuel (LL84)` : "No LL84 disclosure",
    p.svi != null ? `Social vulnerability: ${(p.svi * 100).toFixed(0)}th pct (CDC SVI)` : "",
  ];
  return rows.filter(Boolean).join("<br/>");
}
