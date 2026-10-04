import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import * as maplibregl from "maplibre-gl";
// Bundle MapLibre's module worker locally so the map works offline in production builds.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { LightingEffect, AmbientLight, DirectionalLight } from "@deck.gl/core";
import { loadSite, type BuildingProps, type SiteBundle } from "./data";
import { loadScenario, type ScenarioBundle } from "./results";
import { indexByBin, siteLayers, tooltipHtml, COLORS } from "./map/layers";
import { ui } from "./state";
import { renderKpis } from "./ui/kpis";
import { renderRanking } from "./ui/ranking";
import { renderDetail } from "./ui/detail";
import { renderEvidence } from "./ui/evidence";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

const params = new URLSearchParams(location.search);
const SITE = params.get("site") ?? "site1_chelsea";
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const loading = $("loading");

function showError(msg: string) {
  loading.classList.remove("hidden");
  loading.innerHTML = `<div class="error-card"><b>Could not load this site</b><br/>${msg}<br/><small>Run <code>make simulate</code> to regenerate data.</small></div>`;
}

const rgb = (c: number[]) => `rgb(${c[0]},${c[1]},${c[2]})`;
function renderLegend() {
  const items: [string, number[]][] = [
    ["Data center (heat source)", COLORS.dc], ["Connected by optimizer", COLORS.connected],
    ["Considered, not chosen", COLORS.rejected], ["NYCHA public housing", COLORS.nycha],
  ];
  $("legend").innerHTML = items.map(([l, c]) => `<span class="lg"><span class="sw" style="background:${rgb(c)}"></span>${l}</span>`).join("") +
    `<span class="lg"><span class="sw pipe"></span>Heat network (width = design flow)</span>`;
}

async function start() {
  const site: SiteBundle = await loadSite(SITE);
  const scenarioId = params.get("scenario") ?? site.manifest.default_scenario;
  const scenario: ScenarioBundle = await loadScenario(SITE, scenarioId);
  const byBin = indexByBin(scenario.offtakers);
  const byId = new Map(scenario.offtakers.map((o) => [o.id, o]));
  const dc = site.manifest.data_center;

  document.querySelector(".brand .sub")!.textContent = site.manifest.site.name;
  renderKpis($("kpis"), scenario.results);
  renderEvidence($("evidence"), scenario.results);
  renderLegend();

  // Offline-safe: no tile server, background-only style. Site geometry comes from bundled GeoJSON.
  const map = new maplibregl.Map({
    container: "map",
    style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#0b0f14" } }] },
    center: [dc.lon + 0.002, dc.lat + 0.002],
    zoom: 15.2,
    pitch: 58,
    bearing: -29,
    attributionControl: false,
  });

  const lighting = new LightingEffect({
    ambient: new AmbientLight({ color: [255, 255, 255], intensity: 1.2 }),
    sun: new DirectionalLight({ color: [255, 244, 230], intensity: 2.0, direction: [-1, -2, -3] }),
  });
  const overlay = new MapboxOverlay({
    interleaved: false,
    effects: [lighting],
    layers: [],
    onClick: ({ object, layer }) => {
      if (layer?.id !== "buildings" || !object) return;
      const o = byBin.get(String((object as { properties: BuildingProps }).properties.bin));
      if (o) ui.set({ selectedId: o.id });
    },
    getTooltip: ({ object, layer }) => {
      if (layer?.id === "buildings" && object) {
        const p = (object as { properties: BuildingProps }).properties;
        return { html: tooltipHtml(p, byBin.get(String(p.bin))), className: "tooltip" };
      }
      if (layer?.id === "pipes" && object) {
        const p = (object as { properties: { flow_mw: number; dn: string } }).properties;
        return { html: `<b>Heat main ${p.dn.toUpperCase()}</b><br/>${p.flow_mw.toFixed(1)} MW design flow · 65–80 °C supply`, className: "tooltip" };
      }
      return null;
    },
  });
  map.addControl(overlay as unknown as maplibregl.IControl);

  const redraw = () => overlay.setProps({ layers: siteLayers({ site, scenario, selectedId: ui.get().selectedId }, byBin) });
  const renderSide = () => {
    const sel = ui.get().selectedId;
    const o = sel ? byId.get(sel) : undefined;
    if (o) renderDetail($("side"), o); else renderRanking($("side"), scenario);
  };
  ui.subscribe((s, prev) => {
    renderSide();
    if (s.selectedId !== prev.selectedId) {
      redraw();
      const o = s.selectedId ? byId.get(s.selectedId) : undefined;
      if (o) map.flyTo({ center: [o.lon, o.lat], zoom: 16.4, pitch: 60, duration: 1400, essential: true });
    }
  });
  redraw();
  renderSide();
  map.on("load", () => {
    loading.classList.add("hidden");
    const pre = params.get("select");   // deep link, e.g. ?select=FULTON (used by Demo Mode and tests)
    const hit = pre ? scenario.offtakers.find((o) => o.id === pre || o.name.toUpperCase() === pre.toUpperCase()) : undefined;
    if (hit) ui.set({ selectedId: hit.id });
  });
}

start().catch((e: unknown) => showError(e instanceof Error ? e.message : String(e)));
