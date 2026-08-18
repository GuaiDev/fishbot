import { useState, useRef, useEffect } from 'react';
import Message from '../components/Message';
import { sendMessage, getConditions, getSessions } from '../api';
import GrainOverlay from '../components/GrainOverlay';
import CompassWatermark from '../components/CompassWatermark';
import ConditionsPanel from '../components/ConditionsPanel';
import { seasonNote } from '../conditions-format';
import '../fishdex-tokens.css';

// Dev-only toggle to compare the two Chat design directions side by side
// (same pattern as FishDex's DevViewOverride). Dead code in production
// builds (import.meta.env.DEV is false).
function DevVariantToggle({ value, onChange }) {
  if (!import.meta.env.DEV) return null;
  const options = [
    { id: 'journal', label: 'Journal' },
    { id: 'instrument', label: 'Instrument' },
  ];
  return (
    <div style={{
      position: 'fixed', top: 8, right: 8, zIndex: 200,
      display: 'flex', gap: 4, padding: 4,
      background: 'rgba(9,10,6,.85)', borderRadius: 10, border: '1px solid var(--fx-hairline)',
    }}>
      {options.map(opt => (
        <button key={opt.id} type="button" onClick={() => onChange(opt.id)}
          style={{
            font: '600 9px system-ui', letterSpacing: '.03em', padding: '4px 7px',
            borderRadius: 6, border: 'none', cursor: 'pointer',
            background: value === opt.id ? 'var(--fx-moss-light)' : 'transparent',
            color: value === opt.id ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)',
          }}>
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default function Chat({ onNavigate, user, onLogout }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hey — what's on your mind? Ask me anything about fishing, or tap + to log a catch.",
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conditions, setConditions] = useState(null);
  const [headerLine, setHeaderLine] = useState(`We're into ${seasonNote()} on Ontario water.`);
  const [variant, setVariant] = useState('journal');
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Conditions for the evidence panel. Uses GPS only if already granted —
  // never prompts on load (a forced permission dialog is a bad first
  // impression); otherwise the backend resolves location from the user's
  // last trip, then a regional default. Fails quietly: the panel simply
  // doesn't render, so the screen stays calm even offline.
  function loadConditions(lat, lng) {
    getConditions(lat, lng).then(setConditions).catch(() => {});
  }

  useEffect(() => {
    if (navigator.geolocation && navigator.permissions?.query) {
      navigator.permissions.query({ name: 'geolocation' }).then(status => {
        if (status.state === 'granted') {
          navigator.geolocation.getCurrentPosition(
            pos => loadConditions(pos.coords.latitude, pos.coords.longitude),
            () => loadConditions(),
            { timeout: 5000 },
          );
        } else {
          loadConditions();
        }
      }).catch(() => loadConditions());
    } else {
      loadConditions();
    }
  }, []);

  // Fishing-grounded header line — references the user's real history, never
  // a time-of-day greeting. Falls back to a seasonal (still fishing) line for
  // users with no located trips yet.
  useEffect(() => {
    let cancelled = false;
    getSessions().then(data => {
      if (cancelled) return;
      const s = data.sessions?.[0];
      if (s && s.location && s.location !== 'Unknown location') {
        const sp = s.species_caught || [];
        if (sp.length) {
          const phrase = sp.length > 1 ? `${sp[0]} and more` : sp[0];
          setHeaderLine(`Last time out, you brought ${phrase} to hand at ${s.location}.`);
        } else {
          setHeaderLine(`Your last line was in the water at ${s.location}.`);
        }
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Explicit, user-initiated GPS read (the one place a permission prompt is
  // acceptable — a tap, not an on-load dialog).
  function useMyLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      pos => loadConditions(pos.coords.latitude, pos.coords.longitude),
      () => {},
    );
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: 'user', content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    setLoading(true);

    try {
      const conversationHistory = messages
        .filter((_, i) => i > 0) // skip the initial bot greeting
        .map(m => ({ role: m.role, content: m.content }));

      const data = await sendMessage(text, conversationHistory);
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
  const showLocationOptIn = conditions && conditions.location.source !== 'gps';

  return (
    <div style={{
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      height: '100dvh',
      background: 'radial-gradient(circle at 50% 0%, var(--fx-bg-grad-1), var(--fx-bg-grad-2) 45%, var(--fx-bg-grad-3) 100%)',
    }}>
      <GrainOverlay />
      <CompassWatermark variant={variant} />
      <DevVariantToggle value={variant} onChange={setVariant} />

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
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ fontFamily: 'var(--fx-font-serif)', fontSize: 17, fontWeight: 600, color: 'var(--fx-text-primary-2)', margin: 0 }}>
              FishBot
            </h1>
            <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 11.5, color: 'var(--fx-text-muted)', lineHeight: 1.35 }}>
              {headerLine}
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
                flexShrink: 0,
              }}
            >
              {displayName}
            </button>
          )}
        </div>
      </div>

      {/* Scroll area — evidence panel first, then the conversation. z-index:1
          keeps content above the compass atmosphere behind it. */}
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        style={{
          position: 'relative',
          zIndex: 1,
          flex: 1,
          overflowY: 'auto',
          padding: '14px 0 80px',
        }}
      >
        <ConditionsPanel data={conditions} variant={variant} />
        {showLocationOptIn && (
          <div style={{ margin: '-6px 16px 14px', textAlign: 'right' }}>
            <button type="button" onClick={useMyLocation} style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              fontFamily: 'var(--fx-font-ui)', fontSize: 11, color: 'var(--fx-moss-light)',
              textDecoration: 'underline', textUnderlineOffset: 2,
            }}>
              Use my current location
            </button>
          </div>
        )}

        <div style={{ padding: '0 16px' }}>
          {messages.map((msg, i) => (
            <Message key={i} role={msg.role} content={msg.content} />
          ))}
          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 8 }}>
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
