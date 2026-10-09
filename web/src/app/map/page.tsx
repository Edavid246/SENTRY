"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GeoJSONSource, Map as MlMap } from "maplibre-gl";
import { api, type ConnectedMap, type MapFeature, type MapKind } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Shell } from "@/components/Shell";
import { ClearanceBadge } from "@/components/ClearanceBadge";
import { BASEMAP_BOUNDS, basemapStyle, registerBasemap } from "@/lib/basemap";
import { STATES } from "@/lib/states";

const COLOURS: Record<MapKind, string> = {
  sensor: "#8fa89d",
  detection: "#efa93a",
  mission: "#5fae86",
};
// One replay tick advances the clock by 30 simulated minutes (the 48 h window takes ~1.5 min).
const REPLAY_STEP_MS = 30 * 60 * 1000;
const REPLAY_TICK_MS = 1000;
const KIND_LABEL: Record<MapKind, string> = {
  sensor: "Sensors",
  detection: "Detections",
  mission: "UAS missions",
};

function boundsOf(features: MapFeature[]): [number, number, number, number] | null {
  let w = 180, s = 90, e = -180, n = -90;
  for (const f of features) {
    const pts = f.geometry.type === "Point" ? [f.geometry.coordinates] : f.geometry.coordinates;
    for (const [lon, lat] of pts) {
      w = Math.min(w, lon);
      e = Math.max(e, lon);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
    }
  }
  return w > e ? null : [w, s, e, n];
}

