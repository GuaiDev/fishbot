// Segmented collection-progress trail, per DESIGN.md's Discovery Progress
// Trail component: a discrete "3 of 5 discoveries" count, not the map's
// continuous exploration-score bar. Filled Moss per discovered segment,
// outline Twig/Ash per not-yet-found segment. If discovered === total, the
// final segment and caption take Gold instead of Moss (The Earned Gold Rule).
export default function DiscoveryTrail({ discovered, total, label }) {
  const complete = discovered >= total && total > 0;
  const segments = Array.from({ length: total }, (_, i) => i < discovered);

  return (
    <div>
      <div style={{ display: 'flex', gap: 6 }}>
        {segments.map((filled, i) => {
          const isLastAndComplete = complete && i === total - 1;
          return (
            <div
              key={i}
              aria-hidden="true"
              style={{
                flex: 1,
                height: 6,
                borderRadius: 'var(--radius-xs)',
                background: filled
                  ? (isLastAndComplete ? 'var(--color-gold)' : 'var(--color-moss)')
                  : 'transparent',
                border: filled ? 'none' : '1px solid var(--color-border-twig)',
              }}
            />
          );
        })}
      </div>
      <div style={{
        marginTop: 6,
        fontSize: 11,
        fontWeight: 500,
        color: complete ? 'var(--color-gold)' : 'var(--color-text-ash)',
      }}>
        {label || `${discovered} of ${total} discovered`}
      </div>
    </div>
  );
}
