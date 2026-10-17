// Offline street basemap (air-gap safe): an OpenStreetMap extract of the demo area, label
// fonts and sprites are all served by this app from public/basemap/. Nothing is fetched
// from a tile server, font CDN or any other external host (web/public/basemap/README.md).
import type { LayerSpecification, StyleSpecification } from "maplibre-gl";
import { layers, namedFlavor } from "@protomaps/basemaps";
import { PMTiles, Protocol, type RangeResponse, type Source } from "pmtiles";
import { palette } from "./palette";

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

// Protomaps "light", recoloured to the app palette: warm grey land, grey roads, near-black
// labels. The demo area is rural and sparsely mapped, so roads and labels get more contrast than
// the stock flavor gives them; the overlay colours (sensors, detections, missions) stay the
// strongest marks on the map. The POI and one-way icons still come from the offline dark sprite
// set (public/basemap/README.md); the extract has very few of them.
const FLAVOR = {
  ...namedFlavor("light"),
  background: "#e9e4e2",
  earth: "#efebe9",
  water: "#c9d8de",
  wood_a: "#dfe6da",
  wood_b: "#dfe6da",
  scrub_a: "#e4e8de",
  scrub_b: "#e4e8de",
  buildings: "#ddd5d3",
  boundaries: "#a99e9c",
  railway: "#b3a8a6",
  other: "#e6e0de",
  // Roads are grey lines rather than white: the area's thin rural tracks vanish as white on
  // light land.
  minor_service: "#c9bfbd",
  minor_a: "#bdb2b0",
  minor_b: "#bdb2b0",
  link: "#a99e9c",
  major: "#a99e9c",
  highway: "#968a88",
  roads_label_minor: palette.mute,
  roads_label_minor_halo: palette.ground,
  roads_label_major: palette.soft,
  roads_label_major_halo: palette.ground,
  subplace_label: palette.soft,
  subplace_label_halo: palette.ground,
  city_label: palette.ink,
  city_label_halo: palette.ground,
};
