import { useState, useEffect } from 'react';
import { getSessions } from '../api';
import InstrumentDial from '../components/InstrumentDial';

export default function Trips() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getSessions()
      .then(data => {
        setSessions(Array.isArray(data) ? data : data.sessions || []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div style={{
      minHeight: '100dvh',
      background: 'var(--color-base-bark)',
      padding: '16px 16px 100px',
      maxWidth: 480,
      margin: '0 auto',
    }}>
      <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--color-text-bone)', marginBottom: 20 }}>
        Your trips
      </h1>

      {loading && (
        <div style={{ color: 'var(--color-text-ash)', fontSize: 14 }}>Loading trips...</div>
      )}

      {error && (
        <div style={{
          padding: '12px 14px', background: 'var(--color-rust-bg)',
          color: 'var(--color-rust)', borderRadius: 10, fontSize: 14,
        }}>
          {error.includes('404') || error.includes('failed')
            ? 'Trip history coming soon — log your first trip to get started.'
            : `Error: ${error}`}
        </div>
      )}

      {!loading && !error && sessions.length === 0 && (
        <div style={{
          padding: '24px 16px', textAlign: 'center',
          color: 'var(--color-text-ash)', fontSize: 14,
        }}>
          No trips logged yet. Tap + to log your first catch.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {sessions.map((session, i) => {
          const species = session.species_caught || [];
          const date = session.date || session.date_approx || 'Undated';
          const location = session.location || session.primary_location || 'Unknown location';
          const conditions = session.conditions;

          return (
            <div key={i} style={{
              background: 'var(--color-surface-loam)',
              borderRadius: 10,
              padding: '12px 14px',
              border: '1px solid var(--color-border-twig)',
            }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--color-text-bone)', marginBottom: 2 }}>
                {location}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-ash)', marginBottom: 8 }}>
                {date}
                {conditions?.anomaly_flag && conditions.anomaly_flag !== 'normal' && (
                  <span style={{ color: 'var(--color-rust)' }}> · {conditions.anomaly_flag.replace('_', ' ')}</span>
                )}
              </div>
              {(conditions?.air_temp_c != null || conditions?.pressure_hpa != null) && (
                <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
                  {conditions?.air_temp_c != null && (
                    <InstrumentDial value={conditions.air_temp_c} unit="°C" label="Air temp" min={-10} max={35} />
                  )}
                  {conditions?.pressure_hpa != null && (
                    <InstrumentDial value={conditions.pressure_hpa} unit="" label="Pressure hPa" min={970} max={1040} />
                  )}
                </div>
              )}
              {species.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {species.map((sp, j) => (
                    <span key={j} style={{
                      background: 'var(--color-sage-tint-bg)',
                      color: 'var(--color-moss)',
                      borderRadius: 6,
                      padding: '3px 8px',
                      fontSize: 11,
                      fontWeight: 500,
                    }}>
                      {sp}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
