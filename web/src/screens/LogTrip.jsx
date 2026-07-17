import { useState, useRef } from 'react';
import { confirmCatchSpecies, logTrip } from '../api';
import GrainOverlay from '../components/GrainOverlay';
import '../fishdex-tokens.css';

// A logged catch's species is a suggestion — from the text parser, and from
// a photo-vision ID if a photo was attached — never committed as fact until
// confirmed here. See the FishDex hallucination fix (species_confirmed gate
// in trip_logger.py / catches.py).
function SpeciesConfirmCard({ pending, onConfirmed }) {
  const [custom, setCustom] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const allCandidates = pending.suggested_species || [];
  // Ranked, confidence-bearing candidates (photo IDs and any specific
  // text-named species) vs. the one honest "notes didn't say" entry, which
  // is never a competing guess and is never ranked by confidence — see
  // _build_suggested_species in trip_logger.py.
  const ranked = allCandidates.filter(c => c.confidence);
  const unspecified = allCandidates.find(c => !c.confidence);

  async function handleConfirm(species) {
    const final = (species || custom).trim();
    if (!final || saving) return;
    setSaving(true);
    setError('');
    try {
      await confirmCatchSpecies(pending.catch_id, final);
      onConfirmed(pending.catch_id);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <div style={{
      marginTop: 12, padding: '14px 16px',
      background: 'var(--fx-card-fill)', border: '1px solid var(--fx-hairline)',
      borderRadius: 14,
    }}>
      <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 15, color: 'var(--fx-text-primary-2)', marginBottom: 4 }}>
        Confirm species
      </div>
      <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)', marginBottom: 10 }}>
        {ranked.length > 1
          ? "The photo and your notes don't agree — which is it?"
          : ranked.length === 1 && unspecified
            ? 'Notes didn’t name a species — here’s what the photo suggests.'
            : 'Tap to confirm, or type the correct species below.'}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: unspecified ? 6 : 10 }}>
        {ranked.map((c, i) => (
          <button
            key={i}
            type="button"
            onClick={() => handleConfirm(c.species)}
            disabled={saving}
            style={{
              padding: '8px 14px', borderRadius: 'var(--radius-pill)',
              border: `1px solid ${i === 0 ? 'var(--fx-moss-light)' : 'var(--fx-hairline)'}`,
              background: i === 0 ? 'var(--fx-moss-light)' : 'transparent',
              color: i === 0 ? 'var(--fx-on-accent)' : 'var(--fx-text-primary)',
              fontFamily: 'var(--fx-font-ui)', fontSize: 13,
              cursor: saving ? 'default' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 6, textTransform: 'capitalize',
            }}
          >
            {c.species}
            <span style={{ fontSize: 10, color: i === 0 ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)' }}>
              {c.source === 'photo' ? `📷 ${c.confidence}` : c.confidence}
            </span>
          </button>
        ))}
      </div>
      {unspecified && (
        <button
          type="button"
          onClick={() => handleConfirm(unspecified.species)}
          disabled={saving}
          style={{
            display: 'block', border: 'none', background: 'none', padding: '2px 0 10px',
            color: 'var(--fx-text-muted)', fontFamily: 'var(--fx-font-serif)', fontStyle: 'italic', fontSize: 12,
            cursor: saving ? 'default' : 'pointer', textAlign: 'left',
          }}
        >
          Notes {unspecified.note} — log as "{unspecified.species}" instead
        </button>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={custom}
          onChange={e => setCustom(e.target.value)}
          placeholder="Or type the correct species"
          style={{
            flex: 1, padding: '10px 12px', borderRadius: 8,
            border: '1px solid var(--fx-hairline)', background: 'var(--fx-card-fill-quiet)',
            color: 'var(--fx-text-primary)', fontFamily: 'var(--fx-font-ui)', fontSize: 13, outline: 'none',
          }}
        />
        <button
          type="button"
          onClick={() => handleConfirm(custom)}
          disabled={saving || !custom.trim()}
          style={{
            padding: '10px 16px', borderRadius: 8, border: 'none',
            background: custom.trim() ? 'var(--fx-moss-light)' : 'var(--fx-hairline)',
            color: custom.trim() ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)',
            fontFamily: 'var(--fx-font-ui)', fontSize: 13, fontWeight: 600,
            cursor: custom.trim() ? 'pointer' : 'default',
          }}
        >
          Use this
        </button>
      </div>
      {error && (
        <div style={{ marginTop: 8, fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--color-rust)' }}>{error}</div>
      )}
    </div>
  );
}

async function extractExif(file) {
  return new Promise(resolve => {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const view = new DataView(e.target.result);
        if (view.getUint16(0) !== 0xFFD8) { resolve(null); return; }
        let offset = 2;
        while (offset < view.byteLength - 2) {
          const marker = view.getUint16(offset);
          if (marker === 0xFFE1) {
            const exifData = parseExifData(view, offset + 4);
            resolve(exifData); return;
          }
          if ((marker & 0xFF00) !== 0xFF00) break;
          offset += 2 + view.getUint16(offset + 2);
        }
        resolve(null);
      } catch { resolve(null); }
    };
    reader.readAsArrayBuffer(file);
  });
}

