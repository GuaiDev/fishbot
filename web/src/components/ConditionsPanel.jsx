import InstrumentDial from './InstrumentDial';
import { skyLabel, trendMark, formatCoords, sourceCaption } from '../conditions-format';
import '../chat-instrument.css';

// The Chat coach's "showing its work" evidence panel — the same real
// conditions the coach reasons from, rendered two ways for comparison.
// Both consume the identical /conditions payload; they differ only in visual
// vocabulary (and, for the instrument direction, information hierarchy).

function signed(n) {
  if (n == null) return '—';
  const r = Math.round(n * 10) / 10;
  return r > 0 ? `+${r}` : `${r}`;
}

// ─────────────────────────────────────────────────────────────────────────
// Version A — Field Journal. On-system (--fx-*), Spectral serif, moss/brass.
// A page in the journal: dials + the coach's own note in scientific italics.
// ─────────────────────────────────────────────────────────────────────────
function ConditionsJournal({ data }) {
  const { location, temperature_c, pressure_hpa, wind_speed_kmh, humidity_pct } = data;
  const sky = skyLabel(data.weather_code);
  const tm = trendMark(data.pressure_trend);

  const readRow = (label, value) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 14 }}>
      <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-text-dim)', letterSpacing: '.04em' }}>{label}</span>
      <span style={{ fontFamily: 'var(--fx-font-serif)', fontSize: 15, fontWeight: 600, color: 'var(--fx-text-primary)' }}>{value}</span>
    </div>
  );

  return (
    <div style={{
      position: 'relative',
      margin: '4px 16px 14px',
      padding: '14px 16px 15px',
      borderRadius: 14,
      background: 'var(--fx-card-fill-quiet)',
      border: '1px solid var(--fx-hairline)',
      borderTop: '2px solid var(--fx-brass)',
    }}>
      {/* eyebrow: label + real place */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--fx-moss-light)', boxShadow: '0 0 8px var(--fx-moss-light)' }} />
          <span style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', color: 'var(--fx-moss-light)' }}>
            Conditions
          </span>
          <span style={{ fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 14, color: 'var(--fx-text-primary)' }}>
            {location.name}
          </span>
        </div>
      </div>

      {/* dials + secondary readings */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <InstrumentDial value={Math.round(temperature_c)} unit="°C" label="AIR TEMP" min={-20} max={40} />
        <div style={{ position: 'relative' }}>
          <InstrumentDial value={Math.round(pressure_hpa)} unit="" label="PRESSURE hPa" min={980} max={1040} />
          {/* trend arrow — brass, the presence-carrying precision index */}
          <div style={{
            position: 'absolute', top: -2, right: -6,
            fontFamily: 'var(--fx-font-serif)', fontSize: 17, fontWeight: 700, color: 'var(--fx-brass-light)',
          }} title={`Pressure ${tm.word}`}>{tm.glyph}</div>
        </div>

        <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--fx-hairline)', margin: '4px 2px' }} />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {readRow('Wind', wind_speed_kmh != null ? `${Math.round(wind_speed_kmh)} km/h` : '—')}
          {readRow('Sky', sky || '—')}
          {readRow('Humidity', humidity_pct != null ? `${Math.round(humidity_pct)}%` : '—')}
        </div>
      </div>

      {/* the coach's own reasoning, in scientific italics */}
      <div style={{
        marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--fx-hairline)',
        display: 'flex', gap: 10,
      }}>
        <span style={{ width: 2, borderRadius: 2, background: 'var(--fx-brass)', flexShrink: 0 }} />
        <p style={{
          margin: 0, fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 14, lineHeight: 1.5,
          color: 'var(--fx-text-primary-3)',
        }}>
          {data.pressure_note}
        </p>
      </div>

      <div style={{ marginTop: 10, fontFamily: 'var(--fx-font-ui)', fontSize: 10.5, color: 'var(--fx-text-dim)' }}>
        {sourceCaption(location.source, location.name)}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Version B — Ship's Instrument. Off-system (scoped .chat-instrument), cool
