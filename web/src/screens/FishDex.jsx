import { useState, useEffect, useMemo } from 'react';
import { getFishDex, resolvePhotoUrl } from '../api';
import GrainOverlay from '../components/GrainOverlay';
import '../fishdex-tokens.css';

// ============================================================================
// My FishDex — the real collection screen.
//
// Built against design_handoff_fishdex_collection/README.md (hifi spec) and
// its two reference screenshots (3a flat, 3b grouped). Adaptive: renders the
// flat view (3a) when the user's catches span < 3 distinct families, and the
// grouped view (3b) once they span 3+ — this is inferred from real data via
// GET /fishdex, never a user-facing toggle.
//
// Known real-data gaps, handled honestly rather than faked:
// - No photo yet for a catch -> a quiet placeholder tile, never a broken
//   image icon (the handoff's <image-slot> concept).
// - biggest_size (personal-best length) isn't populated by any current input
//   path (no NL size extraction, no manual entry field yet) -- species with
//   no recorded size simply show a catch count, no "x″" figure or PB pill.
// - No acknowledgment-state table exists for "new find until dismissed" --
//   a species caught exactly once is used as an honest proxy for "new".
// - Region title reads "Ontario" (the real jurisdiction this data is scoped
//   to), not a fabricated watershed name — the prototype's "Credit River
//   watershed" was a hardcoded sample, not real computed geography.
// ============================================================================

const FISH_GLYPH = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M3 12c3-4 7-6 11-6 3 0 5.5 2 7 4-1.5 2-4 4-7 4-4 0-8-2-11-6z"
      stroke="currentColor"
      strokeWidth="1.2"
    />
    <path d="M21 10l2 2-2 2" stroke="currentColor" strokeWidth="1.2" />
    <circle cx="8" cy="11" r="0.8" fill="currentColor" />
  </svg>
);

function familyKeyOf(species) {
  return species.family || 'Unclassified';
}

// Merge caughtSpecies + regionSpeciesPool into one per-family structure:
// each family carries every species (caught + locked) it contains, plus
// caught/total counts for completion framing.
function groupByFamily(caughtSpecies, regionSpeciesPool) {
  const caughtById = new Map(caughtSpecies.map(s => [s.id, s]));
  const poolIds = new Set(regionSpeciesPool.map(s => s.id));

  // Union: pool species, plus any caught species the pool doesn't list
  // (e.g. caught outside the expected regional pool coverage) so nothing
  // caught ever silently vanishes from the totals.
  const allSpecies = [
    ...regionSpeciesPool.map(s => ({ ...s, caught: caughtById.get(s.id) || null })),
    ...caughtSpecies.filter(s => !poolIds.has(s.id)).map(s => ({ ...s, caught: s })),
  ];

  const families = new Map();
  for (const sp of allSpecies) {
    const key = familyKeyOf(sp);
    if (!families.has(key)) {
      families.set(key, {
        familyKey: key,
        familyCommonName: sp.familyCommonName || 'Other',
        species: [],
      });
    }
    families.get(key).species.push(sp);
  }

  return Array.from(families.values()).map(f => {
    const caughtCount = f.species.filter(s => s.caught).length;
    // Caught species first (mirrors the flat view's PB-first ordering),
    // then locked species alphabetically — the handoff's grid shows caught
    // tiles grouped together, not interleaved with locked ones in whatever
    // order the region-pool query happened to return.
    const sortedSpecies = [...f.species].sort((a, b) => {
      if (!!a.caught !== !!b.caught) return a.caught ? -1 : 1;
      if (a.caught && b.caught) {
        if (a.caught.isPersonalBest !== b.caught.isPersonalBest) return a.caught.isPersonalBest ? -1 : 1;
        return b.caught.count - a.caught.count;
      }
      return a.commonName.localeCompare(b.commonName);
    });
    return {
      ...f,
      species: sortedSpecies,
      caughtCount,
      totalCount: f.species.length,
      hasNewFind: f.species.some(s => s.caught?.isNewFind),
      // Representative photo for the collapsed banner: prefer a personal
      // best, then any caught species with a photo.
      representativePhotoUrl:
        f.species.find(s => s.caught?.isPersonalBest && s.caught?.representativePhotoUrl)?.caught
          ?.representativePhotoUrl ||
        f.species.find(s => s.caught?.representativePhotoUrl)?.caught?.representativePhotoUrl ||
        null,
    };
  });
}

