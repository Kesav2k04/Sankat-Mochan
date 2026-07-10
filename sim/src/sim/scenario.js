/**
 * The scripted disaster. Deterministic — a demo must rehearse cold and replay
 * identically, so every "random" number here comes from a seeded PRNG and never
 * from Math.random().
 *
 * Triage output is pre-computed (the `ai` field) rather than inferred live. This
 * is the hybrid call from docs/SIMULATION-DEMO.md: cached triage for cinematic
 * playback, because running an LLM on eight SOS in one sim-second means latency
 * spikes and output variance on stage. The pipeline shape is real; the answers
 * are cached.
 */

/** mulberry32 — public domain, by Tommy Ettinger. Small, fast, seedable. */
function mulberry32(seed) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** SURGE compresses a 24-hour disaster into 480 sim-seconds of scenario time. */
export const SURGE_SPAN_S = 480
export const SURGE_DAY_SCALE = 86400 / SURGE_SPAN_S // 180 wall-seconds per sim-second
export const DAY_START_H = 4 // the landslide hits before dawn

/**
 * The hero SOS. Tamil, life-threatening, carries a voice clip.
 *
 * Sized deliberately: 237 of the 244 available bytes, nothing trimmed. Tamil
 * costs ~3 UTF-8 bytes per character, so a sentence this ordinary already fills
 * 97% of a BLE write. That is the whole point of the byte budget in the
 * inspector — it is real, and it is tightest in exactly the languages this app
 * exists to carry. One more clause and the gist starts getting cut.
 */
export const TRACE_SOS = {
  id: 'c363-0',
  origin: 'c363',
  type: 'SOS',
  lang: 'ta',
  gist: 'மாடியில் சிக்கினேன், தண்ணீர் ஏறுகிறது',
  urgency: 5,
  category: 'trapped',
  locationHint: 'Block C',
  lat: 11.7082,
  lng: 76.0995,
  hops: 0,
  ts: 1752100000,
  voice: { seq: 0, chunks: 12, codec: 1, bytes: 200, loseIndex: 7 },
  ai: {
    urgency: 5,
    category: 'trapped',
    english: 'I am trapped upstairs, the water is rising',
    rationale: 'rising water, victim cannot self-evacuate',
    latencyMs: 1420,
  },
}

/** Hotspots — victims cluster around these, so geo-clustering has something to do. */
const HOTSPOTS = [
  { name: 'landslide scar', lat: 11.7085, lng: 76.099 },
  { name: 'govt school', lat: 11.704, lng: 76.108 },
  { name: 'river bridge', lat: 11.6995, lng: 76.121 },
  { name: 'Kunhome hamlet', lat: 11.712, lng: 76.1035 },
]

const MESSAGES = [
  { lang: 'ta', gist: 'நான் மாடியில் சிக்கிக்கொண்டேன், தண்ணீர் ஏறுகிறது', english: 'I am trapped upstairs, the water is rising', category: 'trapped', urgency: 5 },
  { lang: 'ta', gist: 'என் அப்பாவுக்கு மூச்சு விட முடியவில்லை', english: 'My father cannot breathe', category: 'medical', urgency: 5 },
  { lang: 'ta', gist: 'சாலை அடைபட்டுள்ளது, நாங்கள் ஆறு பேர் இருக்கிறோம்', english: 'The road is blocked, there are six of us', category: 'trapped', urgency: 3 },
  { lang: 'hi', gist: 'मेरा बेटा लापता है, वह नौ साल का है', english: 'My son is missing, he is nine years old', category: 'missing', urgency: 4 },
  { lang: 'hi', gist: 'घर में पानी भर गया है, छत पर हैं', english: 'The house is flooded, we are on the roof', category: 'flood', urgency: 4 },
  { lang: 'hi', gist: 'दीवार गिर गई, मेरा पैर दब गया है', english: 'A wall collapsed, my leg is pinned', category: 'trapped', urgency: 5 },
  { lang: 'ml', gist: 'ഞങ്ങൾ സ്കൂളിൽ കുടുങ്ങി, കുട്ടികളുണ്ട്', english: 'We are stuck in the school, there are children', category: 'trapped', urgency: 4 },
  { lang: 'ml', gist: 'അമ്മയ്ക്ക് രക്തസ്രാവം നിൽക്കുന്നില്ല', english: 'Mother is bleeding and it will not stop', category: 'medical', urgency: 5 },
  { lang: 'ml', gist: 'വൈദ്യുതി ഇല്ല, ഭക്ഷണം തീർന്നു', english: 'No electricity, we have run out of food', category: 'other', urgency: 2 },
  { lang: 'kn', gist: 'ಸೇತುವೆ ಕುಸಿದಿದೆ, ಜನರು ನೀರಿನಲ್ಲಿದ್ದಾರೆ', english: 'The bridge collapsed, people are in the water', category: 'flood', urgency: 5 },
  { lang: 'kn', gist: 'ಅಂಗಡಿಯಲ್ಲಿ ಬೆಂಕಿ ಹತ್ತಿದೆ', english: 'There is a fire in the shop', category: 'fire', urgency: 4 },
  { lang: 'en', gist: 'Landslide took the back of our house, two hurt', english: 'Landslide took the back of our house, two hurt', category: 'trapped', urgency: 4 },
  { lang: 'en', gist: 'Elderly neighbour not answering, door jammed', english: 'Elderly neighbour not answering, door jammed', category: 'missing', urgency: 3 },
  { lang: 'ta', gist: 'thanni veettukkul varuthu, help pannunga', english: 'Water is entering the house, please help', category: 'flood', urgency: 4 },
  { lang: 'hi', gist: 'bijli ka khamba gir gaya hai, aag lag rahi hai', english: 'An electricity pole has fallen, it is catching fire', category: 'fire', urgency: 4 },
  { lang: 'ml', gist: 'ഞങ്ങൾക്ക് കുടിവെള്ളം വേണം', english: 'We need drinking water', category: 'other', urgency: 1 },
  { lang: 'en', gist: 'Three families sheltering in temple, all safe for now', english: 'Three families sheltering in temple, all safe for now', category: 'other', urgency: 1 },
  { lang: 'ta', gist: 'குழந்தைக்கு காய்ச்சல், மருந்து இல்லை', english: 'The child has a fever, we have no medicine', category: 'medical', urgency: 3 },
  { lang: 'hi', gist: 'हम फंसे हैं, मोबाइल की बैटरी खत्म हो रही है', english: 'We are trapped, the phone battery is dying', category: 'trapped', urgency: 4 },
  { lang: 'kn', gist: 'ಎರಡು ಮನೆಗಳು ಮಣ್ಣಿನಡಿ ಸಿಕ್ಕಿವೆ', english: 'Two houses are buried under mud', category: 'trapped', urgency: 5 },
]

