import { useState, useRef, useEffect } from 'react';
import Message from '../components/Message';
import { sendMessage } from '../api';
import GrainOverlay from '../components/GrainOverlay';
import '../fishdex-tokens.css';

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
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      height: '100dvh',
      background: 'radial-gradient(circle at 50% 0%, var(--fx-bg-grad-1), var(--fx-bg-grad-2) 45%, var(--fx-bg-grad-3) 100%)',
    }}>
      <GrainOverlay />

      {/* Header */}
      <div style={{
        padding: '16px 16px 12px',
        borderBottom: '1px solid var(--fx-hairline)',
        background: 'var(--fx-canvas)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%',
            background: 'var(--fx-moss-light)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--fx-font-serif)', fontSize: 16, fontWeight: 600, color: 'var(--fx-on-accent)',
          }}>F</div>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontFamily: 'var(--fx-font-serif)', fontSize: 17, fontWeight: 600, color: 'var(--fx-text-primary-2)', margin: 0 }}>
              FishBot
            </h1>
            <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-text-muted)' }}>
              Ontario freshwater intelligence
            </div>
          </div>
          {user && (
            <button
              onClick={onLogout}
              title={`Logged in as ${displayName}`}
              style={{
                background: 'none',
                border: '1px solid var(--fx-hairline)',
                borderRadius: '20px',
                padding: '4px 10px',
                color: 'var(--fx-text-muted)',
                fontFamily: 'var(--fx-font-ui)',
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
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 16px 80px',
        }}
      >
        {messages.map((msg, i) => (
          <Message key={i} role={msg.role} content={msg.content} />
        ))}
        {loading && (
          <div style={{
            display: 'flex', justifyContent: 'flex-start', marginBottom: 8,
          }}>
            <div role="status" style={{
              padding: '10px 14px',
              borderRadius: '4px 14px 14px 14px',
              background: 'var(--fx-card-fill)',
              borderLeft: '2px solid var(--fx-moss)',
              color: 'var(--fx-text-muted)',
              fontFamily: 'var(--fx-font-ui)',
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
        background: 'var(--fx-canvas)',
        borderTop: '1px solid var(--fx-hairline)',
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
            background: 'var(--fx-moss-light)',
            border: 'none',
            cursor: 'pointer',
            fontSize: 22,
            color: 'var(--fx-on-accent)',
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
            background: 'var(--fx-card-fill)',
            border: '1px solid var(--fx-hairline)',
            borderRadius: 20,
            padding: '10px 14px',
            color: 'var(--fx-text-primary)',
            fontFamily: 'var(--fx-font-ui)',
            fontSize: 14,
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
            background: input.trim() && !loading ? 'var(--fx-moss-light)' : 'var(--fx-hairline)',
            border: 'none',
            cursor: input.trim() && !loading ? 'pointer' : 'default',
            fontSize: 18,
            color: input.trim() && !loading ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)',
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
