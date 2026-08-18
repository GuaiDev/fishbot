// Faint nautical atmosphere behind the Chat coach's content — a line-art
// compass rose with a few chart-contour arcs. Sense of place and craft
// without crowding: it sits behind everything (pointer-events:none, low
// opacity) and is naturally covered as a real conversation fills the screen,
// so atmosphere recedes as evidence accumulates.
//
// Two treatments: 'journal' keeps it a barely-there warm watermark; the
// 'instrument' direction lets the chart motif read as structure, cooler and
// a touch more present (but still never competing with content).
export default function CompassWatermark({ variant = 'journal' }) {
  const journal = variant === 'journal';
  const stroke = journal ? 'var(--fx-brass)' : 'var(--ci-line, #6f93a6)';
  const opacity = journal ? 0.06 : 0.11;

  // 8-point rose: long cardinal rays + shorter intercardinal rays, over two
  // concentric rings and a small hub. Angles in degrees from vertical.
  const rays = [];
  for (let i = 0; i < 8; i++) {
    const angle = (i * 45 * Math.PI) / 180;
    const long = i % 2 === 0; // cardinal points get the long, pointed rays
    const r = long ? 100 : 58;
    const x = 120 + r * Math.sin(angle);
    const y = 120 - r * Math.cos(angle);
    // A slim diamond/kite ray rather than a plain line, for the rose look.
    const bw = long ? 11 : 8;
    const bx = 120 + 26 * Math.sin(angle + Math.PI / 2);
    const by = 120 - 26 * Math.cos(angle + Math.PI / 2);
    const bx2 = 120 + 26 * Math.sin(angle - Math.PI / 2);
    const by2 = 120 - 26 * Math.cos(angle - Math.PI / 2);
    rays.push(
      <polygon
        key={i}
        points={`${x},${y} ${(120 + (bx - 120) * (bw / 26))},${(120 + (by - 120) * (bw / 26))} ${(120 + (bx2 - 120) * (bw / 26))},${(120 + (by2 - 120) * (bw / 26))}`}
        fill="none"
        stroke={stroke}
        strokeWidth="1"
      />
    );
  }

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'absolute',
        top: journal ? '4%' : '-6%',
        right: journal ? '-14%' : '-18%',
        width: journal ? 340 : 440,
        height: journal ? 340 : 440,
        opacity,
        pointerEvents: 'none',
        zIndex: 0,
      }}
    >
      <svg viewBox="0 0 240 240" style={{ width: '100%', height: '100%' }}>
        {/* chart-contour arcs — a few concentric rings suggesting depth lines */}
        <circle cx="120" cy="120" r="112" fill="none" stroke={stroke} strokeWidth="1" />
        <circle cx="120" cy="120" r="92" fill="none" stroke={stroke} strokeWidth="0.75" strokeDasharray={journal ? 'none' : '2 4'} />
        {rays}
        <circle cx="120" cy="120" r="26" fill="none" stroke={stroke} strokeWidth="1" />
        <circle cx="120" cy="120" r="3" fill={stroke} stroke="none" />
        {/* cardinal tick labels only in the instrument direction — a chart cue */}
        {!journal && (
          <g fill={stroke} stroke="none" style={{ fontSize: 11, fontFamily: 'monospace' }}>
            <text x="120" y="14" textAnchor="middle">N</text>
            <text x="230" y="124" textAnchor="middle">E</text>
            <text x="120" y="234" textAnchor="middle">S</text>
            <text x="10" y="124" textAnchor="middle">W</text>
          </g>
        )}
      </svg>
    </div>
  );
}