function SearchButton() {
  // Opens species/family search — explicitly "not designed in this bundle"
  // per the handoff. Rendered inert rather than wired to nothing pretending
  // to work.
  return (
    <button
      type="button"
      aria-label="Search species"
      disabled
      style={{
        width: 38, height: 38, borderRadius: '50%',
        background: 'var(--fx-card-fill-dark)',
        border: '1px solid var(--fx-hairline)',
        color: 'var(--fx-text-muted)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'default', flexShrink: 0,
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.6" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </button>
  );
}

function DiscoveryHeader({ discovered, total, distinctFamilyCount, isGrouped }) {
  const pct = total > 0 ? Math.min(100, (discovered / total) * 100) : 0;

  return (
    <div style={{
      padding: '12px 22px 16px',
      borderBottom: '1px solid var(--fx-divider)',
      flexShrink: 0,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{
            fontFamily: 'var(--fx-font-ui)', fontSize: 11, fontWeight: 700,
            letterSpacing: '.18em', textTransform: 'uppercase', color: 'var(--fx-moss-light)',
            marginBottom: 4,
          }}>
            My FishDex
          </div>
          <div style={{
            fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 27,
            color: 'var(--fx-text-primary)', lineHeight: 1.15,
          }}>
            Ontario
          </div>
        </div>
        <SearchButton />
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 18 }}>
        <div style={{ fontFamily: 'var(--fx-font-serif)' }}>
          <span style={{ fontSize: 22, fontWeight: 600, color: 'var(--fx-text-primary)' }}>{discovered}</span>
          <span style={{ fontSize: 15, color: 'var(--fx-text-dim-2)' }}> / {total}</span>
        </div>
        <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)' }}>
          species in your region{isGrouped ? ` · ${distinctFamilyCount} families` : ''}
        </div>
      </div>

      <div style={{ position: 'relative', height: 16, marginTop: 10 }}>
        <div style={{
          position: 'absolute', top: 6, left: 0, right: 0, height: 4,
          borderRadius: 2, background: '#26281f',
        }}>
          <div style={{
            height: '100%', borderRadius: 2, width: `${pct}%`,
            background: 'linear-gradient(90deg,#5f6d44,#9fae7a)',
          }} />
        </div>
        <div
          aria-hidden="true"
          style={{
            position: 'absolute', top: 0, left: `calc(${pct}% - 8px)`,
            width: 16, height: 16, borderRadius: '50%',
            background: 'var(--fx-moss-light)',
            boxShadow: '0 0 0 4px rgba(159,174,122,.18), 0 0 14px rgba(159,174,122,.5)',
          }}
        />
      </div>

      {!isGrouped && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', marginTop: 6,
          fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-text-dim)',
        }}>
          <span>{discovered} discovered</span>
          <span>{Math.max(0, total - discovered)} still on the trail</span>
        </div>
      )}
    </div>
  );
}

function CaughtPlate({ species }) {
  const c = species.caught;
  const photoUrl = c.representativePhotoUrl ? resolvePhotoUrl(c.representativePhotoUrl) : null;

  const showPB = c.isPersonalBest;
  const showNewFind = !showPB && c.isNewFind;

  const figure = showPB ? `${Math.round(c.maxLengthInches)}″` : `${c.count}`;
  const caption = showPB ? `best · ${c.count} logged` : 'logged';

  return (
    <div style={{
      position: 'relative', borderRadius: 18, height: 214, overflow: 'hidden',
      border: '1px solid var(--fx-hairline)', marginBottom: 13, background: 'var(--fx-card-fill-quiet)',
    }}>
      {photoUrl ? (
        <img src={photoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
      ) : (
        <div style={{
          width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--fx-text-locked-3)',
        }}>
          {FISH_GLYPH}
        </div>
      )}

      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(transparent 40%, rgba(11,12,8,.55) 68%, rgba(9,10,6,.9) 100%)',
      }} />

      {(showPB || showNewFind) && (
        <div style={{
          position: 'absolute', top: 12, right: 12,
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '5px 10px', borderRadius: 14,
          background: showPB ? 'rgba(24,18,8,.62)' : 'rgba(20,24,12,.6)',
          backdropFilter: 'blur(4px)',
          border: `1px solid ${showPB ? '#c2a06a' : '#869663'}`,
        }}>
          {showPB ? (
            <>
              <span style={{ color: 'var(--fx-brass-star)' }}>★</span>
              <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10, fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--fx-brass-light)' }}>
                Personal Best
              </span>
            </>
          ) : (
            <>
              <span style={{ color: 'var(--fx-moss-lightest)' }}>❦</span>
              <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10, fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--fx-moss-lightest)' }}>
                New Find
              </span>
            </>
          )}
        </div>
      )}

      <div style={{ position: 'absolute', left: 16, right: 16, bottom: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 23, color: '#f6f1e6' }}>
            {species.commonName}
          </div>
          {species.scientificName && (
            <div style={{
              fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontWeight: 400, fontSize: 13,
              color: showPB ? 'rgba(232,201,138,.85)' : 'rgba(194,204,159,.8)',
            }}>
              {species.scientificName}
            </div>
          )}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 20, color: '#f6f1e6' }}>{figure}</div>
          <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10.5, color: 'rgba(246,241,230,.6)' }}>{caption}</div>
        </div>
      </div>
    </div>
  );
}

