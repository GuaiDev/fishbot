import 'leaflet/dist/leaflet.css';
import { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, CircleMarker, useMapEvents } from 'react-leaflet';
import { getMapSegments, getMyStops } from '../api';
import { colorHeatHigh, colorHeatMed, colorHeatMid, colorHeatLow, colorHeatMin, colorMoss, colorTextAsh } from '../tokens';
import InstrumentDial from '../components/InstrumentDial';
import '../fishdex-tokens.css';

function scoreColor(score) {
  if (score >= 0.7) return colorHeatHigh;
  if (score >= 0.5) return colorHeatMed;
  if (score >= 0.3) return colorHeatMid;
  if (score >= 0.1) return colorHeatLow;
  return colorHeatMin;
}

function stopColor(productive) {
  return productive ? colorMoss : colorTextAsh;
}

function ExploreLayer({ mode, onSegmentClick }) {
  const [segments, setSegments] = useState([]);
  const fetchTimeout = useRef(null);

  const fetchSegments = useCallback((map) => {
    const zoom = map.getZoom();
    if (zoom < 11) { setSegments([]); return; }

    clearTimeout(fetchTimeout.current);
    const bounds = map.getBounds();
    fetchTimeout.current = setTimeout(async () => {
      try {
        const data = await getMapSegments({
          north: bounds.getNorth(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          west: bounds.getWest(),
        }, mode);
        setSegments(data.segments || []);
      } catch (e) {
        console.error('Failed to fetch segments:', e);
      }
    }, 300);
  }, [mode]);

  const map = useMapEvents({
    moveend: () => fetchSegments(map),
    zoomend: () => fetchSegments(map),
  });

  useEffect(() => {
    fetchSegments(map);
  }, [map, fetchSegments]);

  return segments.map(seg => (
    <CircleMarker
      key={seg.ogf_id}
      center={[seg.lat, seg.lng]}
      radius={6}
      pathOptions={{
        color: scoreColor(seg.score),
        fillColor: scoreColor(seg.score),
        fillOpacity: 0.8,
        weight: 1,
      }}
      eventHandlers={{ click: () => onSegmentClick(seg) }}
    />
  ));
}

function PersonalLayer({ stops, onStopClick }) {
  return stops.map(stop => (
    <CircleMarker
      key={stop.stop_id}
      center={[stop.lat, stop.lng]}
      radius={8}
      pathOptions={{
        color: stopColor(stop.productive),
        fillColor: stopColor(stop.productive),
        fillOpacity: 0.9,
        weight: 2,
      }}
      eventHandlers={{ click: () => onStopClick(stop) }}
    />
  ));
}

export default function Map() {
  const [mapMode, setMapMode] = useState('personal');
  const [exploreMode, setExploreMode] = useState('balanced');
  const [myStops, setMyStops] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loadingStops, setLoadingStops] = useState(true);

  useEffect(() => {
    getMyStops()
      .then(data => {
        setMyStops(data.stops || []);
        setLoadingStops(false);
      })
      .catch(() => setLoadingStops(false));
  }, []);

  const defaultCenter = [43.5, -79.8];
  const defaultZoom = 10;

  return (
    <div style={{
      height: '100dvh', display: 'flex', flexDirection: 'column',
      background: 'radial-gradient(circle at 50% 0%, var(--fx-bg-grad-1), var(--fx-bg-grad-2) 45%, var(--fx-bg-grad-3) 100%)',
    }}>

      {/* Header */}
      <div style={{
        padding: '12px 16px',
        background: 'var(--fx-canvas)',
        borderBottom: '1px solid var(--fx-hairline)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        zIndex: 1000,
        flexShrink: 0,
      }}>
        <h1 style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 17, color: 'var(--fx-text-primary-2)', margin: 0 }}>Map</h1>

        <div style={{
          display: 'flex',
          background: 'var(--fx-card-fill)',
          border: '1px solid var(--fx-hairline)',
          borderRadius: 8,
          padding: 2,
          gap: 2,
        }}>
          {['personal', 'explore'].map(m => (
            <button
              key={m}
              onClick={() => setMapMode(m)}
              style={{
                padding: '5px 12px',
                borderRadius: 6,
                border: 'none',
                background: mapMode === m ? 'var(--fx-moss-light)' : 'transparent',
                color: mapMode === m ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)',
                fontFamily: 'var(--fx-font-ui)',
                fontSize: 12,
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s',
                textTransform: 'capitalize',
              }}
            >
              {m}
            </button>
          ))}
        </div>

        {mapMode === 'explore' && (
          <select
            value={exploreMode}
            onChange={e => setExploreMode(e.target.value)}
            style={{
              background: 'var(--fx-card-fill)',
              border: '1px solid var(--fx-hairline)',
              borderRadius: 6,
              color: 'var(--fx-text-primary)',
              fontFamily: 'var(--fx-font-ui)',
              fontSize: 11,
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            <option value="balanced">Balanced</option>
            <option value="easy">Easy access</option>
            <option value="adventure">Adventure</option>
          </select>
        )}
      </div>

      {/* Map */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <MapContainer
          center={defaultCenter}
          zoom={defaultZoom}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; OpenStreetMap &copy; CARTO'
            maxZoom={19}
          />

          {mapMode === 'personal' && (
            <PersonalLayer stops={myStops} onStopClick={setSelected} />
          )}

          {mapMode === 'explore' && (
            <ExploreLayer mode={exploreMode} onSegmentClick={setSelected} />
          )}
        </MapContainer>

        {mapMode === 'personal' && !loadingStops && myStops.length === 0 && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'var(--fx-card-fill)',
            border: '1px solid var(--fx-hairline)',
            borderRadius: 14,
            padding: '20px 24px',
            textAlign: 'center',
            zIndex: 1000,
            maxWidth: 240,
          }}>
            <div aria-hidden="true" style={{ fontSize: 28, marginBottom: 8 }}>🎣</div>
            <div style={{ fontFamily: 'var(--fx-font-serif)', fontSize: 16, fontWeight: 600, color: 'var(--fx-text-primary-2)', marginBottom: 6 }}>
              Your map is empty
            </div>
            <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)', lineHeight: 1.5 }}>
              Log trips with GPS to see your spots appear here.
              Switch to Explore to find new water.
            </div>
          </div>
        )}

        {mapMode === 'explore' && (
          <div style={{
            position: 'absolute',
            bottom: 80, left: '50%',
            transform: 'translateX(-50%)',
            background: 'color-mix(in srgb, var(--fx-card-fill) 90%, transparent)',
            border: '1px solid var(--fx-hairline)',
            borderRadius: 20,
            padding: '6px 14px',
            fontFamily: 'var(--fx-font-ui)',
            fontSize: 11,
            color: 'var(--fx-text-muted)',
            zIndex: 1000,
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
          }}>
            Zoom in to see spots
          </div>
        )}
      </div>

      {/* Bottom sheet. Intentionally a lightweight detail panel, not a true
          modal: no focus trap, no Escape-to-close, background map stays
          interactive. role="dialog" + aria-label identify it as a distinct
          region for assistive tech without the false promise of aria-modal. */}
      {selected && (
        <div role="dialog" aria-label="Location details" style={{
          position: 'fixed',
          bottom: 64, left: 0, right: 0,
          maxWidth: 480, margin: '0 auto',
          background: 'var(--fx-card-fill)',
          borderTop: '1px solid var(--fx-hairline)',
          borderRadius: '16px 16px 0 0',
          padding: '16px 16px 24px',
          zIndex: 2000,
        }}>
          <button
            onClick={() => setSelected(null)}
            aria-label="Close"
            style={{
              position: 'absolute', top: 4, right: 8,
              width: 44, height: 44,
              background: 'none', border: 'none',
              color: 'var(--fx-text-muted)', fontSize: 20, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          ><span aria-hidden="true">×</span></button>

          {/* Personal stop detail */}
          {selected.stop_id && (
            <>
              <div style={{ fontFamily: 'var(--fx-font-serif)', fontSize: 16, fontWeight: 600, color: 'var(--fx-text-primary-2)', marginBottom: 4 }}>
                {selected.location}
              </div>
              <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)', marginBottom: 10 }}>
                {selected.date}
              </div>
              {(selected.conditions?.air_temp_c != null || selected.conditions?.pressure_hpa != null) && (
                <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
                  {selected.conditions?.air_temp_c != null && (
                    <InstrumentDial value={selected.conditions.air_temp_c} unit="°C" label="Air temp" min={-10} max={35} />
                  )}
                  {selected.conditions?.pressure_hpa != null && (
                    <InstrumentDial value={selected.conditions.pressure_hpa} unit="" label="Pressure hPa" min={970} max={1040} />
                  )}
                </div>
              )}
              {selected.species.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {selected.species.map((sp, i) => (
                    <span key={i} style={{
                      background: 'var(--fx-card-fill-quiet)', color: 'var(--fx-moss-light)',
                      fontFamily: 'var(--fx-font-ui)',
                      borderRadius: 6, padding: '3px 8px', fontSize: 11,
                    }}>{sp}</span>
                  ))}
                </div>
              ) : (
                <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)' }}>No fish logged</div>
              )}
              {selected.technique && (
                <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-text-muted)', marginTop: 8 }}>
                  {selected.technique}
                  {selected.gear ? ` · ${selected.gear}` : ''}
                </div>
              )}
            </>
          )}

          {/* Explore segment detail */}
          {selected.ogf_id && (
            <>
              <div style={{ fontFamily: 'var(--fx-font-serif)', fontSize: 16, fontWeight: 600, color: 'var(--fx-text-primary-2)', marginBottom: 4 }}>
                {selected.watercourse_name || selected.nearest_named_stream || 'Unnamed stream'}
              </div>
              <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)', marginBottom: 10 }}>
                Stream order {selected.stream_order}
                {selected.is_confluence ? ' · Confluence' : ''}
                {selected.connected_to_waterbody ? ' · Connected to lake/river' : ''}
              </div>

              <div style={{ marginBottom: 10 }}>
                <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-text-muted)', marginBottom: 4 }}>
                  Exploration score
                </div>
                <div style={{
                  height: 6, background: 'var(--fx-hairline)', borderRadius: 3, overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%',
                    width: '100%',
                    transform: `scaleX(${selected.score || 0})`,
                    transformOrigin: 'left',
                    background: scoreColor(selected.score),
                    borderRadius: 3,
                    transition: 'transform 0.3s',
                  }} />
                </div>
                <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 10, color: 'var(--fx-text-muted)', marginTop: 2 }}>
                  {((selected.score || 0) * 100).toFixed(0)}/100
                </div>
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                {selected.google_maps_url && (
                  <a
                    href={selected.google_maps_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      flex: 1, padding: '8px',
                      background: 'var(--fx-hairline)', color: 'var(--fx-text-primary)',
                      fontFamily: 'var(--fx-font-ui)',
                      borderRadius: 8, fontSize: 12, fontWeight: 500,
                      textAlign: 'center', textDecoration: 'none',
                    }}
                  >
                    Open in Maps
                  </a>
                )}
                {selected.swoop_url && (
                  <a
                    href={selected.swoop_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      flex: 1, padding: '8px',
                      background: 'var(--fx-hairline)', color: 'var(--fx-text-primary)',
                      fontFamily: 'var(--fx-font-ui)',
                      borderRadius: 8, fontSize: 12, fontWeight: 500,
                      textAlign: 'center', textDecoration: 'none',
                    }}
                  >
                    Satellite view
                  </a>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
