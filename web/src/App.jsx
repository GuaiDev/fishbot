import { useState, useEffect } from 'react';
import Chat from './screens/Chat';
import LogTrip from './screens/LogTrip';
import Trips from './screens/Trips';
import Login from './screens/Login';
import Map from './screens/Map';
import NavBar from './components/NavBar';
import { getMe } from './api';

export default function App() {
  const [screen, setScreen] = useState('chat');
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('fishbot_token');
    if (!token) {
      setAuthChecked(true);
      return;
    }
    getMe().then(me => {
      if (me) {
        setUser(me);
        localStorage.setItem('fishbot_user', JSON.stringify(me));
      } else {
        localStorage.removeItem('fishbot_token');
        localStorage.removeItem('fishbot_user');
      }
    }).catch(() => {
      // network error — keep token, try again later
      const stored = localStorage.getItem('fishbot_user');
      if (stored) {
        try { setUser(JSON.parse(stored)); } catch {}
      }
    }).finally(() => setAuthChecked(true));
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
      <NavBar screen={screen} onNavigate={setScreen} />
    </div>
  );
}
