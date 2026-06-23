import { useState } from 'react';
import { signup } from '../api';

export default function Login({ onLogin }) {
  const [code, setCode] = useState('');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await signup(code.trim().toUpperCase(), username.trim(), displayName.trim());
      localStorage.setItem('fishbot_token', data.token);
      localStorage.setItem('fishbot_user', JSON.stringify({
        id: data.user_id,
        username: data.username,
        display_name: data.display_name,
      }));
      onLogin(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0F1117',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
    }}>
      <div style={{ marginBottom: '32px', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', marginBottom: '12px' }}>🎣</div>
        <h1 style={{ color: '#F0F4F8', fontSize: '24px', margin: 0 }}>FishBot</h1>
        <p style={{ color: '#6B7A8D', fontSize: '14px', marginTop: '8px' }}>
          Enter your invite code to get started
        </p>
      </div>

      <form onSubmit={handleSubmit} style={{ width: '100%', maxWidth: '360px' }}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ color: '#6B7A8D', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            INVITE CODE
          </label>
          <input
            type="text"
            value={code}
            onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="A3KX9P2Q"
            required
            maxLength={12}
            style={{
              width: '100%',
              padding: '12px 14px',
              background: '#1A1D27',
              border: '1px solid #2A2D3A',
              borderRadius: '8px',
              color: '#F0F4F8',
              fontSize: '16px',
              fontFamily: 'monospace',
              letterSpacing: '2px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ color: '#6B7A8D', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            USERNAME
          </label>
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, ''))}
            placeholder="jake"
            required
            minLength={2}
            maxLength={20}
            style={{
              width: '100%',
              padding: '12px 14px',
              background: '#1A1D27',
              border: '1px solid #2A2D3A',
              borderRadius: '8px',
              color: '#F0F4F8',
              fontSize: '16px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
          <p style={{ color: '#6B7A8D', fontSize: '11px', marginTop: '4px' }}>
            Letters and numbers only, 2–20 characters
          </p>
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ color: '#6B7A8D', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            DISPLAY NAME (optional)
          </label>
          <input
            type="text"
            value={displayName}
            onChange={e => setDisplayName(e.target.value)}
            placeholder="Jake"
            maxLength={40}
            style={{
              width: '100%',
              padding: '12px 14px',
              background: '#1A1D27',
              border: '1px solid #2A2D3A',
              borderRadius: '8px',
              color: '#F0F4F8',
              fontSize: '16px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
        </div>

        {error && (
          <div style={{
            background: '#2D1A1A',
            border: '1px solid #5C2A2A',
            borderRadius: '8px',
            padding: '12px',
            marginBottom: '16px',
            color: '#E57373',
            fontSize: '14px',
          }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            width: '100%',
            padding: '14px',
            background: loading ? '#164D3A' : '#1D9E75',
            color: '#fff',
            border: 'none',
            borderRadius: '8px',
            fontSize: '16px',
            fontWeight: '600',
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? 'Joining…' : 'Join FishBot'}
        </button>
      </form>
    </div>
  );
}