function UndiscoveredRow({ species }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      background: 'var(--fx-card-fill-quiet)', border: '1px dashed var(--fx-dashed-border)',
      borderRadius: 14, padding: 14, marginBottom: 13,
    }}>
      <div style={{
        width: 52, height: 52, borderRadius: 10, flexShrink: 0,
        background: 'repeating-linear-gradient(45deg,#20221a,#20221a 7px,#1a1c15 7px,#1a1c15 14px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4c4e40',
      }}>
        {FISH_GLYPH}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 16, color: 'var(--fx-text-locked)' }}>
          {species.commonName}
        </div>
        {species.scientificName && (
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 12.5, color: 'var(--fx-text-locked-3)' }}>
            {species.scientificName}
          </div>
        )}
      </div>
      <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-text-locked-3)', flexShrink: 0 }}>
        not yet caught
      </div>
    </div>
  );
}

function FlatView({ caughtSpecies, undiscoveredSpecies }) {
  const sorted = useMemo(() => [...caughtSpecies].sort((a, b) => {
    const ac = a.caught, bc = b.caught;
    if (ac.isPersonalBest !== bc.isPersonalBest) return ac.isPersonalBest ? -1 : 1;
    return bc.count - ac.count;
  }), [caughtSpecies]);

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '16px 22px 30px' }}>
      {sorted.map(sp => <CaughtPlate key={sp.id} species={sp} />)}

      {undiscoveredSpecies.length > 0 && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '18px 0 16px' }}>
            <div style={{ flex: 1, height: 1, background: 'var(--fx-hairline-2)' }} />
            <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10.5, fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--fx-text-dim)' }}>
              Still On The Trail
            </span>
            <div style={{ flex: 1, height: 1, background: 'var(--fx-hairline-2)' }} />
          </div>
          {undiscoveredSpecies.map(sp => <UndiscoveredRow key={sp.id} species={sp} />)}
        </>
      )}
    </div>
  );
}