// marine palette, monospaced figures. STRUCTURALLY DIVERGES from A: a
// horizontal instrument cluster (headline reading | baro | ledger) with a
// station-identifier line and a calibration ruler — an instrument readout
// wants a different hierarchy than a journal page, so it gets one.
// ─────────────────────────────────────────────────────────────────────────
function ConditionsInstrument({ data }) {
  const { location, temperature_c, pressure_hpa, wind_speed_kmh, humidity_pct, cloud_cover_pct } = data;
  const sky = skyLabel(data.weather_code);
  const tm = trendMark(data.pressure_trend);
  const coords = formatCoords(location.lat, location.lng);

  const mono = 'var(--ci-mono)';
  const ledger = (label, value) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '2px 0' }}>
      <span style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: '.08em', color: 'var(--ci-text-dim)' }}>{label}</span>
      <span style={{ fontFamily: mono, fontSize: 12, color: 'var(--ci-live)' }}>{value}</span>
    </div>
  );

  return (
    <div className="chat-instrument" style={{
      position: 'relative',
      margin: '4px 16px 14px',
      background: 'linear-gradient(180deg, var(--ci-surface), var(--ci-surface-2))',
      border: '1px solid var(--ci-line)',
      borderRadius: 6,
      overflow: 'hidden',
    }}>
      {/* calibration ruler edge */}
      <div className="ci-ruler" />
      <div className="ci-ruler-major" />

      <div style={{ padding: '11px 15px 14px' }}>
        {/* station identifier — min-width:0 lets it truncate instead of
            forcing horizontal overflow at narrow widths */}
        <div style={{ display: 'flex', marginBottom: 13, minWidth: 0 }}>
          <span style={{ fontFamily: mono, fontSize: 10.5, letterSpacing: '.1em', color: 'var(--ci-text-muted)', textTransform: 'uppercase', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, flex: 1 }}>
            <span style={{ color: 'var(--ci-brass)' }}>STATION</span> · {location.name}{coords ? ` · ${coords}` : ''}
          </span>
        </div>

        {/* instrument cluster */}
        <div style={{ display: 'flex', alignItems: 'stretch', gap: 11 }}>
          {/* headline reading */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
              <span style={{ fontFamily: mono, fontSize: 29, fontWeight: 500, color: 'var(--ci-live)', lineHeight: 1 }}>
                {temperature_c != null ? temperature_c.toFixed(1) : '—'}
              </span>
              <span style={{ fontFamily: mono, fontSize: 13, color: 'var(--ci-text-muted)' }}>°C</span>
            </div>
            <span style={{ fontFamily: mono, fontSize: 10, letterSpacing: '.14em', color: 'var(--ci-text-dim)', marginTop: 5 }}>AIR</span>
          </div>

          <div style={{ width: 1, background: 'var(--ci-line)' }} />

          {/* barometer */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
              <span style={{ fontFamily: mono, fontSize: 20, color: 'var(--ci-live)', lineHeight: 1 }}>
                {pressure_hpa != null ? Math.round(pressure_hpa) : '—'}
              </span>
              <span style={{ fontFamily: mono, fontSize: 15, color: 'var(--ci-brass)' }} title={`Pressure ${tm.word}`}>{tm.glyph}</span>
            </div>
            <div style={{ marginTop: 5 }}>
              <span style={{ fontFamily: mono, fontSize: 9.5, letterSpacing: '.08em', color: 'var(--ci-text-dim)' }}>BARO </span>
              <span style={{ fontFamily: mono, fontSize: 9.5, color: 'var(--ci-brass)' }}>Δ{signed(data.pressure_delta_24h_hpa)}</span>
            </div>
          </div>

          <div style={{ width: 1, background: 'var(--ci-line)' }} />

          {/* secondary ledger */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0 }}>
            {ledger('WIND', wind_speed_kmh != null ? `${Math.round(wind_speed_kmh)} km/h` : '—')}
            {ledger('SKY', sky || '—')}
            {ledger('HUM', humidity_pct != null ? `${Math.round(humidity_pct)}%` : '—')}
            {ledger('CLOUD', cloud_cover_pct != null ? `${Math.round(cloud_cover_pct)}%` : '—')}
          </div>
        </div>

        {/* annotation readout — the coach's reasoning as an instrument note */}
        <div style={{ marginTop: 13, paddingTop: 11, borderTop: '1px solid var(--ci-line-soft)', display: 'flex', gap: 8 }}>
          <span style={{ fontFamily: mono, fontSize: 13, color: 'var(--ci-brass)', flexShrink: 0 }}>▸</span>
          <p style={{ margin: 0, fontFamily: 'var(--fx-font-ui)', fontSize: 13, lineHeight: 1.5, color: 'var(--ci-text)' }}>
            {data.pressure_note}
          </p>
        </div>

        <div style={{ marginTop: 9, fontFamily: mono, fontSize: 10, letterSpacing: '.05em', color: 'var(--ci-text-dim)', textTransform: 'uppercase' }}>
          {sourceCaption(location.source, location.name)}
        </div>
      </div>
    </div>
  );
}

export default function ConditionsPanel({ data, variant }) {
  if (!data) return null;
  return variant === 'instrument'
    ? <ConditionsInstrument data={data} />
    : <ConditionsJournal data={data} />;
}
