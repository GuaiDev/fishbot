export default function NavBar({ screen, onNavigate }) {
  const tabs = [
    { id: 'chat', label: 'Chat', icon: '💬' },
    { id: 'map', label: 'Map', icon: '🗺️' },
    { id: 'log', label: 'Log', icon: '＋' },
    { id: 'trips', label: 'Trips', icon: '📋' },
  ];

  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      maxWidth: 480, margin: '0 auto',
      background: 'var(--color-surface-loam)',
      borderTop: '1px solid var(--color-border-twig)',
      display: 'flex',
      padding: '8px 0 20px',
      zIndex: 100,
    }}>
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onNavigate(tab.id)}
          style={{
            flex: 1,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 3,
            padding: '6px 0',
            color: screen === tab.id ? 'var(--color-moss)' : 'var(--color-text-ash)',
            fontSize: 10,
            fontWeight: screen === tab.id ? 600 : 400,
            transition: 'color 0.15s',
          }}
        >
          <span aria-hidden="true" style={{ fontSize: 20 }}>{tab.icon}</span>
          <span>{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
