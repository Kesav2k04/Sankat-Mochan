/**
 * The opening story, told ON the map: each beat aims a pitched, drifting
 * camera, sets the weather, and reveals what the disaster does to the ground
 * below. The last beat hands the victim their phone — pressing SOS is what
 * starts the sim.
 *
 * cam: { center, zoom, pitch, bearing } — the shot this beat drifts toward.
 * scene: 'hero' shows the big illustrated panel; undefined keeps the map as
 *        the star with only the lower-third caption.
 * fx.shake — ONE decaying impact, not a constant jitter.
 */
export const BEATS = [
  {
    key: 'rain',
    hour: '02:00',
    place: 'WAYANAD · KERALA',
    title: 'The rain will not stop',
    text: 'Forty-eight hours of monsoon rain has soaked the hills above the villages. The soil is holding on by habit alone.',
    dur: 7.5,
    scene: 'hero',
    cam: { center: [76.132, 11.685], zoom: 10.8, pitch: 30, bearing: -10 },
    fx: { rain: 'heavy', tint: 0.3 },
  },
  {
    key: 'slide',
    hour: '03:10',
    place: 'ABOVE ACHILAKKADU',
    title: 'The hillside gives way',
    text: 'A landslide tears through the valley. Roads vanish. Houses are buried where they stood.',
    dur: 8.5,
    scene: 'hero',
    cam: { center: [76.0605, 11.6995], zoom: 12.3, pitch: 55, bearing: -28 },
    fx: { rain: 'heavy', tint: 0.36, shake: true },
    zone: true,
    scar: true,
  },
  {
    key: 'dark',
    hour: '03:25',
    place: 'THE VALLEY FLOOR',
    title: 'The power goes out',
    text: 'Transmission lines snap under the mud. Every village for ten kilometres goes dark, one window at a time.',
    dur: 8,
    scene: 'hero',
    cam: { center: [76.11, 11.687], zoom: 11.6, pitch: 45, bearing: 12 },
    fx: { rain: 'light', tint: 0.44 },
    zone: true,
    scar: true,
  },
  {
    key: 'tower',
    hour: '03:40',
    place: 'GRID SECTOR 4',
    title: 'Towers down. No signal.',
    text: 'The cell tower is damaged and its backup battery drains. No calls, no internet — no way to ask for help.',
    dur: 7.5,
    scene: 'hero',
    cam: { center: [76.155, 11.679], zoom: 12.6, pitch: 55, bearing: -30 },
    fx: { rain: 'light', tint: 0.4 },
    zone: true,
    scar: true,
    tower: true,
  },
  {
    key: 'mesh',
    hour: '03:41',
    place: 'ACROSS THE ZONE',
    title: 'The mesh wakes up',
    text: 'Solar-charged LoRa modules switch to battery and find each other in the dark. They need no tower, no grid, no permission.',
    dur: 9,
    scene: 'side',
    cam: { center: [76.13, 11.678], zoom: 11.2, pitch: 35, bearing: 8 },
    fx: { rain: false, tint: 0.18 },
    zone: true,
    scar: true,
    tower: true,
    mesh: true,
  },
  {
    key: 'phone',
    hour: '04:05',
    place: 'THE DANGER SPOT',
    title: 'Trapped — but not silent',
    text: 'Someone stuck near the slide opens Sankat-Mochan. No bars on the phone, but the mesh is listening. Press SOS.',
    dur: null, // waits for the tap
    cam: { center: [76.075, 11.6995], zoom: 12.4, pitch: 48, bearing: -18 },
    fx: { rain: false, tint: 0.22 },
    zone: true,
    scar: true,
    tower: true,
    phone: true,
  },
]
