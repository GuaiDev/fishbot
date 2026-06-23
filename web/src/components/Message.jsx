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
        background: isBot ? '#1A1D27' : '#1D9E75',
        borderLeft: isBot ? '2px solid #1D9E75' : 'none',
        color: isBot ? '#E8EAF0' : '#FFFFFF',
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
