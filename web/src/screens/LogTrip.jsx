import { useState, useRef } from 'react';
import { logTrip } from '../api';

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
  const [status, setStatus] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const fileRef = useRef(null);

  async function handlePhoto(e) {
    const file = e.target.files[0];
    if (!file) return;
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
      await logTrip(text, exifData?.lat, exifData?.lng, exifData?.takenAt);
      setStatus('success');
      setText('');
      setPreview(null);
      setExifData(null);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
    }
  }

  const hasGps = exifData && exifData.lat && !exifData.trying;
  const tryingGps = exifData?.trying;

  return (
    <div style={{
      minHeight: '100dvh',
      background: 'var(--color-base-bark)',
      padding: '16px 16px 100px',
      maxWidth: 480,
      margin: '0 auto',
    }}>
      <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--color-text-bone)', marginBottom: 4 }}>
        Log a catch
      </h1>
      <p style={{ fontSize: 12, color: 'var(--color-text-ash)', marginBottom: 20 }}>
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
          border: preview ? 'none' : '1.5px dashed var(--color-border-twig)',
          borderRadius: 12,
          padding: preview ? 0 : '24px 16px',
          textAlign: 'center',
          cursor: 'pointer',
          marginBottom: 16,
          overflow: 'hidden',
          aspectRatio: preview ? '4 / 5' : 'auto',
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
            <img src={preview} alt="Trip" style={{
              width: '100%', height: '100%', objectFit: 'cover', display: 'block',
            }} />
            <div style={{
              position: 'absolute', left: 0, right: 0, bottom: 0,
              padding: '16px',
              background: 'linear-gradient(to top, color-mix(in srgb, var(--color-base-bark) 95%, transparent), transparent)',
            }}>
              {hasGps && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-moss)', fontSize: 13, fontWeight: 600 }}>
                  <span aria-hidden="true">📍</span> GPS captured · {exifData.takenAt ? new Date(exifData.takenAt).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}
                </div>
              )}
              {tryingGps && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-text-bone)', fontSize: 13 }}>
                  <span aria-hidden="true">📍</span> Getting location...
                </div>
              )}
              {exifData === null && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-rust)', fontSize: 13, fontWeight: 600 }}>
                  <span aria-hidden="true">📍</span> No GPS — describe location in text
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div aria-hidden="true" style={{ fontSize: 28, marginBottom: 6 }}>📷</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-ash)' }}>
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
          background: 'var(--color-surface-loam)',
          border: '1px solid var(--color-border-twig)',
          borderRadius: 10,
          padding: '12px 14px',
          color: 'var(--color-text-bone)',
          fontSize: 14,
          fontFamily: 'inherit',
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
          background: text.trim() && status !== 'loading' ? 'var(--color-moss-fill)' : 'var(--color-border-twig)',
          color: 'var(--color-text-bone)',
          border: 'none',
          borderRadius: 10,
          padding: '14px',
          fontSize: 15,
          fontWeight: 600,
          cursor: text.trim() && status !== 'loading' ? 'pointer' : 'default',
          transition: 'background 0.15s',
        }}
      >
        {status === 'loading' ? 'Logging...' : 'Log trip'}
      </button>

      {status === 'success' && (
        <div style={{
          marginTop: 12, padding: '12px 14px',
          background: 'var(--color-sage-tint-bg)', color: 'var(--color-moss)',
          borderRadius: 10, fontSize: 14,
        }}>
          <span aria-hidden="true">✓</span> Trip logged. Keep fishing.
        </div>
      )}
      {status === 'error' && (
        <div style={{
          marginTop: 12, padding: '12px 14px',
          background: 'var(--color-rust-bg)', color: 'var(--color-rust)',
          borderRadius: 10, fontSize: 14,
        }}>
          Error: {errorMsg}
        </div>
      )}
    </div>
  );
}
