import { useState, useRef, useEffect } from 'react';
import Message from '../components/Message';
import { sendMessage } from '../api';

export default function Chat({ onNavigate, user, onLogout }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hey — what's on your mind? Ask me anything about fishing, or tap + to log a catch.",
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setLoading(true);

    try {
      const apiMessages = newMessages
        .filter((_, i) => i > 0) // skip the initial bot greeting
        .map(m => ({ role: m.role, content: m.content }));

      const data = await sendMessage(apiMessages);
      const reply = data.reply || data.content || 'No response.';
      setMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch (err) {
      if (err.status === 401) {
        onLogout?.();
        return;
      }
      const msg = err.status === 429
        ? err.message
        : "Couldn't reach FishBot right now. Check your connection and try again.";
      setMessages(prev => [...prev, { role: 'assistant', content: msg }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const displayName = user?.display_name || user?.username || 'You';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100dvh',
      background: 'var(--color-base-bark)',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 16px 12px',
        borderBottom: '1px solid var(--color-border-twig)',
        background: 'var(--color-base-bark)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            background: 'var(--color-moss-fill)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 600, color: 'var(--color-text-bone)',
          }}>F</div>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text-bone)', margin: 0 }}>
              FishBot
            </h1>
            <div style={{ fontSize: 11, color: 'var(--color-text-ash)' }}>
              Ontario freshwater intelligence
            </div>
          </div>
          {user && (
            <button
              onClick={onLogout}
              title={`Logged in as ${displayName}`}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-twig)',
                borderRadius: '20px',
                padding: '4px 10px',
                color: 'var(--color-text-ash)',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              {displayName}
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px 16px 80px',
      }}>
        {messages.map((msg, i) => (
          <Message key={i} role={msg.role} content={msg.content} />
        ))}
        {loading && (
          <div style={{
            display: 'flex', justifyContent: 'flex-start', marginBottom: 8,
          }}>
            <div style={{
              padding: '10px 14px',
              borderRadius: '4px 14px 14px 14px',
              background: 'var(--color-surface-loam)',
              borderLeft: '2px solid var(--color-moss)',
              color: 'var(--color-text-ash)',
              fontSize: 14,
            }}>
              thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{
        position: 'fixed',
        bottom: 64,
        left: 0, right: 0,
        maxWidth: 480,
        margin: '0 auto',
        padding: '10px 12px',
        background: 'var(--color-base-bark)',
        borderTop: '1px solid var(--color-border-twig)',
        display: 'flex',
        alignItems: 'flex-end',
        gap: 8,
        zIndex: 50,
      }}>
        {/* Log button */}
        <button
          onClick={() => onNavigate('log')}
          aria-label="Log a catch"
          title="Log a catch"
          style={{
            width: 44, height: 44,
            borderRadius: '50%',
            background: 'var(--color-moss-fill)',
            border: 'none',
            cursor: 'pointer',
            fontSize: 22,
            color: 'var(--color-text-bone)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        ><span aria-hidden="true">＋</span></button>

        {/* Text input */}
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything..."
          rows={1}
          style={{
            flex: 1,
            background: 'var(--color-surface-loam)',
            border: '1px solid var(--color-border-twig)',
            borderRadius: 20,
            padding: '10px 14px',
            color: 'var(--color-text-bone)',
            fontSize: 14,
            fontFamily: 'inherit',
            resize: 'none',
            outline: 'none',
            maxHeight: 120,
            overflowY: 'auto',
          }}
          onInput={e => {
            e.target.style.height = 'auto';
            e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
          }}
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          aria-label="Send message"
          style={{
            width: 44, height: 44,
            borderRadius: '50%',
            background: input.trim() && !loading ? 'var(--color-moss-fill)' : 'var(--color-border-twig)',
            border: 'none',
            cursor: input.trim() && !loading ? 'pointer' : 'default',
            fontSize: 18,
            color: 'var(--color-text-bone)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            transition: 'background 0.15s',
          }}
        ><span aria-hidden="true">↑</span></button>
      </div>
    </div>
  );
}