/**
 * Arrival times shaped as a disaster arc: a few calls, a surge at the peak,
 * responders stretched, then a taper. 40 SOS over the sim-day.
 */
function arrivalTimes(rng, n) {
  const out = []
  const bands = [
    { from: 0, to: 130, n: 7 }, // first light, scattered
    { from: 130, to: 300, n: 21 }, // the surge
    { from: 300, to: SURGE_SPAN_S, n: n - 28 }, // taper
  ]
  for (const b of bands) {
    for (let i = 0; i < b.n; i++) {
      const base = b.from + ((b.to - b.from) * (i + 0.5)) / b.n
      out.push(base + (rng() - 0.5) * ((b.to - b.from) / b.n) * 0.9)
    }
  }
  return out.sort((a, b) => a - b)
}

export function buildSurge(seed = 20260711) {
  const rng = mulberry32(seed)
  const times = arrivalTimes(rng, 40)
  const noFix = new Set([4, 11, 19, 27]) // GPS is optional; some SOS arrive with no fix

  return times.map((t, i) => {
    const m = MESSAGES[Math.floor(rng() * MESSAGES.length)]
    const hs = HOTSPOTS[Math.floor(rng() * HOTSPOTS.length)]
    const spread = 0.0016 // ~180 m — tight enough that clusters form
    const hasFix = !noFix.has(i)

    // The peak of the arc leans more critical, the taper less.
    const peak = t > 130 && t < 300
    let urgency = m.urgency
    if (peak && rng() < 0.35) urgency = Math.min(5, urgency + 1)
    if (!peak && t > 300 && rng() < 0.4) urgency = Math.max(1, urgency - 1)

    const origin = `${(0x1000 + Math.floor(rng() * 0xefff)).toString(16)}`
    return {
      t,
      id: `${origin}-0`,
      origin,
      type: 'SOS',
      lang: m.lang,
      gist: m.gist,
      urgency,
      category: m.category,
      locationHint: hasFix ? hs.name : ['near the old mill', 'behind the church', 'ward 4', 'no landmark'][i % 4],
      lat: hasFix ? hs.lat + (rng() - 0.5) * spread : null,
      lng: hasFix ? hs.lng + (rng() - 0.5) * spread : null,
      hops: 0,
      ts: 1752100000 + Math.floor(t * SURGE_DAY_SCALE),
      voice: null,
      ai: {
        urgency,
        category: m.category,
        english: m.english,
        rationale: RATIONALE[m.category] ?? 'triaged from message content',
        latencyMs: 900 + Math.floor(rng() * 900),
      },
    }
  })
}

const RATIONALE = {
  trapped: 'victim cannot self-evacuate',
  medical: 'time-critical clinical need',
  flood: 'rising water, escape route closing',
  fire: 'fire spread risk to occupants',
  missing: 'unaccounted person, search needed',
  other: 'welfare need, no immediate threat',
}

/** Render sim-scenario seconds as a clock face in the compressed disaster day. */
export function surgeClock(t) {
  const secs = DAY_START_H * 3600 + t * SURGE_DAY_SCALE
  const h = Math.floor(secs / 3600) % 24
  const m = Math.floor((secs % 3600) / 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