function parseExifData(view, start) {
  try {
    const header = String.fromCharCode(
      view.getUint8(start), view.getUint8(start+1),
      view.getUint8(start+2), view.getUint8(start+3)
    );
    if (header !== 'Exif') return null;
    const tiffStart = start + 6;
    const littleEndian = view.getUint16(tiffStart) === 0x4949;
    const getUint16 = o => view.getUint16(tiffStart + o, littleEndian);
    const getUint32 = o => view.getUint32(tiffStart + o, littleEndian);
    const ifdOffset = getUint32(4);
    const numEntries = getUint16(ifdOffset);
    let gpsIfdOffset = null, dateTimeStr = null;
    for (let i = 0; i < numEntries; i++) {
      const e = ifdOffset + 2 + i * 12;
      const tag = getUint16(e);
      if (tag === 0x8825) gpsIfdOffset = getUint32(e + 8);
      if (tag === 0x9003 || tag === 0x0132) {
        const count = getUint32(e + 4);
        const valOffset = getUint32(e + 8);
        let str = '';
        for (let j = 0; j < count - 1; j++)
          str += String.fromCharCode(view.getUint8(tiffStart + valOffset + j));
        dateTimeStr = str;
      }
    }
    let lat = null, lng = null;
    if (gpsIfdOffset !== null) {
      const gpsEntries = getUint16(gpsIfdOffset);
      let latRef = 'N', lngRef = 'E', latRaw = null, lngRaw = null;
      for (let i = 0; i < gpsEntries; i++) {
        const e = gpsIfdOffset + 2 + i * 12;
        const tag = getUint16(e);
        if (tag === 1) latRef = String.fromCharCode(view.getUint8(tiffStart + getUint32(e+8)));
        if (tag === 3) lngRef = String.fromCharCode(view.getUint8(tiffStart + getUint32(e+8)));
        if (tag === 2) latRaw = readGpsCoord(view, tiffStart, getUint32(e+8), littleEndian);
        if (tag === 4) lngRaw = readGpsCoord(view, tiffStart, getUint32(e+8), littleEndian);
      }
      if (latRaw !== null && lngRaw !== null) {
        lat = latRaw * (latRef === 'S' ? -1 : 1);
        lng = lngRaw * (lngRef === 'W' ? -1 : 1);
      }
    }
    let isoDate = null;
    if (dateTimeStr) {
      const parts = dateTimeStr.match(/(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
      if (parts) isoDate = `${parts[1]}-${parts[2]}-${parts[3]}T${parts[4]}:${parts[5]}:${parts[6]}`;
    }
    return { lat, lng, takenAt: isoDate };
  } catch { return null; }
}

function readGpsCoord(view, tiffStart, offset, le) {
  const d = view.getUint32(tiffStart+offset,le)/view.getUint32(tiffStart+offset+4,le);
  const m = view.getUint32(tiffStart+offset+8,le)/view.getUint32(tiffStart+offset+12,le);
  const s = view.getUint32(tiffStart+offset+16,le)/view.getUint32(tiffStart+offset+20,le);
  return d + m/60 + s/3600;
}

export default function LogTrip({ onNavigate }) {
  const [text, setText] = useState('');
  const [exifData, setExifData] = useState(null);
  const [preview, setPreview] = useState(null);
  const [photoFile, setPhotoFile] = useState(null);
  const [status, setStatus] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [pendingCatches, setPendingCatches] = useState([]);
  const fileRef = useRef(null);

  async function handlePhoto(e) {
    const file = e.target.files[0];
    if (!file) return;
    setPhotoFile(file);
    setPreview(URL.createObjectURL(file));
    const exif = await extractExif(file);
    if (exif && exif.lat) {
      setExifData(exif);
    } else {
      setExifData({ lat: null, lng: null, takenAt: null, trying: true });
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          pos => setExifData({
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            takenAt: new Date().toISOString(),
          }),
          () => setExifData(null),
          { timeout: 8000 }
        );
      } else {
        setExifData(null);
      }
    }
  }

  async function handleSubmit() {
    if (!text.trim()) return;
    setStatus('loading');
    try {
      const result = await logTrip(text, exifData?.lat, exifData?.lng, exifData?.takenAt, photoFile);
      setStatus('success');
      setPendingCatches(result.pending_catches || []);
      setText('');
      setPreview(null);
      setExifData(null);
      setPhotoFile(null);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
    }
  }

  function handleCatchConfirmed(catchId) {
    setPendingCatches(prev => prev.filter(p => p.catch_id !== catchId));
  }

  const hasGps = exifData && exifData.lat && !exifData.trying;
  const tryingGps = exifData?.trying;

  return (
    <div style={{
      position: 'relative',
      minHeight: '100dvh',
      background: 'radial-gradient(circle at 50% 0%, var(--fx-bg-grad-1), var(--fx-bg-grad-2) 45%, var(--fx-bg-grad-3) 100%)',
      padding: '16px 16px 100px',
      maxWidth: 480,
      margin: '0 auto',
    }}>
      <GrainOverlay />
      <h1 style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 22, color: 'var(--fx-text-primary-2)', marginBottom: 4 }}>
        Log a catch
      </h1>
      <p style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 12, color: 'var(--fx-text-muted)', marginBottom: 20 }}>
        Photo adds GPS + time automatically
      </p>

      {/* Photo zone. Once a photo is picked, this becomes a near-full-bleed
          photography-led card (DESIGN.md's Catch Photo Card): GPS status
          sits directly on the image via a bottom scrim, not as separate
          pills below it. Empty state stays a plain dashed dropzone — there's
          no photo yet for the photograph to carry. */}
      <label
        htmlFor="photo-input"
        className="photo-dropzone"
        style={{
          display: 'block',
          position: 'relative',
          border: preview ? 'none' : '1.5px dashed var(--fx-dashed-border)',
          borderRadius: 14,
          padding: preview ? 0 : '24px 16px',
          textAlign: 'center',
          cursor: 'pointer',
          marginBottom: 16,
          overflow: 'hidden',
          aspectRatio: preview ? '4 / 5' : 'auto',
          background: preview ? 'transparent' : 'var(--fx-card-fill-quiet)',
        }}
      >
        <input
          id="photo-input"
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={handlePhoto}
          className="sr-only"
        />
        {preview ? (
          <>
            <img src={preview} alt="Trip" loading="lazy" style={{
              width: '100%', height: '100%', objectFit: 'cover', display: 'block',
            }} />
            <div style={{
              position: 'absolute', left: 0, right: 0, bottom: 0,
              padding: '16px',
              background: 'linear-gradient(to top, rgba(9,10,6,.9), transparent)',
            }}>
              {hasGps && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--fx-moss-lightest)', fontFamily: 'var(--fx-font-ui)', fontSize: 13, fontWeight: 600 }}>
                  <span aria-hidden="true">📍</span> GPS captured · {exifData.takenAt ? new Date(exifData.takenAt).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}
                </div>
              )}
              {tryingGps && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--fx-text-primary-2)', fontFamily: 'var(--fx-font-ui)', fontSize: 13 }}>
                  <span aria-hidden="true">📍</span> Getting location...
                </div>
              )}
              {exifData === null && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-rust)', fontFamily: 'var(--fx-font-ui)', fontSize: 13, fontWeight: 600 }}>
                  <span aria-hidden="true">📍</span> No GPS — describe location in text
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div aria-hidden="true" style={{ fontSize: 28, marginBottom: 6, color: 'var(--fx-text-locked-3)' }}>📷</div>
            <div style={{ fontFamily: 'var(--fx-font-ui)', fontSize: 13, color: 'var(--fx-text-muted)' }}>
              Tap to add photo
            </div>
          </>
        )}
      </label>

      <label htmlFor="trip-notes" className="sr-only">
        What happened on this trip?
      </label>
      <textarea
        id="trip-notes"
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="What happened? Species, location, technique, conditions — as much or as little as you remember."
        style={{
          width: '100%',
          background: 'var(--fx-card-fill)',
          border: '1px solid var(--fx-hairline)',
          borderRadius: 12,
          padding: '12px 14px',
          color: 'var(--fx-text-primary)',
          fontFamily: 'var(--fx-font-ui)',
          fontSize: 14,
          resize: 'none',
          outline: 'none',
          minHeight: 120,
          marginBottom: 16,
          lineHeight: 1.5,
        }}
      />

      <button
        onClick={handleSubmit}
        disabled={!text.trim() || status === 'loading'}
        style={{
          width: '100%',
          background: text.trim() && status !== 'loading' ? 'var(--fx-moss-light)' : 'var(--fx-hairline)',
          color: text.trim() && status !== 'loading' ? 'var(--fx-on-accent)' : 'var(--fx-text-muted)',
          border: 'none',
          borderRadius: 'var(--radius-pill)',
          padding: '14px',
          fontFamily: 'var(--fx-font-ui)',
          fontSize: 15,
          fontWeight: 600,
          cursor: text.trim() && status !== 'loading' ? 'pointer' : 'default',
          transition: 'background 0.15s',
        }}
      >
        {status === 'loading' ? 'Logging...' : 'Log trip'}
      </button>

      {status === 'success' && (
        <>
          {/* Quiet celebration, not a plain checkmark — same ❦ new-find
              vocabulary as FishDex's CaughtPlate, dressed for a confirmation
              moment rather than a collection plate. */}
          <div style={{
            marginTop: 12, padding: '16px 18px',
            background: 'var(--fx-card-fill-quiet)', border: '1px solid var(--fx-hairline)',
            borderRadius: 14,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <span style={{ color: 'var(--fx-moss-lightest)', fontSize: 14 }} aria-hidden="true">❦</span>
              <span style={{
                fontFamily: 'var(--fx-font-ui)', fontSize: 10, fontWeight: 600,
                letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--fx-moss-lightest)',
              }}>
                Logged
              </span>
            </div>
            <div style={{ fontFamily: 'var(--fx-font-serif)', fontWeight: 600, fontSize: 17, color: 'var(--fx-text-primary-2)' }}>
              Trip logged. Keep fishing.
            </div>
          </div>
          {pendingCatches.map(p => (
            <SpeciesConfirmCard key={p.catch_id} pending={p} onConfirmed={handleCatchConfirmed} />
          ))}
        </>
      )}
      {status === 'error' && (
        <div role="alert" style={{
          marginTop: 12, padding: '12px 14px',
          background: 'var(--color-rust-bg)', color: 'var(--color-rust)',
          borderRadius: 10, fontFamily: 'var(--fx-font-ui)', fontSize: 14,
        }}>
          Error: {errorMsg}
        </div>
      )}
    </div>
  );
}