function FamilyGridCell({ species }) {
  if (!species.caught) {
    return (
      <div style={{
        position: 'relative', height: 150, borderRadius: 14, overflow: 'hidden',
        background: 'repeating-linear-gradient(45deg,#20221a,#20221a 7px,#1a1c15 7px,#1a1c15 14px)',
      }}>
        <div style={{ position: 'absolute', top: 10, left: 10, color: '#4c4e40' }}>{FISH_GLYPH}</div>
        <div style={{ position: 'absolute', left: 10, bottom: 10 }}>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 14, color: 'var(--fx-text-locked)' }}>
            {species.commonName}
          </div>
          <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10, color: 'var(--fx-text-locked-3)' }}>not yet caught</div>
        </div>
      </div>
    );
  }

  const c = species.caught;
  const photoUrl = c.representativePhotoUrl ? resolvePhotoUrl(c.representativePhotoUrl) : null;
  const statLine = c.isPersonalBest ? `×${c.count} · ${Math.round(c.maxLengthInches)}″ PB` : `×${c.count}`;

  return (
    <div style={{
      position: 'relative', height: 150, borderRadius: 14, overflow: 'hidden',
      boxShadow: '0 10px 24px rgba(0,0,0,.35)', background: 'var(--fx-card-fill-quiet)',
    }}>
      {photoUrl ? (
        <img src={photoUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
      ) : (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fx-text-locked-3)' }}>
          {FISH_GLYPH}
        </div>
      )}
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(transparent 44%, rgba(9,10,6,.9))' }} />

      {c.isPersonalBest && (
        <div style={{
          position: 'absolute', top: 8, left: 8, display: 'flex', alignItems: 'center', gap: 3,
          padding: '3px 7px', borderRadius: 10, background: 'rgba(24,18,8,.62)',
        }}>
          <span style={{ color: 'var(--fx-brass-star)', fontSize: 9 }}>★</span>
          <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 8, fontWeight: 600, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--fx-brass-light)' }}>Best</span>
        </div>
      )}

      <div style={{ position: 'absolute', left: 10, bottom: 8 }}>
        <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 15, color: '#fff' }}>{species.commonName}</div>
        <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10.5, color: 'rgba(246,241,230,.62)' }}>{statLine}</div>
      </div>
    </div>
  );
}

function ExpandedFamily({ family }) {
  return (
    <div style={{ marginBottom: 26 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <div>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 18, color: 'var(--fx-text-primary)' }}>
            {family.familyCommonName}
          </div>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 12, color: 'var(--fx-text-muted)' }}>
            {family.familyKey} · {family.caughtCount} of {family.totalCount} caught
          </div>
        </div>
        <span style={{ color: 'var(--fx-moss-light)', fontSize: 16 }} aria-hidden="true">︿</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 11 }}>
        {family.species.map(sp => <FamilyGridCell key={sp.id} species={sp} />)}
      </div>
    </div>
  );
}

function CollapsedFamilyBanner({ family, onExpand }) {
  const photoUrl = family.representativePhotoUrl ? resolvePhotoUrl(family.representativePhotoUrl) : null;

  return (
    <button
      type="button"
      onClick={onExpand}
      style={{
        display: 'block', border: 'none', padding: 0, margin: 0, cursor: 'pointer',
        textAlign: 'left', background: 'none', width: '100%', font: 'inherit',
      }}
    >
      {/* Clipping lives on this plain div, not the <button> itself — buttons
          have inconsistent overflow/border-radius clipping behavior for
          absolutely-positioned children across browsers. */}
      <div style={{
        position: 'relative', height: 96, borderRadius: 16, overflow: 'hidden',
        boxShadow: '0 10px 26px rgba(0,0,0,.35)', background: 'var(--fx-card-fill-quiet)',
      }}>
        {photoUrl ? (
          <img src={photoUrl} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : null}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, rgba(9,10,6,.86) 42%, rgba(9,10,6,.15))' }} />

        <div style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', right: 48 }}>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 17, color: '#f6f1e6', display: 'flex', alignItems: 'center', gap: 6 }}>
            {family.familyCommonName}
            {family.hasNewFind && <span style={{ color: 'var(--fx-moss-lightest)', fontSize: 13 }}>❦</span>}
          </div>
          <div style={{ fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 12, color: 'rgba(236,230,216,.55)', marginBottom: 6 }}>
            {family.familyKey}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 72, height: 3, borderRadius: 2, background: 'rgba(236,230,216,.16)', flexShrink: 0 }}>
              <div style={{
                height: '100%', borderRadius: 2, background: 'var(--fx-moss-light)',
                width: `${family.totalCount > 0 ? (family.caughtCount / family.totalCount) * 100 : 0}%`,
              }} />
            </div>
            <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, fontWeight: 600, color: 'var(--fx-moss-lightest)' }}>
              {family.caughtCount} / {family.totalCount}
            </span>
          </div>
        </div>

        <div style={{ position: 'absolute', right: 16, top: '50%', transform: 'translateY(-50%)', color: 'rgba(236,230,216,.5)' }} aria-hidden="true">
          ›
        </div>
      </div>
    </button>
  );
}

