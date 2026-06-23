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
      background: '#0F1117',
      padding: '16px 16px 100px',
      maxWidth: 480,
      margin: '0 auto',
    }}>
      <h1 style={{ fontSize: 18, fontWeight: 600, color: '#E8EAF0', marginBottom: 4 }}>
        Log a catch
      </h1>
      <p style={{ fontSize: 12, color: '#6B7280', marginBottom: 20 }}>
        Photo adds GPS + time automatically
      </p>

      {/* Photo zone */}
      <div
        onClick={() => fileRef.current?.click()}
        style={{
          border: `1.5px dashed ${preview ? '#1D9E75' : '#2A2D3A'}`,
          borderRadius: 12,
          padding: preview ? 0 : '24px 16px',
          textAlign: 'center',
          cursor: 'pointer',
          marginBottom: 12,
          overflow: 'hidden',
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={handlePhoto}
          style={{ display: 'none' }}
        />
        {preview ? (
          <img src={preview} alt="Trip" style={{
            width: '100%', maxHeight: 200, objectFit: 'cover', display: 'block',
          }} />
        ) : (
          <>
            <div style={{ fontSize: 28, marginBottom: 6 }}>📷</div>
            <div style={{ fontSize: 13, color: '#6B7280' }}>
              Tap to add photo
            </div>
          </>
        )}
      </div>

      {hasGps && (
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: '#0F4D38', color: '#1D9E75',
          borderRadius: 20, padding: '4px 12px',
          fontSize: 12, fontWeight: 500, marginBottom: 16,
        }}>
          📍 GPS captured · {exifData.takenAt ? new Date(exifData.takenAt).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : ''}
        </div>
      )}
      {tryingGps && (
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: '#1A1D27', color: '#6B7280',
          borderRadius: 20, padding: '4px 12px',
          fontSize: 12, marginBottom: 16,
        }}>
          📍 Getting location...
        </div>
      )}
      {exifData === null && preview && (
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: '#2A1F12', color: '#E07B39',
          borderRadius: 20, padding: '4px 12px',
          fontSize: 12, marginBottom: 16,
        }}>
          📍 No GPS — describe location in text
        </div>
      )}

      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="What happened? Species, location, technique, conditions — as much or as little as you remember."
        style={{
          width: '100%',
          background: '#1A1D27',
          border: '1px solid #2A2D3A',
          borderRadius: 10,
          padding: '12px 14px',
          color: '#E8EAF0',
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
          background: text.trim() && status !== 'loading' ? '#1D9E75' : '#2A2D3A',
          color: 'white',
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
          background: '#0F4D38', color: '#1D9E75',
          borderRadius: 10, fontSize: 14,
        }}>
          ✓ Trip logged. Keep fishing.
        </div>
      )}
      {status === 'error' && (
        <div style={{
          marginTop: 12, padding: '12px 14px',
          background: '#2A1212', color: '#E07B39',
          borderRadius: 10, fontSize: 14,
        }}>
          Error: {errorMsg}
        </div>
      )}
    </div>
  );
}
