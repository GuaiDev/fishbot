// Shared formatting for the Chat coach's conditions evidence — used by both
// design directions (journal + instrument) and the header line, so the two
// variants render identical facts and only differ visually.

// WMO weather codes -> plain sky words. Grouped, not exhaustive per-code, so
// the coach reads like a person describing the sky, not a decoder ring.
export function skyLabel(code) {
  if (code == null) return null;
  if (code === 0) return 'Clear';
  if (code <= 2) return 'Mostly clear';
  if (code === 3) return 'Overcast';
  if (code <= 48) return 'Fog';
  if (code <= 57) return 'Drizzle';
  if (code <= 67) return 'Rain';
  if (code <= 77) return 'Snow';
  if (code <= 82) return 'Showers';
  if (code <= 86) return 'Snow showers';
  return 'Thunderstorms';
}

// Trend glyph + word, shared so both variants label pressure the same way.
export function trendMark(trend) {
  if (trend === 'rising') return { glyph: '↑', word: 'rising' };
  if (trend === 'falling') return { glyph: '↓', word: 'falling' };
  return { glyph: '→', word: 'steady' };
}

// Ontario-freshwater seasonal note, grounded in fishing rather than a
// generic month name. Drives the header line for users without a recent trip.
export function seasonNote(date = new Date()) {
  const m = date.getMonth(); // 0-11
  if (m === 11 || m <= 1) return 'hard-water season';
  if (m === 2 || m === 3) return 'the spring melt and pre-spawn';
  if (m === 4 || m === 5) return 'the spawn and early season';
  if (m === 6 || m === 7) return 'peak warmwater season';
  if (m === 8 || m === 9) return 'the fall feed and turnover';
  return 'the late-fall bite';
}

// e.g. 45.44°N 73.67°W — a precision/credibility touch for the instrument
// direction. Kept to 2 decimals: honest about resolution without false
// six-decimal precision on a coarse station read.
export function formatCoords(lat, lng) {
  if (lat == null || lng == null) return null;
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lng >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(2)}°${ns} ${Math.abs(lng).toFixed(2)}°${ew}`;
}

// Honest one-liner about WHERE the reading is from — specificity is itself
// part of the credibility, and it never implies more certainty than we have.
export function sourceCaption(source, name) {
  if (source === 'gps') return `at your current location`;
  if (source === 'last_trip') return `from your last trip · ${name}`;
  return `typical for ${name} · share your location for a precise read`;
}
