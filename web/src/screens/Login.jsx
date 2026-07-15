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
      background: 'var(--color-base-bark)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
    }}>
      <div style={{ marginBottom: '32px', textAlign: 'center' }}>
        <div aria-hidden="true" style={{ fontSize: '48px', marginBottom: '12px' }}>🎣</div>
        <h1 style={{ color: 'var(--color-text-bone)', fontSize: '24px', margin: 0 }}>FishBot</h1>
        <p style={{ color: 'var(--color-text-ash)', fontSize: '14px', marginTop: '8px' }}>
          Enter your invite code to get started
        </p>
      </div>

      <form onSubmit={handleSubmit} style={{ width: '100%', maxWidth: '360px' }}>
        <div style={{ marginBottom: '16px' }}>
          <label htmlFor="invite-code" style={{ color: 'var(--color-text-ash)', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            INVITE CODE
          </label>
          <input
            id="invite-code"
            type="text"
            value={code}
            onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="A3KX9P2Q"
            required
            maxLength={12}
            style={{
              width: '100%',
              padding: '12px 14px',
              background: 'var(--color-surface-loam)',
              border: '1px solid var(--color-border-twig)',
              borderRadius: '8px',
              color: 'var(--color-text-bone)',
              fontSize: '16px',
              fontFamily: 'monospace',
              letterSpacing: '2px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label htmlFor="username" style={{ color: 'var(--color-text-ash)', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            USERNAME
          </label>
          <input
            id="username"
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
              background: 'var(--color-surface-loam)',
              border: '1px solid var(--color-border-twig)',
              borderRadius: '8px',
              color: 'var(--color-text-bone)',
              fontSize: '16px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
          <p style={{ color: 'var(--color-text-ash)', fontSize: '11px', marginTop: '4px' }}>
            Letters and numbers only, 2–20 characters
          </p>
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label htmlFor="display-name" style={{ color: 'var(--color-text-ash)', fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            DISPLAY NAME (optional)
          </label>
          <input
            id="display-name"
            type="text"
            value={displayName}
            onChange={e => setDisplayName(e.target.value)}
            placeholder="Jake"
            maxLength={40}
            style={{
              width: '100%',
              padding: '12px 14px',
              background: 'var(--color-surface-loam)',
              border: '1px solid var(--color-border-twig)',
              borderRadius: '8px',
              color: 'var(--color-text-bone)',
              fontSize: '16px',
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />
        </div>

        {error && (
          <div style={{
            background: 'var(--color-rust-bg)',
            border: '1px solid var(--color-rust-border)',
            borderRadius: '8px',
            padding: '12px',
            marginBottom: '16px',
            color: 'var(--color-rust)',
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
            background: loading ? 'var(--color-moss-fill-dim)' : 'var(--color-moss-fill)',
            color: 'var(--color-text-bone)',
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
