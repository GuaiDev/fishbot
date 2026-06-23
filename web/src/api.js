const BASE_URL = 'https://web-production-e2094.up.railway.app';
const API_KEY = 'fdf0f9f1381176065637fe72a69cd651bb6ac117cbcabcf60d26988127a574a9';

const headers = {
  'Content-Type': 'application/json',
  'X-Api-Key': API_KEY,
};

// The backend /chat endpoint takes { message, conversation_history } —
// extract the last user message and pass the rest as history.
export async function sendMessage(messages) {
  const lastMsg = messages[messages.length - 1];
  const history = messages.slice(0, -1);
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message: lastMsg.content,
      conversation_history: history,
    }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json();
}

export async function logTrip(text, photoLat, photoLng, photoTakenAt) {
  const body = { text };
  if (photoLat) { body.photo_lat = photoLat; body.photo_lng = photoLng; }
  if (photoTakenAt) body.photo_taken_at = photoTakenAt;

  const res = await fetch(`${BASE_URL}/log-trip`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Log trip failed: ${res.status}`);
  return res.json();
}

export async function getSessions() {
  const res = await fetch(`${BASE_URL}/sessions`, { headers });
  if (!res.ok) throw new Error(`Sessions failed: ${res.status}`);
  return res.json();
}
