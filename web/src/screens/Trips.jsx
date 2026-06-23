import { useState, useEffect } from 'react';
import { getSessions } from '../api';

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
      background: '#0F1117',
      padding: '16px 16px 100px',
      maxWidth: 480,
      margin: '0 auto',
    }}>
      <h1 style={{ fontSize: 18, fontWeight: 600, color: '#E8EAF0', marginBottom: 20 }}>
        Your trips
      </h1>

      {loading && (
        <div style={{ color: '#6B7280', fontSize: 14 }}>Loading trips...</div>
      )}

      {error && (
        <div style={{
          padding: '12px 14px', background: '#2A1212',
          color: '#E07B39', borderRadius: 10, fontSize: 14,
        }}>
          {error.includes('404') || error.includes('failed')
            ? 'Trip history coming soon — log your first trip to get started.'
            : `Error: ${error}`}
        </div>
      )}

      {!loading && !error && sessions.length === 0 && (
        <div style={{
          padding: '24px 16px', textAlign: 'center',
          color: '#6B7280', fontSize: 14,
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
              background: '#1A1D27',
              borderRadius: 10,
              padding: '12px 14px',
              border: '1px solid #2A2D3A',
            }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: '#E8EAF0', marginBottom: 2 }}>
                {location}
              </div>
              <div style={{ fontSize: 12, color: '#6B7280', marginBottom: 8 }}>
                {date}
                {conditions?.air_temp_c && ` · ${conditions.air_temp_c}°C`}
                {conditions?.pressure_hpa && ` · ${conditions.pressure_hpa}hPa`}
                {conditions?.anomaly_flag && conditions.anomaly_flag !== 'normal' && (
                  <span style={{ color: '#E07B39' }}> · {conditions.anomaly_flag.replace('_', ' ')}</span>
                )}
              </div>
              {species.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {species.map((sp, j) => (
                    <span key={j} style={{
                      background: '#0F4D38',
                      color: '#1D9E75',
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
