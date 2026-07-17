import { useState, useEffect } from 'react';
import Chat from './screens/Chat';
import LogTrip from './screens/LogTrip';
import Trips from './screens/Trips';
import Login from './screens/Login';
import Map from './screens/Map';
import FishDex from './screens/FishDex';
import NavBar from './components/NavBar';
import { getMe, devBootstrapLogin } from './api';

export default function App() {
  const [screen, setScreen] = useState('chat');
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    // TEMPORARY DEV-ONLY BYPASS — REMOVE BEFORE THIS BRANCH IS MERGED OR
    // DEPLOYED TO RAILWAY. Skips the invite-code Login screen locally by
    // auto-logging in via /admin/bootstrap. Gated on import.meta.env.DEV,
    // which Vite hardcodes to `false` in production builds (`vite build`)
    // — this block is dead code in anything actually shipped, but remove
    // it anyway once local testing is done; don't rely on the gate alone.
    // Also fires when a stale/invalid token is sitting in localStorage
    // (e.g. from a previous local server) instead of leaving the user
    // stranded on Login after the 401 clears it.
    function devBypass() {
      if (!import.meta.env.DEV) return false;
      console.warn(
        '[DEV ONLY] Auto-login bypass active — remove this block in App.jsx before merging/deploying.'
      );
      devBootstrapLogin()
        .then(data => {
          localStorage.setItem('fishbot_token', data.token);
          localStorage.setItem('fishbot_user', JSON.stringify({
            id: data.user_id,
            username: data.username,
          }));
          setUser({ id: data.user_id, username: data.username });
        })
        .catch(() => {
          // Backend not reachable, or FISHBOT_API_KEY set (production) —
          // fall back to the normal Login screen.
        })
        .finally(() => setAuthChecked(true));
      return true;
    }

    const token = localStorage.getItem('fishbot_token');
    if (!token) {
      if (devBypass()) return;
      setAuthChecked(true);
      return;
    }
    getMe().then(me => {
      if (me) {
        setUser(me);
        localStorage.setItem('fishbot_user', JSON.stringify(me));
        setAuthChecked(true);
      } else {
        localStorage.removeItem('fishbot_token');
        localStorage.removeItem('fishbot_user');
        if (!devBypass()) setAuthChecked(true);
      }
    }).catch(() => {
      // network error — keep token, try again later
      const stored = localStorage.getItem('fishbot_user');
      if (stored) {
        try { setUser(JSON.parse(stored)); } catch {}
      }
      setAuthChecked(true);
    });
  }, []);

  function handleLogin(data) {
    setUser({ id: data.user_id, username: data.username, display_name: data.display_name });
  }

  function handleLogout() {
    localStorage.removeItem('fishbot_token');
    localStorage.removeItem('fishbot_user');
    setUser(null);
  }

  if (!authChecked) {
    return (
      <div style={{
        minHeight: '100vh',
        background: 'var(--color-base-bark)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--color-text-ash)',
        fontSize: '14px',
      }}>
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    // maxWidth: 480 is an intentional mobile-first constraint, not an
    // oversight — PRODUCT.md's primary use case is one-handed, stream-side.
    // Wider viewports (the stated desk/planning use case) currently get the
    // same centered mobile column; revisit with a real wide-viewport layout
    // in a future pass rather than stretching this shell ad hoc.
    <div style={{
      maxWidth: 480,
      margin: '0 auto',
      minHeight: '100dvh',
      position: 'relative',
      background: 'var(--color-base-bark)',
    }}>
      {screen === 'chat' && <Chat onNavigate={setScreen} user={user} onLogout={handleLogout} />}
      {screen === 'map' && <Map />}
      {screen === 'log' && <LogTrip onNavigate={setScreen} />}
      {screen === 'trips' && <Trips onNavigate={setScreen} />}
      {screen === 'fishdex' && <FishDex onNavigate={setScreen} />}
      <NavBar screen={screen} onNavigate={setScreen} />
    </div>
  );
}
