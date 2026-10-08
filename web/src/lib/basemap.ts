// Offline street basemap (air-gap safe): an OpenStreetMap extract of the demo area, label
// fonts and sprites are all served by this app from public/basemap/. Nothing is fetched
// from a tile server, font CDN or any other external host (web/public/basemap/README.md).
import type { LayerSpecification, StyleSpecification } from "maplibre-gl";
import { layers, namedFlavor } from "@protomaps/basemaps";
import { PMTiles, Protocol, type RangeResponse, type Source } from "pmtiles";

const ARCHIVE = "/basemap/demo-area.pmtiles";
const KEY = "demo-area";

/** [west, south, east, north] of the extract; the map cannot be panned outside it. */
export const BASEMAP_BOUNDS: [number, number, number, number] = [5.25, 9.15, 5.7, 9.55];

// Reads the whole archive (about 2 MB) once and serves byte ranges from memory, so the
// map does not depend on the web server supporting HTTP Range requests.
class WholeFileSource implements Source {
  private bytes: Promise<ArrayBuffer> | null = null;
  getKey() {
    return KEY;
  }
  async getBytes(offset: number, length: number): Promise<RangeResponse> {
    this.bytes ??= fetch(ARCHIVE).then((r) => {
      if (!r.ok) throw new Error(`basemap archive: HTTP ${r.status}`);
      return r.arrayBuffer();
    });
    return { data: (await this.bytes).slice(offset, offset + length) };
  }
}

let protocol: Protocol | null = null;

/** Register the pmtiles:// protocol with MapLibre once per page load. */
export function registerBasemap(maplibregl: typeof import("maplibre-gl")): void {
  if (protocol) return;
  protocol = new Protocol();
  protocol.add(new PMTiles(new WholeFileSource()));
  maplibregl.addProtocol("pmtiles", protocol.tile);
}

export const BASEMAP_ATTRIBUTION = "© OpenStreetMap contributors · Protomaps";

/** Style pieces for the basemap: sources, glyphs, sprite and the base layers. */
export function basemapStyle(): Pick<StyleSpecification, "glyphs" | "sprite" | "sources"> & {
  layers: LayerSpecification[];
} {
  // MapLibre needs absolute URLs for glyphs and sprites; both point at this app.
  const origin = window.location.origin;
  return {
    glyphs: `${origin}/basemap/fonts/{fontstack}/{range}.pbf`,
    sprite: `${origin}/basemap/sprites/dark`,
    sources: {
      basemap: {
        type: "vector",
        url: `pmtiles://${KEY}`,
        attribution: BASEMAP_ATTRIBUTION,
      },
    },
    layers: layers("basemap", FLAVOR, { lang: "en" }),
  };
}

// Protomaps "dark", recoloured to the app palette. The demo area is rural and sparsely
// mapped, so roads and labels get more contrast than the stock flavor gives them; the
// overlay colours (sensors, detections, missions) stay the brightest things on the map.
const FLAVOR = {
  ...namedFlavor("dark"),
  background: "#091017",
  earth: "#0f1a20",
  water: "#173543",
  wood_a: "#122219",
  wood_b: "#122219",
  scrub_a: "#131f1a",
  scrub_b: "#131f1a",
  buildings: "#1f2d33",
  boundaries: "#3c5058",
  railway: "#36474c",
  other: "#2a3a3f",
  minor_service: "#2f4146",
  minor_a: "#3a4f53",
  minor_b: "#3a4f53",
  link: "#4a6063",
  major: "#4f6668",
  highway: "#5f7774",
  roads_label_minor: "#7d918a",
  roads_label_minor_halo: "#091017",
  roads_label_major: "#8fa89d",
  roads_label_major_halo: "#091017",
  subplace_label: "#8fa89d",
  subplace_label_halo: "#091017",
  city_label: "#b7c7bf",
  city_label_halo: "#091017",
};
