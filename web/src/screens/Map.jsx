import 'leaflet/dist/leaflet.css';
import { useState, useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, CircleMarker, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { getMapSegments, getMyStops } from '../api';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

function scoreColor(score) {
  if (score >= 0.7) return '#e74c3c';
  if (score >= 0.5) return '#e67e22';
  if (score >= 0.3) return '#f1c40f';
  if (score >= 0.1) return '#2ecc71';
  return '#3498db';
}

function stopColor(productive) {
  return productive ? '#1D9E75' : '#6B7280';
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
    <div style={{ height: '100dvh', display: 'flex', flexDirection: 'column', background: '#0F1117' }}>

      {/* Header */}
      <div style={{
        padding: '12px 16px',
        background: '#0F1117',
        borderBottom: '1px solid #2A2D3A',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        zIndex: 1000,
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 15, fontWeight: 600, color: '#E8EAF0' }}>Map</span>

        <div style={{
          display: 'flex',
          background: '#1A1D27',
          border: '1px solid #2A2D3A',
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
                background: mapMode === m ? '#1D9E75' : 'transparent',
                color: mapMode === m ? 'white' : '#6B7280',
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
              background: '#1A1D27',
              border: '1px solid #2A2D3A',
              borderRadius: 6,
              color: '#E8EAF0',
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
          zoomControl={false}
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
            background: '#1A1D27',
            border: '1px solid #2A2D3A',
            borderRadius: 12,
            padding: '20px 24px',
            textAlign: 'center',
            zIndex: 1000,
            maxWidth: 240,
          }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>🎣</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: '#E8EAF0', marginBottom: 6 }}>
              Your map is empty
            </div>
            <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.5 }}>
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
            background: 'rgba(26,29,39,0.9)',
            border: '1px solid #2A2D3A',
            borderRadius: 20,
            padding: '6px 14px',
            fontSize: 11,
            color: '#6B7280',
            zIndex: 1000,
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
          }}>
            Zoom in to see spots
          </div>
        )}
      </div>

      {/* Bottom sheet */}
      {selected && (
        <div style={{
          position: 'fixed',
          bottom: 64, left: 0, right: 0,
          maxWidth: 480, margin: '0 auto',
          background: '#1A1D27',
          borderTop: '1px solid #2A2D3A',
          borderRadius: '16px 16px 0 0',
          padding: '16px 16px 24px',
          zIndex: 2000,
        }}>
          <button
            onClick={() => setSelected(null)}
            style={{
              position: 'absolute', top: 12, right: 16,
              background: 'none', border: 'none',
              color: '#6B7280', fontSize: 20, cursor: 'pointer',
            }}
          >×</button>

          {/* Personal stop detail */}
          {selected.stop_id && (
            <>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#E8EAF0', marginBottom: 4 }}>
                {selected.location}
              </div>
              <div style={{ fontSize: 12, color: '#6B7280', marginBottom: 10 }}>
                {selected.date}
                {selected.conditions?.air_temp_c && ` · ${selected.conditions.air_temp_c}°C`}
                {selected.conditions?.pressure_hpa && ` · ${selected.conditions.pressure_hpa}hPa`}
              </div>
              {selected.species.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {selected.species.map((sp, i) => (
                    <span key={i} style={{
                      background: '#0F4D38', color: '#1D9E75',
                      borderRadius: 6, padding: '3px 8px', fontSize: 11,
                    }}>{sp}</span>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: '#6B7280' }}>No fish logged</div>
              )}
              {selected.technique && (
                <div style={{ fontSize: 11, color: '#6B7280', marginTop: 8 }}>
                  {selected.technique}
                  {selected.gear ? ` · ${selected.gear}` : ''}
                </div>
              )}
            </>
          )}

          {/* Explore segment detail */}
          {selected.ogf_id && (
            <>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#E8EAF0', marginBottom: 4 }}>
                {selected.watercourse_name || selected.nearest_named_stream || 'Unnamed stream'}
              </div>
              <div style={{ fontSize: 12, color: '#6B7280', marginBottom: 10 }}>
                Stream order {selected.stream_order}
                {selected.is_confluence ? ' · Confluence' : ''}
                {selected.connected_to_waterbody ? ' · Connected to lake/river' : ''}
              </div>

              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>
                  Exploration score
                </div>
                <div style={{
                  height: 6, background: '#2A2D3A', borderRadius: 3, overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%',
                    width: `${(selected.score || 0) * 100}%`,
                    background: scoreColor(selected.score),
                    borderRadius: 3,
                    transition: 'width 0.3s',
                  }} />
                </div>
                <div style={{ fontSize: 10, color: '#6B7280', marginTop: 2 }}>
                  {((selected.score || 0) * 100).toFixed(0)}/100
                </div>
              </div>

              {selected.top1_species && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>
                    Likely species
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <span style={{
                      background: '#0F4D38', color: '#1D9E75',
                      borderRadius: 6, padding: '3px 8px', fontSize: 11,
                    }}>
                      {selected.top1_species}{selected.top1_prob
                        ? ` (${(selected.top1_prob * 100).toFixed(0)}%)`
                        : ''}
                    </span>
                    {selected.top2_species && (
                      <span style={{
                        background: '#1A1D27', color: '#6B7280',
                        border: '1px solid #2A2D3A',
                        borderRadius: 6, padding: '3px 8px', fontSize: 11,
                      }}>
                        {selected.top2_species}
                      </span>
                    )}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                {selected.google_maps_url && (
                  <a
                    href={selected.google_maps_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      flex: 1, padding: '8px',
                      background: '#2A2D3A', color: '#E8EAF0',
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
                      background: '#2A2D3A', color: '#E8EAF0',
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