function EmptyState({ onNavigate }) {
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '32px 32px 64px', textAlign: 'center',
    }}>
      <div style={{
        width: 64, height: 64, borderRadius: '50%', marginBottom: 20,
        border: '1px solid var(--fx-hairline)', background: 'var(--fx-card-fill-quiet)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fx-moss-light)',
      }}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M3 12c3-4 7-6 11-6 3 0 5.5 2 7 4-1.5 2-4 4-7 4-4 0-8-2-11-6z" stroke="currentColor" strokeWidth="1.3" />
          <path d="M21 10l2 2-2 2" stroke="currentColor" strokeWidth="1.3" />
          <circle cx="8" cy="11" r="0.9" fill="currentColor" />
        </svg>
      </div>
      <div style={{
        fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 21,
        color: 'var(--fx-text-primary)', marginBottom: 8,
      }}>
        Your FishDex is waiting
      </div>
      <div style={{
        fontFamily: 'var(--fx-font-ui)', fontSize: 13, lineHeight: 1.5,
        color: 'var(--fx-text-muted)', maxWidth: 260, marginBottom: 24,
      }}>
        Every species you catch adds a page to your collection. Log your first catch to begin the trail.
      </div>
      <button
        type="button"
        onClick={() => onNavigate?.('log')}
        style={{
          fontFamily: 'var(--fx-font-ui)', fontSize: 13, fontWeight: 600,
          color: 'var(--fx-on-accent)', background: 'var(--fx-moss-light)',
          border: 'none', borderRadius: 20, padding: '10px 22px', cursor: 'pointer',
        }}
      >
        Log a catch
      </button>
    </div>
  );
}

function ExploreCard({ family, onExpand }) {
  return (
    <button
      type="button"
      onClick={onExpand}
      style={{
        flexShrink: 0, width: 150, background: 'var(--fx-card-fill-quiet)', borderRadius: 14, padding: 14,
        border: 'none', textAlign: 'left', cursor: 'pointer', font: 'inherit',
      }}
    >
      <div style={{ color: 'var(--fx-text-locked-3)', marginBottom: 8 }}>{FISH_GLYPH}</div>
      <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 14, color: 'var(--fx-text-muted)' }}>
        {family.familyCommonName}
      </div>
      <div style={{ fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 11, color: 'var(--fx-text-locked-3)' }}>
        {family.familyKey} · 0 / {family.totalCount}
      </div>
    </button>
  );
}

