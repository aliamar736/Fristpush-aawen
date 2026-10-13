/* Line icon set (24px grid, 1.8 stroke). Category icons follow the brand board's custom icons. */
const P: Record<string, string> = {
  home: "M3 11.5 12 4l9 7.5M5.5 9.5V20h5v-5.5h3V20h5V9.5",
  map: "M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Zm0 0v14m6-12v14",
  hands: "M7 11.5V7.8a1.6 1.6 0 0 1 3.2 0v3.2m0-1.5V6.3a1.6 1.6 0 0 1 3.2 0v4.2m0-1V7.5a1.6 1.6 0 0 1 3.2 0V14c0 3.6-2.7 6-6 6h-.8a5.6 5.6 0 0 1-4.3-2l-2.6-3.1a1.5 1.5 0 0 1 2.1-2.1L7 13.6",
  give: "M3 15h3.5l3.5 2.5h4.5a1.5 1.5 0 0 0 0-3H11m-5 3.5V21H3m7-7.5h4l4.6-2.4a1.6 1.6 0 0 1 2 2.4L15.5 18M14 3.5a2.6 2.6 0 0 0-3.7 0L9.7 4l-.6-.5A2.6 2.6 0 0 0 5.4 7.2l4.3 4.3L14 7.2a2.6 2.6 0 0 0 0-3.7Z",
  me: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7.5 8.5c.8-3.4 3.9-5.5 7.5-5.5s6.7 2.1 7.5 5.5",
  plus: "M12 5v14M5 12h14",
  bell: "M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15l1.5-2ZM10 20.5a2.2 2.2 0 0 0 4 0",
  back: "M15 5l-7 7 7 7",
  fwd: "M9 5l7 7-7 7",
  pin: "M12 21s-6.5-6-6.5-11a6.5 6.5 0 1 1 13 0c0 5-6.5 11-6.5 11Zm0-8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  camera: "M4 8h3l1.6-2.5h6.8L17 8h3v11H4V8Zm8 8.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
  mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm-6-3a6 6 0 0 0 12 0M12 18v3",
  check: "M5 12.5 10 17.5 19 7",
  alert: "M12 4 2.8 20h18.4L12 4Zm0 6v4.5m0 2.8v.2",
  x: "M6 6l12 12M18 6 6 18",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v4.5l3 2",
  layers: "m12 4 9 4.5-9 4.5-9-4.5L12 4Zm-9 8.5 9 4.5 9-4.5M3 16.5 12 21l9-4.5",
  wifioff: "M3 3l18 18M8.5 12.5a5 5 0 0 1 5.6-1M5 9a10 10 0 0 1 4-2.2m5.4-.3A10 10 0 0 1 19 9m-7 9.5h.01",
  lock: "M6.5 10.5h11V20h-11v-9.5Zm2.5 0V7.5a3 3 0 0 1 6 0v3",
  box: "m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9",
  people: "M8.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.5 0a2.5 2.5 0 1 0 0-5M3 19.5c.6-3 2.8-4.8 5.5-4.8s4.9 1.8 5.5 4.8m1-4.6c2.4 0 4.3 1.6 4.9 4.6",
  trash: "M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5m4-5.5v5.5",
  pothole: "M3 18h18M4.5 18 7 12.5h10l2.5 5.5M10.5 12.5l1.6 2.2-1.3 1.8.9 1.5M15 12.5l-.8 1.7 1 1.3",
  cone: "M9.5 4h5l4 14h-13l4-14Zm-1 6h7M7 14h10M4 20h16",
  lamp: "M7 21h4m-2 0V9a5 5 0 0 1 5-5h1a3 3 0 0 1 3 3v.5M14 7.5h6l-1 3h-4l-1-3Z",
  drop: "M12 3.5S6 10 6 14a6 6 0 0 0 12 0c0-4-6-10.5-6-10.5Zm-2.5 11a2.5 2.5 0 0 0 2.5 2.5",
  wheelchair: "M11 5.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM11 8v6h5l2.5 5M11 11h5M8.3 10.5a5.5 5.5 0 1 0 7 7",
  car: "M5 16.5h14v-4l-2-5H7l-2 5v4Zm0 0V19h2.5v-2.5M19 16.5V19h-2.5v-2.5M5 12.5h14M7.5 14.5h1m7 0h1",
  road: "M8 3 4 21m12-18 4 18M12 4v3m0 3.5v3m0 3.5v3",
  chart: "M4 20V4m0 16h16M8 16v-5m4 5V8m4 8v-3",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.5 7.5 0 0 0-.1-1.3l2-1.6-2-3.4-2.4 1a7.4 7.4 0 0 0-2.2-1.3L14.4 3h-4l-.4 2.4a7.4 7.4 0 0 0-2.2 1.3l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0 0 2.6l-2 1.6 2 3.4 2.4-1a7.4 7.4 0 0 0 2.2 1.3l.4 2.4h4l.4-2.4a7.4 7.4 0 0 0 2.2-1.3l2.4 1 2-3.4-2-1.6c.1-.4.1-.9.1-1.3Z",
  search: "M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Zm5.5-2 5 5",
  refresh: "M20 11a8 8 0 0 0-14.5-4.5M4 4v4h4m-4 5a8 8 0 0 0 14.5 4.5M20 20v-4h-4",
  locate: "M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm0-4a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0-13v3m0 14v3M2 12h3m14 0h3",
  shield: "M12 3 5 6v5.5c0 4.2 3 7.8 7 9.5 4-1.7 7-5.3 7-9.5V6l-7-3Zm-3 9 2 2 4-4",
  store: "M4 9.5 5.5 4h13L20 9.5M4 9.5V20h16V9.5M4 9.5c0 1.4 1.1 2.5 2.7 2.5S9.3 11 9.3 9.5c0 1.4 1.2 2.5 2.7 2.5s2.7-1.1 2.7-2.5c0 1.4 1.1 2.5 2.6 2.5S20 11 20 9.5M9.5 20v-5h5v5",
  star: "m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z",
  doc: "M7 3.5h7l4 4V20.5H7v-17Zm7 0v4h4M9.5 12h6m-6 3.5h6",
  logout: "M14 4.5h5v15h-5M10 8l-4 4 4 4m-4-4h11",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-9-9h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3Z",
  care: "M12 20s-7-4.3-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.7-7 10-7 10Zm-3-9.5h6M12 7.5v6",
  vote: "M5 12.5 9.5 17 19 7.5M4 20h16",
  phone: "M6.5 3.5h3l1.5 4-2 1.5a11 11 0 0 0 6 6l1.5-2 4 1.5v3A2 2 0 0 1 18.5 19.5 15.5 15.5 0 0 1 4.5 5.5a2 2 0 0 1 2-2Z",
};

export const CATEGORY_ICON: Record<string, string> = {
  garbage: "trash", pothole: "pothole", obstacle: "cone", lighting: "lamp", "water-sewage": "drop", sidewalk: "wheelchair",
  trash: "trash", cone: "cone", lamp: "lamp", drop: "drop", accident: "car", congestion: "road", closure: "cone",
};

export function Icon({ name, size = 24, title, className }: { name: string; size?: number; title?: string; className?: string }) {
  const d = P[name] ?? P[CATEGORY_ICON[name]] ?? P.pin;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? "img" : undefined}
      className={className}>
      {title && <title>{title}</title>}
      <path d={d} />
    </svg>
  );
}
