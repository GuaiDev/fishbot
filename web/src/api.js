const BASE_URL = 'https://web-production-e2094.up.railway.app';

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

export async function logTrip(text, photoLat, photoLng, photoTakenAt) {
  const body = { text };
  if (photoLat) { body.photo_lat = photoLat; body.photo_lng = photoLng; }
  if (photoTakenAt) body.photo_taken_at = photoTakenAt;

  const res = await fetch(`${BASE_URL}/log-trip`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`Log trip failed: ${res.status}`);
  return res.json();
}

export async function getSessions() {
  const res = await fetch(`${BASE_URL}/sessions`, { headers: authHeaders() });
  if (res.status === 401) throw Object.assign(new Error('Not authenticated'), { status: 401 });
  if (!res.ok) throw new Error(`Sessions failed: ${res.status}`);
  return res.json();
}