function GroupedView({ families }) {
  const touched = useMemo(
    () => [...families].filter(f => f.caughtCount > 0).sort((a, b) => b.caughtCount - a.caughtCount),
    [families]
  );
  const untouched = useMemo(
    () => [...families].filter(f => f.caughtCount === 0).sort((a, b) => a.familyCommonName.localeCompare(b.familyCommonName)),
    [families]
  );
  const [expandedKey, setExpandedKey] = useState(touched[0]?.familyKey ?? null);

  // expandedKey can point at a touched family (rendered inline below) or an
  // untouched one — tapping an explore card opens that family's undiscovered
  // species per the handoff spec, same expand mechanism as a caught family.
  const expandedUntouched = untouched.find(f => f.familyKey === expandedKey);
  const remainingUntouched = untouched.filter(f => f.familyKey !== expandedKey);

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '16px 22px 30px' }}>
      {touched.map(family => (
        family.familyKey === expandedKey ? (
          <ExpandedFamily key={family.familyKey} family={family} />
        ) : (
          <div key={family.familyKey} style={{ marginBottom: 11 }}>
            <CollapsedFamilyBanner family={family} onExpand={() => setExpandedKey(family.familyKey)} />
          </div>
        )
      ))}

      {expandedUntouched && <ExpandedFamily family={expandedUntouched} />}

      {remainingUntouched.length > 0 && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '10px 0 16px' }}>
            <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10.5, fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--fx-text-dim)' }}>
              New Families To Explore
            </span>
            <div style={{ flex: 1, height: 1, background: 'var(--fx-hairline-2)' }} />
          </div>
          <div style={{ display: 'flex', gap: 11, overflowX: 'auto', paddingBottom: 4 }}>
            {remainingUntouched.map(family => (
              <ExploreCard key={family.familyKey} family={family} onExpand={() => setExpandedKey(family.familyKey)} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// DEV-ONLY — lets you force each visual state (empty/flat/grouped) for
// testing without touching real catch data. Dead code in production builds
// (import.meta.env.DEV is false), same pattern as App.jsx's login bypass.
function DevViewOverride({ value, onChange }) {
  if (!import.meta.env.DEV) return null;
  const options = [
    { id: 'auto', label: 'Real data' },
    { id: 'empty', label: 'Empty' },
    { id: 'flat', label: 'Flat' },
    { id: 'grouped', label: 'Grouped' },
  ];
  return (
    <div style={{
      position: 'fixed', top: 8, right: 8, zIndex: 200,
      display: 'flex', gap: 4, padding: 4,
      background: 'rgba(9,10,6,.85)', borderRadius: 10,
      border: '1px solid var(--fx-hairline)',
    }}>
      {options.map(opt => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          style={{
            font: '600 9px system-ui', letterSpacing: '.03em',
            padding: '4px 7px', borderRadius: 6, border: 'none', cursor: 'pointer',
            background: value === opt.id ? 'var(--fx-moss-light)' : 'transparent',
            color: value === opt.id ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default function FishDex({ onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [devView, setDevView] = useState('auto');

  useEffect(() => {
    getFishDex()
      .then(setData)
      .catch(err => setError(err.message));
  }, []);

  const families = useMemo(
    () => data ? groupByFamily(data.caughtSpecies, data.regionSpeciesPool) : [],
    [data]
  );
  const distinctFamilyCount = useMemo(
    () => families.filter(f => f.caughtCount > 0).length,
    [families]
  );
  const isGrouped = distinctFamilyCount >= 3;

  const caughtSpeciesMerged = useMemo(() => {
    if (!data) return [];
    const poolIds = new Set(data.regionSpeciesPool.map(s => s.id));
    const fromPool = data.regionSpeciesPool
      .filter(s => data.caughtSpecies.some(c => c.id === s.id))
      .map(s => ({ ...s, caught: data.caughtSpecies.find(c => c.id === s.id) }));
    const notInPool = data.caughtSpecies
      .filter(c => !poolIds.has(c.id))
      .map(c => ({ ...c, caught: c }));
    return [...fromPool, ...notInPool];
  }, [data]);

  const undiscoveredSpecies = useMemo(() => {
    if (!data) return [];
    const caughtIds = new Set(data.caughtSpecies.map(c => c.id));
    return data.regionSpeciesPool.filter(s => !caughtIds.has(s.id));
  }, [data]);

  const discovered = data?.caughtSpecies.length ?? 0;
  const total = data ? Math.max(data.regionSpeciesPool.length, discovered) : 0;

  // devView lets local testing force any state on top of whatever real data
  // exists — 'auto' preserves the real discovered/family-count-driven logic.
  const effectiveIsEmpty = devView === 'empty' ? true : devView === 'auto' ? discovered === 0 : false;
  const effectiveIsGrouped = devView === 'grouped' ? true : devView === 'flat' ? false : isGrouped;

  return (
    <div style={{
      position: 'relative',
      minHeight: '100dvh',
      display: 'flex',
      flexDirection: 'column',
      background: 'radial-gradient(circle at 50% 0%, var(--fx-bg-grad-1), var(--fx-bg-grad-2) 45%, var(--fx-bg-grad-3) 100%)',
      paddingBottom: 84,
    }}>
      <GrainOverlay />
      <DevViewOverride value={devView} onChange={setDevView} />

      {error && (
        <div style={{ padding: 16, fontFamily: 'var(--fx-font-ui)', fontSize: 13, color: 'var(--fx-brass-light)' }}>
          {error.includes('401') ? 'Not authenticated.' : `Couldn't load your FishDex: ${error}`}
        </div>
      )}

      {!error && !data && (
        <div style={{ padding: 16, fontFamily: 'var(--fx-font-ui)', fontSize: 13, color: 'var(--fx-text-muted)' }}>
          Loading…
        </div>
      )}

      {data && (
        <>
          <DiscoveryHeader
            discovered={discovered}
            total={total}
            distinctFamilyCount={distinctFamilyCount}
            isGrouped={effectiveIsGrouped}
          />
          {effectiveIsEmpty ? (
            <EmptyState onNavigate={onNavigate} />
          ) : effectiveIsGrouped ? (
            <GroupedView families={families} />
          ) : (
            <FlatView caughtSpecies={caughtSpeciesMerged} undiscoveredSpecies={undiscoveredSpecies} />
          )}
        </>
      )}
    </div>
  );
}
