// The sim reuses the command post's offline basemap (Wayanad PMTiles extract +
// vendored fonts/sprites) rather than shipping a second copy in git. This runs
// before dev/build and copies them into public/ (which is gitignored).
//
// Basemap data © OpenStreetMap contributors (ODbL) via Protomaps; rendering
// stack is MapLibre GL + @protomaps/basemaps (both BSD-3).
import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = join(here, '..', '..', 'command-post', 'static')
const dst = join(here, '..', 'public')

if (!existsSync(join(src, 'wayanad.pmtiles'))) {
  console.error(`Missing ${join(src, 'wayanad.pmtiles')} — run from the sankat-mochan repo.`)
  process.exit(1)
}

mkdirSync(dst, { recursive: true })
cpSync(join(src, 'wayanad.pmtiles'), join(dst, 'wayanad.pmtiles'))
cpSync(join(src, 'basemaps-assets'), join(dst, 'basemaps-assets'), { recursive: true })
console.log('map assets copied to sim/public/')
