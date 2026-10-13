import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";

import L from "leaflet";
import "leaflet.markercluster";
import { useEffect, useRef } from "react";

export type MapMarker = { id: string | number; lat: number; lng: number; color: string; label: string; onClick?: () => void;
  icon?: "pin" | "square" };
export type MapArea = { id: number; name: string; geometry: GeoJSON.MultiPolygon | null };

const TILE_URL = import.meta.env.VITE_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = import.meta.env.VITE_TILE_ATTRIBUTION ?? "© OpenStreetMap contributors";
export const TRIPOLI: [number, number] = [32.8872, 13.1913];

function pinIcon(color: string, label: string, shape: "pin" | "square" = "pin") {
  const html = shape === "pin"
    ? `<div class="pin" style="background:${color}"><i></i></div>`
    : `<div style="width:26px;height:26px;border-radius:7px;background:${color};border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3)"></div>`;
  return L.divIcon({ html, className: "", iconSize: [28, 28], iconAnchor: [14, 28], popupAnchor: [0, -26],
                     tooltipAnchor: [0, -20], ...{ alt: label } } as L.DivIconOptions);
}

type Props = {
  markers?: MapMarker[];
  areas?: MapArea[];
  center?: [number, number];
  zoom?: number;
  cluster?: boolean;
  picker?: { lat?: number; lng?: number; onChange: (lat: number, lng: number) => void };
  label: string;
  fitToMarkers?: boolean;
};

/** Leaflet map with marker clustering at low zoom, area boundary layer and an optional draggable location picker.
 *  Area boundaries come from our own API, so the map stays meaningful even if the tile server is unreachable. */
export function MapView({ markers = [], areas = [], center = TRIPOLI, zoom = 13, cluster = true, picker, label, fitToMarkers }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const markerLayer = useRef<L.LayerGroup | null>(null);
  const areaLayer = useRef<L.GeoJSON | null>(null);
  const pickMarker = useRef<L.Marker | null>(null);
  const pickerRef = useRef(picker);
  pickerRef.current = picker;

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { center, zoom, zoomControl: true, attributionControl: true });
    L.tileLayer(TILE_URL, { maxZoom: 19, attribution: TILE_ATTR, crossOrigin: true }).addTo(m);
    areaLayer.current = L.geoJSON(undefined, {
      style: { color: "#123F46", weight: 1.5, opacity: 0.6, fillColor: "#20B7A5", fillOpacity: 0.06, dashArray: "4 4" },
    }).addTo(m);
    if (pickerRef.current) {
      m.on("click", (e: L.LeafletMouseEvent) => pickerRef.current?.onChange(e.latlng.lat, e.latlng.lng));
    }
    map.current = m;
    el.current.querySelector(".leaflet-container")?.setAttribute("aria-label", label);
    return () => {
      m.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const layer = areaLayer.current;
    if (!layer) return;
    layer.clearLayers();
    areas.forEach((a) => {
      if (!a.geometry) return;
      const g = L.geoJSON(a.geometry as GeoJSON.GeoJsonObject, { style: layer.options.style });
      g.bindTooltip(a.name, { sticky: true, direction: "top" });
      g.eachLayer((l) => layer.addLayer(l));
    });
  }, [areas]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    markerLayer.current?.remove();
    const group = cluster
      ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50,
          iconCreateFunction: (c) => L.divIcon({ html: `<div class="cluster">${c.getChildCount()}</div>`, className: "",
                                                  iconSize: [40, 40] }) })
      : L.layerGroup();
    markers.forEach((mk) => {
      const marker = L.marker([mk.lat, mk.lng], { icon: pinIcon(mk.color, mk.label, mk.icon), title: mk.label,
                                                  keyboard: true, alt: mk.label });
      marker.bindTooltip(mk.label, { direction: "top" });
      if (mk.onClick) marker.on("click", mk.onClick).on("keypress", (e) => (e as unknown as { originalEvent: KeyboardEvent }).originalEvent.key === "Enter" && mk.onClick?.());
      group.addLayer(marker);
    });
    group.addTo(m);
    markerLayer.current = group;
    if (fitToMarkers && markers.length > 1) {
      m.fitBounds(L.latLngBounds(markers.map((x) => [x.lat, x.lng] as [number, number])).pad(0.2), { maxZoom: 16 });
    }
  }, [markers, cluster, fitToMarkers]);

  useEffect(() => {
    const m = map.current;
    if (!m || !picker) return;
    if (picker.lat == null || picker.lng == null) return;
    const pos: [number, number] = [picker.lat, picker.lng];
    if (!pickMarker.current) {
      pickMarker.current = L.marker(pos, { draggable: true, icon: pinIcon("#F4B544", "موقع البلاغ"), keyboard: true,
                                           title: "موقع البلاغ — اسحب لتعديله" }).addTo(m);
      pickMarker.current.on("dragend", () => {
        const p = pickMarker.current!.getLatLng();
        pickerRef.current?.onChange(p.lat, p.lng);
      });
      m.setView(pos, Math.max(m.getZoom(), 16));
    } else {
      pickMarker.current.setLatLng(pos);
    }
  }, [picker?.lat, picker?.lng, picker]);

  useEffect(() => {
    map.current?.setView(center, map.current.getZoom());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center[0], center[1]]);

  return <div ref={el} style={{ width: "100%", height: "100%" }} role="region" aria-label={label} />;
}