export default function MapPage() {
  const { me } = useSession();
  const [data, setData] = useState<ConnectedMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<MapKind>>(new Set());
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const [state, setState] = useState("");

  useEffect(() => {
    if (!me) return;
    setError(null);
    api
      .connectedMap(state || undefined)
      .then(setData)
      .catch(() => setError("The map data could not be loaded."));
  }, [me, state]);

  // Replay (STUB live feed, docs/STUBS.md): detections arrive one batch at a time as a
  // replay clock advances through the window; sensors and missions stay as loaded.
  const [replay, setReplay] = useState<{ events: MapFeature[]; clock: string } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopReplay = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setReplay(null);
  };
  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);
  const startReplay = async () => {
    try {
      const head = await api.replay(null, "1970-01-01T00:00:00Z", state || undefined);
      const end = Date.parse(head.window_end);
      let clock = Date.parse(head.window_start);
      let last: string | null = null;
      let busy = false;
      setReplay({ events: [], clock: head.window_start });
      timer.current = setInterval(async () => {
        if (busy) return;
        busy = true;
        try {
          clock = Math.min(clock + REPLAY_STEP_MS, end);
          const upto = new Date(clock).toISOString().replace(".000Z", "Z");
          const batch = await api.replay(last, upto, state || undefined);
          if (batch.events.length) last = batch.events[batch.events.length - 1].properties.observed_at ?? last;
          setReplay((r) => (r ? { events: [...r.events, ...batch.events], clock: upto } : r));
          if (clock >= end && timer.current) {
            clearInterval(timer.current);
            timer.current = null;
          }
        } catch {
          setError("The replay feed could not be loaded.");
          stopReplay();
        } finally {
          busy = false;
        }
      }, REPLAY_TICK_MS);
    } catch {
      setError("The replay feed could not be loaded.");
    }
  };

  const visible = useMemo(() => {
    const base = (data?.features ?? []).filter(
      (f) => !(replay && f.properties.kind === "detection"),
    );
    return [...base, ...(replay?.events ?? [])].filter((f) => !hidden.has(f.properties.kind));
  }, [data, hidden, replay]);
  const counts = useMemo(() => {
    const c: Record<MapKind, number> = { sensor: 0, detection: 0, mission: 0 };
    for (const f of data?.features ?? []) c[f.properties.kind] += 1;
    return c;
  }, [data]);
  const picked = data?.features.find((f) => f.properties.ref === selected) ?? null;

  // Create the map once the data (and so the extent) is known.
  useEffect(() => {
    if (!data || !container.current || mapRef.current) return;
    let disposed = false;
    const box = boundsOf(data.features) ?? BASEMAP_BOUNDS;
    const pad = 0.05;
    const extent: [number, number, number, number] = [
      box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad,
    ];
    import("maplibre-gl").then(({ default: maplibregl }) => {
      if (disposed || !container.current) return;
      registerBasemap(maplibregl);
      const base = basemapStyle();
      const map = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          glyphs: base.glyphs,
          sprite: base.sprite,
          sources: {
            ...base.sources,
            features: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
          },
          layers: [
            ...base.layers,
            {
              id: "missions",
              type: "line",
              source: "features",
              filter: ["==", ["geometry-type"], "LineString"],
              paint: { "line-color": COLOURS.mission, "line-width": 2.5, "line-dasharray": [2, 1] },
            },
            {
              id: "points",
              type: "circle",
              source: "features",
              filter: ["==", ["geometry-type"], "Point"],
              paint: {
                "circle-radius": ["case", ["==", ["get", "kind"], "sensor"], 7, 6],
                "circle-color": ["match", ["get", "kind"], "sensor", COLOURS.sensor, COLOURS.detection],
                "circle-stroke-color": "#cfdcd5",
                "circle-stroke-width": 1,
              },
            },
          ],
        },
        bounds: extent,
        fitBoundsOptions: { padding: 40, maxZoom: 14 },
        // Keep the view on the offline extract; outside it there is no map data.
        maxBounds: BASEMAP_BOUNDS,
        attributionControl: { compact: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      for (const layer of ["points", "missions"]) {
        map.on("click", layer, (e) => {
          const ref = e.features?.[0]?.properties?.ref;
          if (typeof ref === "string") setSelected(ref);
        });
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
      map.on("load", () => setReady(true));
      mapRef.current = map;
    });
    return () => {
      disposed = true;
    };
  }, [data]);

  useEffect(() => () => {
    mapRef.current?.remove();
    mapRef.current = null;
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("features") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: visible,
    } as never);
  }, [visible, ready]);

  const toggle = (k: MapKind) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <Shell>
      <div className="flex h-full">
        <div className="relative min-w-0 flex-1">
          <div ref={container} data-testid="map-canvas" data-ready={ready}
            style={{ position: "absolute", inset: 0 }} />
          <div className="absolute left-3 top-3 border border-rule bg-surface/90 px-3 py-1 text-[0.75rem] tracking-[0.12em] text-sage">
            SYNTHETIC DATA · OFFLINE BASEMAP (NO EXTERNAL TILES)
          </div>
          {error && (
            <p role="alert" data-testid="map-error" className="absolute left-3 top-12 border border-rule bg-surface p-3">
              {error}
            </p>
          )}
        </div>
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-rule bg-surface p-4">
          <h1 className="label">Connected sensors and UAS</h1>
          <p className="mt-1 text-[0.75rem] text-mute">
            Only what your clearance and compartments allow is returned by the API.
          </p>
          <label className="mt-3 flex flex-col gap-1 text-[0.75rem] text-mute">
            State
            <select
              data-testid="state-filter"
              className="border border-rule bg-surface px-2 py-1 text-[0.85rem] text-ink"
              value={state}
              onChange={(e) => {
                stopReplay();
                setState(e.target.value);
              }}
            >
              <option value="">All states</option>
              {STATES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              data-testid="replay-toggle"
              className="btn"
              onClick={() => (replay ? stopReplay() : void startReplay())}
            >
              {replay ? "Stop replay" : "Replay detections"}
            </button>
            {replay && (
              <span data-testid="replay-clock" className="font-mono text-[0.75rem] text-amber">
                {replay.clock.replace("T", " ").replace("Z", " UTC")} · {replay.events.length}
              </span>
            )}
          </div>
          {replay && (
            <p className="mt-1 text-[0.7rem] text-mute">
              Simulated live feed: synthetic detections replayed on a timer.
            </p>
          )}
          <div className="mt-3 flex flex-col gap-1.5" data-testid="map-legend">
            {(Object.keys(KIND_LABEL) as MapKind[]).map((k) => (
              <label key={k} className="flex cursor-pointer items-center gap-2 text-[0.85rem]">
                <input type="checkbox" checked={!hidden.has(k)} onChange={() => toggle(k)} />
                <span className="inline-block h-2.5 w-2.5" style={{ background: COLOURS[k] }} />
                {KIND_LABEL[k]}
                <span data-testid={`count-${k}`} className="ml-auto font-mono text-mute">
                  {counts[k]}
                </span>
              </label>
            ))}
          </div>

          {picked && (
            <div data-testid="map-detail" className="mt-4 border border-rule p-3 text-[0.85rem]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="label">{picked.properties.kind}</span>
                <ClearanceBadge code={picked.properties.classification} />
                {picked.properties.compartments.map((c) => (
                  <span key={c} className="tag">
                    {c}
                  </span>
                ))}
              </div>
              <div className="mt-2 font-medium">{picked.properties.label}</div>
              <dl className="mt-2 grid grid-cols-[6rem_1fr] gap-y-1 text-[0.8rem]">
                {(
                  [
                    ["Unit", picked.properties.unit_path],
                    ["Observed", picked.properties.observed_at],
                    ["Date", picked.properties.mission_date],
                    ["Status", picked.properties.status],
                    ["Track", picked.properties.track_kind],
                    ["Area", picked.properties.area],
                    ["Reason", picked.properties.reason],
                    ["Confidence", picked.properties.confidence?.toString()],
                  ] as [string, string | null | undefined][]
                )
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-mute">{k}</dt>
                      <dd className="break-words">{v}</dd>
                    </div>
                  ))}
              </dl>
              <Link
                href={`/records/${encodeURIComponent(picked.properties.ref)}`}
                data-testid="map-record-link"
                className="btn mt-3 inline-block"
              >
                Open {picked.properties.ref}
              </Link>
            </div>
          )}

          <ul className="mt-4 flex flex-col gap-1" data-testid="map-list">
            {visible.map((f) => (
              <li key={f.properties.ref}>
                <button
                  type="button"
                  onClick={() => setSelected(f.properties.ref)}
                  data-testid={`map-item-${f.properties.ref}`}
                  className={`flex w-full items-center gap-2 border-l-[3px] px-2 py-1 text-left text-[0.8rem] ${
                    f.properties.ref === selected ? "border-amber bg-raised" : "border-transparent hover:bg-raised"
                  }`}
                >
                  <span className="inline-block h-2 w-2 shrink-0" style={{ background: COLOURS[f.properties.kind] }} />
                  <span className="truncate">{f.properties.label}</span>
                  <span className="ml-auto font-mono text-mute">{f.properties.ref}</span>
                </button>
              </li>
            ))}
          </ul>
          {data && data.features.length === 0 && !error && (
            <p data-testid="map-empty" className="mt-4 text-sage">
              Nothing to show for your access level.
            </p>
          )}
        </aside>
      </div>
    </Shell>
  );
}
