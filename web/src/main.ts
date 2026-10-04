import "@fontsource/inter/400.css";
import "@fontsource/inter/700.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import * as maplibregl from "maplibre-gl";
// Bundle MapLibre's module worker locally so the map works offline in production builds.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { LightingEffect, AmbientLight, DirectionalLight } from "@deck.gl/core";
import { loadSite } from "./data";
import { buildingTooltip, siteLayers } from "./map/layers";
import type { BuildingProps } from "./data";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

const SITE = new URLSearchParams(location.search).get("site") ?? "site1_chelsea";
const loading = document.getElementById("loading")!;

function showError(msg: string) {
  loading.classList.remove("hidden");
  loading.innerHTML = `<div class="error-card"><b>Could not load this site</b><br/>${msg}<br/><small>Run <code>make simulate</code> to regenerate data.</small></div>`;
}

async function start() {
  const bundle = await loadSite(SITE);
  const dc = bundle.manifest.data_center;

  // Offline-safe: no tile server, background-only style. Site geometry comes from bundled GeoJSON.
  const map = new maplibregl.Map({
    container: "map",
    style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#0b0f14" } }] },
    center: [dc.lon, dc.lat],
    zoom: 15.3,
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
    layers: siteLayers(bundle),
    getTooltip: ({ object, layer }) =>
      layer?.id === "buildings" && object
        ? { html: buildingTooltip((object as { properties: BuildingProps }).properties), className: "tooltip" }
        : null,
  });
  map.addControl(overlay as unknown as maplibregl.IControl);
  document.querySelector(".brand .sub")!.textContent = bundle.manifest.site.name;
  map.on("load", () => loading.classList.add("hidden"));
}

start().catch((e: unknown) => showError(e instanceof Error ? e.message : String(e)));
