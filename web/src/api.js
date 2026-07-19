const BASE_URL = 'https://web-production-e2094.up.railway.app';

// catches[].photo_url from GET /sessions is a relative path (e.g. /photos/x.jpg).
// In production that resolves fine since the backend serves the app itself,
// but resolve it explicitly so it also works wherever frontend and backend
// are on different origins (e.g. local dev).
export function resolvePhotoUrl(path) {
  if (!path) return null;
  return path.startsWith('http') ? path : `${BASE_URL}${path}`;
}

function getToken() {
  return localStorage.getItem('fishbot_token');
}

function authHeaders() {
  const token = getToken();
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

export async function signup(code, username, displayName) {
  const res = await fetch(`${BASE_URL}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, username, display_name: displayName }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Signup failed: ${res.status}`);
  return data;
}

export async function getMe() {
  const res = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`Auth check failed: ${res.status}`);
  return res.json();
}

export async function sendMessage(messages) {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ messages }),
  });
  if (res.status === 429) {
    const data = await res.json();
    throw Object.assign(new Error(data.detail || 'Rate limit reached'), { status: 429 });
  }
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json();
}

// TODO(backend): /log-trip and /log-trip/photo only accept one freeform
// `text` string + at most one photo file — there is no structured per-catch
// input path (see src/services/trip_logger.py:log_session, which never
// passes count/biggest_size/bait to insert_catch even though the `catches`
// table has those columns). Until the backend accepts a real catches array
// (JSON body field or additional multipart fields, plus a way to attach more
// than one photo), `catches` here is carried as an inert `catches_json`
// field so the wire format is ready the moment the backend reads it — the
// actual species/pending-catch flow still runs off the synthesized `text`,
// same as before this param existed. Callers that don't pass `catches` are
// unaffected.
export async function logTrip(text, photoLat, photoLng, photoTakenAt, photoFile, catches) {
  let res;
  if (photoFile) {
    const form = new FormData();
    form.append('text', text);
    form.append('photo', photoFile);
    if (photoLat) { form.append('photo_lat', photoLat); form.append('photo_lng', photoLng); }
    if (photoTakenAt) form.append('photo_taken_at', photoTakenAt);
    if (catches) form.append('catches_json', JSON.stringify(catches));

    const token = getToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    res = await fetch(`${BASE_URL}/log-trip/photo`, { method: 'POST', headers, body: form });
  } else {
    const body = { text };
    if (photoLat) { body.photo_lat = photoLat; body.photo_lng = photoLng; }
    if (photoTakenAt) body.photo_taken_at = photoTakenAt;
    if (catches) body.catches_json = JSON.stringify(catches);

    res = await fetch(`${BASE_URL}/log-trip`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
  }
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`Log trip failed: ${res.status}`);
  return res.json();
}

export async function confirmCatchSpecies(catchId, species) {
  const res = await fetch(`${BASE_URL}/catches/${catchId}/confirm-species`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ species }),
  });
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`Confirm species failed: ${res.status}`);
  return res.json();
}

export async function getFishDex() {
  const res = await fetch(`${BASE_URL}/fishdex`, { headers: authHeaders() });
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`FishDex fetch failed: ${res.status}`);
  return res.json();
}

export async function getSessions() {
  const res = await fetch(`${BASE_URL}/sessions`, { headers: authHeaders() });
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`Sessions failed: ${res.status}`);
  return res.json();
}

export async function getMapSegments(bounds, mode = 'balanced') {
  const { north, south, east, west } = bounds;
  const params = new URLSearchParams({ north, south, east, west, mode });
  const res = await fetch(`${BASE_URL}/map/segments?${params}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to fetch segments');
  return res.json();
}

export async function getMyStops() {
  const res = await fetch(`${BASE_URL}/map/my-stops`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Failed to fetch stops');
  return res.json();
}
