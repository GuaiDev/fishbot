import { useState } from 'react';
import Chat from './screens/Chat';
import LogTrip from './screens/LogTrip';
import Trips from './screens/Trips';
import NavBar from './components/NavBar';

export default function App() {
  const [screen, setScreen] = useState('chat');

  return (
    <div style={{
      maxWidth: 480,
      margin: '0 auto',
      minHeight: '100dvh',
      position: 'relative',
      background: '#0F1117',
    }}>
      {screen === 'chat' && <Chat onNavigate={setScreen} />}
      {screen === 'log' && <LogTrip onNavigate={setScreen} />}
      {screen === 'trips' && <Trips onNavigate={setScreen} />}
      <NavBar screen={screen} onNavigate={setScreen} />
    </div>
  );
}
