import "@fontsource/inter/400.css";
import "@fontsource/inter/700.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import * as maplibregl from "maplibre-gl";
// Bundle MapLibre's module worker locally so the map works offline in production builds.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer } from "@deck.gl/layers";

maplibregl.setWorkerUrl(maplibreWorkerUrl);

// Offline-safe: no tile server, background-only style. Site geometry comes from bundled GeoJSON.
const map = new maplibregl.Map({
  container: "map",
  style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#0b0f14" } }] },
  center: [-74.0029, 40.7411],
  zoom: 15.5,
  pitch: 55,
  bearing: -29,
  attributionControl: false,
});

const overlay = new MapboxOverlay({
  interleaved: false,
  layers: [
    new ScatterplotLayer({
      id: "dc",
      data: [{ position: [-74.0029, 40.7411] }],
      getPosition: (d: { position: [number, number] }) => d.position,
      getRadius: 60,
      getFillColor: [255, 107, 53, 220],
    }),
  ],
});
map.addControl(overlay as unknown as maplibregl.IControl);
map.on("load", () => document.getElementById("loading")?.classList.add("hidden"));
