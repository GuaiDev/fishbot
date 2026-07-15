export default function Message({ role, content }) {
  const isBot = role === 'assistant';

  return (
    <div style={{
      display: 'flex',
      justifyContent: isBot ? 'flex-start' : 'flex-end',
      marginBottom: 8,
    }}>
      <div style={{
        maxWidth: '80%',
        padding: '10px 14px',
        borderRadius: isBot ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
        background: isBot ? 'var(--color-surface-loam)' : 'var(--color-moss-fill)',
        borderLeft: isBot ? '2px solid var(--color-moss)' : 'none',
        color: 'var(--color-text-bone)',
        fontSize: 14,
        lineHeight: 1.5,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {content}
      </div>
    </div>
  );
}
