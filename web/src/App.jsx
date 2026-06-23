import { useState, useEffect } from 'react';
import Chat from './screens/Chat';
import LogTrip from './screens/LogTrip';
import Trips from './screens/Trips';
import Login from './screens/Login';
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
        background: '#0F1117',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#6B7A8D',
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
    <div style={{
      maxWidth: 480,
      margin: '0 auto',
      minHeight: '100dvh',
      position: 'relative',
      background: '#0F1117',
    }}>
      {screen === 'chat' && <Chat onNavigate={setScreen} user={user} onLogout={handleLogout} />}
      {screen === 'log' && <LogTrip onNavigate={setScreen} />}
      {screen === 'trips' && <Trips onNavigate={setScreen} />}
      <NavBar screen={screen} onNavigate={setScreen} />
    </div>
  );
}
