// Circular gauge for a single condition reading (temperature, pressure, ...),
// per DESIGN.md's Instrument Dial component: a scientific-instrument register
// instead of a small text chip.
//
// Deliberate scope note: DESIGN.md specs the ring arc colored by reading
// *quality* (Moss favorable / Wet Stone neutral / Rust unfavorable). This app
// has no established thresholds for what counts as a "favorable" temperature
// or pressure for fishing — inventing one here would be exactly the kind of
// unsupported presence/quality claim CLAUDE.md's core principle warns
// against. The ring uses a single neutral Moss fill showing position within
// a plausible display range, not a quality judgment. Revisit if/when a real
// habitat-conditions model exists to back that claim.
export default function InstrumentDial({ value, unit, label, min, max }) {
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(1, Math.max(0, (value - min) / (max - min)));
  const offset = circumference * (1 - pct);

  return (
    <div style={{ position: 'relative', width: 72, height: 72, flexShrink: 0 }}>
      <svg viewBox="0 0 80 80" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
        <circle cx="40" cy="40" r={radius} fill="none" stroke="var(--fx-hairline)" strokeWidth="6" />
        <circle
          cx="40" cy="40" r={radius} fill="none"
          stroke="var(--fx-moss-light)" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.4s ease-out' }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      }}>
        <div style={{ fontFamily: 'var(--fx-font-serif)', color: 'var(--fx-text-primary-2)', fontSize: 14, fontWeight: 600 }}>
          {value}{unit}
        </div>
        <div style={{ fontFamily: 'var(--fx-font-ui)', color: 'var(--fx-text-muted)', fontSize: 9, marginTop: 2, textAlign: 'center' }}>
          {label}
        </div>
      </div>
    </div>
  );
}
