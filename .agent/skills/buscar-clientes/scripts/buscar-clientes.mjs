#!/usr/bin/env node
// buscar-clientes: saca todos los negocios de un sector en una ciudad desde Google Maps (a través
// de treg), entra en la web de cada uno a por el correo y lo deja todo en un CSV.
// Sin dependencias: Node 18 o superior. Lo ejecuta Claude siguiendo el SKILL.md.
//
//   node buscar-clientes.mjs comprobar
//   node buscar-clientes.mjs estimar --negocio "clínica dental" --ciudad "Valencia" --carpeta <dir>
//        [--pais es] [--candidato 2] [--paso 1.7]
//   node buscar-clientes.mjs buscar   --carpeta <dir> [--tope 0.10]
//   node buscar-clientes.mjs tipos    --carpeta <dir>
//   node buscar-clientes.mjs filtrar  --carpeta <dir> [--tipos "regex"] [--todos] [--con-alrededores]
//   node buscar-clientes.mjs correos  --carpeta <dir>
//   node buscar-clientes.mjs csv      --carpeta <dir>
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import crypto from 'node:crypto'

const TREG = 'https://treg.to'
const MAPS = 'litescrape.google.serp.maps'
const PRECIO_BUSQUEDA = 0.00015 // USD por búsqueda con resultado (las fallidas no se cobran)
const PAGINAS = 3 // 20 negocios por página
const PARALELO = 16
// Solo se pasa de página si la zona es densa: si la mayoría de los 20 resultados están cerca de su
// centro. En zonas con pocos negocios Maps rellena con los de los pueblos de al lado.
const CERCA_MIN = 6
const INTENTOS = 6
const UA_WEB = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
const UA_MAPA = 'buscar-clientes/1.0 (https://guias.profimaxia.com/leads/)'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const usd = (x) => `${x.toFixed(4).replace('.', ',')} $`
const sinTildes = (t) => String(t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function args() {
  const [orden, ...resto] = process.argv.slice(2)
  const o = { orden }
  for (let i = 0; i < resto.length; i++) {
    if (!resto[i].startsWith('--')) throw new Error(`Argumento no reconocido: ${resto[i]}`)
    const k = resto[i].slice(2)
    const v = resto[i + 1] && !resto[i + 1].startsWith('--') ? resto[++i] : true
    o[k] = v
  }
  return o
}

const leer = (f) => JSON.parse(fs.readFileSync(f, 'utf8'))
const escribir = (f, d) => fs.writeFileSync(f, JSON.stringify(d, null, 1))
function carpeta(o) {
  if (!o.carpeta || o.carpeta === true) throw new Error('Falta --carpeta <dir>')
  fs.mkdirSync(o.carpeta, { recursive: true })
  return o.carpeta
}

// ---------- treg ----------

// La llave sale de TREG_TOKEN o de la que deja `treg login` en ~/.treg/config.json.
function llave() {
  if (process.env.TREG_TOKEN) return { token: process.env.TREG_TOKEN.trim(), org: process.env.TREG_ORG, origen: 'TREG_TOKEN' }
  const ruta = process.env.TREG_CONFIG || path.join(os.homedir(), '.treg', 'config.json')
  if (!fs.existsSync(ruta)) return null
  try {
    const cfg = leer(ruta)
    return cfg.token ? { token: cfg.token, org: cfg.active_org, origen: ruta } : null
  } catch {
    return null
  }
}

function cabeceras(k, extra = {}) {
  const h = { 'X-Treg-Token': k.token, 'User-Agent': UA_MAPA, ...extra }
  if (k.org) h['X-Treg-Org'] = k.org
  return h
}

async function saldo(k) {
  const yo = await fetch(`${TREG}/auth/me`, { headers: cabeceras(k) })
  if (!yo.ok) return { error: `treg no acepta la llave (${yo.status})` }
  const me = await yo.json()
  if (!me.org_id) return { error: 'la cuenta de treg no tiene equipo todavía', email: me.email }
  const r = await fetch(`${TREG}/orgs/${me.org_id}/balance`, { headers: cabeceras(k) })
  const b = r.ok ? await r.json() : {}
  return { email: me.email, equipo: me.org, usd: typeof b.balance_usd === 'number' ? b.balance_usd : null }
}

async function comprobar() {
  const v = Number(process.versions.node.split('.')[0])
  console.log(v >= 18 ? `OK node ${process.versions.node}` : `FALTA node 18 o superior (tienes ${process.versions.node})`)
  const k = llave()
  if (!k) {
    console.log('FALTA treg: no hay llave (ni TREG_TOKEN ni ~/.treg/config.json)')
    return
  }
  const s = await saldo(k)
  if (s.error) console.log(`FALTA treg: ${s.error}`)
  else console.log(`OK treg: ${s.email}, equipo ${s.equipo}, saldo ${s.usd == null ? '?' : usd(s.usd)}`)
}

// ---------- la ciudad ----------

// Superficie aproximada (km²) de un anillo [lng, lat] con proyección local.
function areaAnillo(anillo) {
  const lat0 = (anillo.reduce((a, p) => a + p[1], 0) / anillo.length) * (Math.PI / 180)
  const kx = 111.32 * Math.cos(lat0), ky = 110.57
  let a = 0
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
    a += (anillo[j][0] * kx) * (anillo[i][1] * ky) - (anillo[i][0] * kx) * (anillo[j][1] * ky)
  }
  return Math.abs(a / 2)
}

function km([la1, lo1], [la2, lo2]) {
  const x = (lo2 - lo1) * 111.32 * Math.cos(((la1 + la2) / 2) * (Math.PI / 180))
  const y = (la2 - la1) * 110.57
  return Math.hypot(x, y)
}

function poligonos(geo) {
  return geo.type === 'Polygon' ? [geo.coordinates] : geo.type === 'MultiPolygon' ? geo.coordinates : []
}

function dentroAnillo(lng, lat, anillo) {
  let dentro = false
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
    const [xi, yi] = anillo[i], [xj, yj] = anillo[j]
    if ((yi > lat) !== (yj > lat) && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) dentro = !dentro
  }
  return dentro
}

// Dentro del contorno exterior y fuera de sus huecos.
function dentro(geo, lat, lng) {
  return poligonos(geo).some((p) => dentroAnillo(lng, lat, p[0]) && !p.slice(1).some((h) => dentroAnillo(lng, lat, h)))
}

const TIPOS_LUGAR = new Set(['city', 'town', 'village', 'municipality', 'city_district', 'borough', 'suburb', 'hamlet'])

async function lugares(ciudad, pais) {
  const q = new URLSearchParams({ q: ciudad, format: 'jsonv2', polygon_geojson: '1', addressdetails: '1', limit: '8', 'accept-language': 'es' })
  if (pais) q.set('countrycodes', String(pais).toLowerCase())
  const r = await fetch(`https://nominatim.openstreetmap.org/search?${q}`, { headers: { 'User-Agent': UA_MAPA } })
  if (!r.ok) throw new Error(`No se pudo buscar la ciudad en el mapa (${r.status})`)
  const todos = await r.json()
  return todos.filter((x) => ['Polygon', 'MultiPolygon'].includes(x.geojson?.type) && TIPOS_LUGAR.has(x.addresstype))
}

async function estimar(o) {
  const dir = carpeta(o)
  if (!o.negocio || !o.ciudad || o.negocio === true || o.ciudad === true) throw new Error('Faltan --negocio y --ciudad')
  const candidatos = await lugares(o.ciudad, o.pais)
  if (!candidatos.length) {
    console.log(`NO ENCONTRADA: no hay ningún municipio llamado «${o.ciudad}» en el mapa. Prueba con el nombre oficial o añade la provincia ("Elche, Alicante").`)
    return
  }
  candidatos.forEach((c, i) => console.log(`candidato ${i + 1}: ${c.display_name}`))
  const n = Number(o.candidato || 1)
  const lugar = candidatos[n - 1]
  if (!lugar) throw new Error(`No hay candidato ${n}`)
  const geo = lugar.geojson
  const km2 = poligonos(geo).reduce((a, p) => a + areaAnillo(p[0]), 0)

  const paso = Number(o.paso || 1.7)
  const [s, nn, w, e] = lugar.boundingbox.map(Number)
  const dLat = paso / 110.57
  const dLng = paso / (111.32 * Math.cos((((s + nn) / 2) * Math.PI) / 180))
  const puntos = []
  for (let lat = s + dLat / 2; lat < nn; lat += dLat) {
    for (let lng = w + dLng / 2; lng < e; lng += dLng) {
      // La zona entra si su centro o alguna esquina cae dentro: así no se pierden los bordes.
      const esquinas = [[0, 0], [0.5, 0.5], [0.5, -0.5], [-0.5, 0.5], [-0.5, -0.5]]
      if (esquinas.some(([a, b]) => dentro(geo, lat + a * dLat, lng + b * dLng))) puntos.push([+lat.toFixed(5), +lng.toFixed(5)])
    }
  }
  const maxBusquedas = puntos.length * PAGINAS
  const zona = {
    negocio: String(o.negocio).trim(),
    ciudad: String(o.ciudad).trim(),
    lugar: lugar.display_name,
    pais: lugar.address?.country_code || o.pais || 'es',
    km2: Math.round(km2),
    paso,
    puntos,
    maxBusquedas,
    maxUsd: +(maxBusquedas * PRECIO_BUSQUEDA).toFixed(4),
    geojson: geo,
  }
  escribir(path.join(dir, 'zona.json'), zona)
  const k = llave()
  const s2 = k ? await saldo(k) : { error: 'sin llave' }
  console.log(`LUGAR: ${zona.lugar}`)
  console.log(`SUPERFICIE: ${zona.km2} km², ${puntos.length} zonas de ${String(paso).replace('.', ',')} km`)
  console.log(`COMO MUCHO: ${maxBusquedas} búsquedas en Google Maps = ${usd(zona.maxUsd)} (suelen ser bastantes menos: solo se pasa de página donde hay más de 20)`)
  console.log(`SALDO treg: ${s2.error ? s2.error : s2.usd == null ? '?' : usd(s2.usd)}`)
  if (puntos.length > 1500) console.log('AVISO: es una zona muy grande. Mejor una ciudad concreta o un --paso mayor.')
}

// ---------- Google Maps ----------

async function llamar(k, zona, punto, pagina, clave) {
  const q = new URLSearchParams({
    q: zona.negocio, type: 'search', hl: 'es', gl: zona.pais,
    google_domain: zona.pais === 'es' ? 'google.es' : 'google.com',
    ll: `@${punto[0]},${punto[1]},15z`, start: String(pagina * 20),
  })
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 95000)
  try {
    const r = await fetch(`${TREG}/call/${MAPS}?${q}`, { headers: cabeceras(k, { 'Idempotency-Key': clave }), signal: ctrl.signal })
    const coste = Number(r.headers.get('x-treg-cost-micro') || 0) / 1e6
    const cuerpo = await r.json().catch(() => ({}))
    const espera = Number(r.headers.get('retry-after') || cuerpo?.detail?.retry_after_s || 0)
    return { estado: r.status, coste, cuerpo, espera }
  } catch {
    return { estado: 0, coste: 0, cuerpo: {}, espera: 0 }
  } finally {
    clearTimeout(t)
  }
}

async function buscar(o) {
  const dir = carpeta(o)
  const zona = leer(path.join(dir, 'zona.json'))
  const k = llave()
  if (!k) throw new Error('No hay llave de treg: ejecuta antes la instalación de treg')
  const tope = Number(o.tope || zona.maxUsd)
  const cola = zona.puntos.map((p) => ({ p, pagina: 0, intentos: 0, clave: crypto.randomUUID() }))
  const negocios = new Map()
  const t0 = Date.now()
  let llamadas = 0, cobradas = 0, gasto = 0, reintentos = 0, perdidas = 0, activas = 0, parar = null

  const guardar = () => escribir(path.join(dir, 'negocios.json'), [...negocios.values()])
  const avance = setInterval(() => {
    console.log(JSON.stringify({ seg: Math.round((Date.now() - t0) / 1000), busquedas: cobradas, negocios: negocios.size, gasto: +gasto.toFixed(5), quedan: cola.length }))
    guardar()
  }, 10000)

  async function obrero() {
    for (;;) {
      if (parar) return
      const tarea = cola.shift()
      if (!tarea) {
        if (activas === 0) return
        await sleep(400)
        continue
      }
      if (gasto + PRECIO_BUSQUEDA > tope + 1e-9) { perdidas++; continue }
      activas++
      const r = await llamar(k, zona, tarea.p, tarea.pagina, tarea.clave)
      activas--
      llamadas++
      gasto += r.coste
      if (r.estado === 402) { parar = 'saldo'; return }
      if (r.estado === 401 || r.estado === 403) { parar = `treg rechaza la llave (${r.estado})`; return }
      if (r.estado === 400 || r.estado === 422) { parar = `treg rechaza la búsqueda (${r.estado}): ${JSON.stringify(r.cuerpo).slice(0, 200)}`; return }
      if (r.estado !== 200) {
        tarea.intentos++
        if (tarea.intentos < INTENTOS) {
          reintentos++
          await sleep(Math.max(r.espera * 1000, 700 * tarea.intentos))
          cola.push(tarea)
        } else perdidas++
        continue
      }
      cobradas++
      const filas = r.cuerpo.local_results || []
      for (const x of filas) {
        if (!x.place_id || negocios.has(x.place_id)) continue
        const lat = x.gps_coordinates?.latitude, lng = x.gps_coordinates?.longitude
        negocios.set(x.place_id, {
          place_id: x.place_id, nombre: x.title, tipo: x.type || '', tipos: x.types || [],
          direccion: x.address || '', telefono: x.phone || '', web: x.website || '',
          nota: x.rating ?? null, resenas: x.reviews ?? null, lat, lng,
          dentro: typeof lat === 'number' ? dentro(zona.geojson, lat, lng) : false,
        })
      }
      const siguiente = (r.cuerpo.pagination || r.cuerpo.serpapi_pagination || {}).next
      const cerca = filas.filter((x) => x.gps_coordinates && km(tarea.p, [x.gps_coordinates.latitude, x.gps_coordinates.longitude]) <= zona.paso * 1.5).length
      if (filas.length === 20 && siguiente && cerca >= CERCA_MIN && tarea.pagina + 1 < PAGINAS) {
        cola.push({ p: tarea.p, pagina: tarea.pagina + 1, intentos: 0, clave: crypto.randomUUID() })
      }
    }
  }
  await Promise.all(Array.from({ length: PARALELO }, obrero))
  clearInterval(avance)
  guardar()
  const segundos = Math.round((Date.now() - t0) / 1000)
  const resumen = { negocio: zona.negocio, lugar: zona.lugar, llamadas, busquedas: cobradas, reintentos, sinHacer: perdidas + cola.length, gastoUsd: +gasto.toFixed(5), segundos, encontrados: negocios.size, dentroDeLaCiudad: [...negocios.values()].filter((n) => n.dentro).length, parada: parar }
  escribir(path.join(dir, 'busqueda.json'), resumen)
  if (parar === 'saldo') console.log('SIN SALDO: treg se ha quedado sin saldo. Lo encontrado hasta aquí está guardado; recarga en treg.to (Team → Billing) y vuelve a buscar.')
  else if (parar) console.log(`PARADA: ${parar}`)
  console.log('FIN', JSON.stringify(resumen))
}

// ---------- quedarse con el sector ----------

const GENERICAS = new Set(['clinica', 'clinicas', 'centro', 'centros', 'tienda', 'tiendas', 'empresa', 'empresas', 'servicio', 'servicios', 'agencia', 'agencias', 'despacho', 'despachos', 'estudio', 'estudios', 'negocio', 'negocios', 'local', 'locales', 'consulta'])

// Raíces del sector: «inmobiliaria» -> «inmobi», «dentista» -> «denti». Se revisan con `tipos`.
function raices(negocio) {
  const palabras = sinTildes(negocio).split(/[^a-z0-9ñ]+/).filter((p) => p.length >= 4)
  const propias = palabras.filter((p) => !GENERICAS.has(p))
  return (propias.length ? propias : palabras).map((p) => p.slice(0, Math.min(6, Math.max(4, p.length - 3))))
}

const textoTipo = (n) => sinTildes([n.tipo, ...(n.tipos || [])].join(' | '))

function tipos(o) {
  const dir = carpeta(o)
  const zona = leer(path.join(dir, 'zona.json'))
  const negocios = leer(path.join(dir, 'negocios.json')).filter((n) => n.dentro)
  const r = raices(zona.negocio)
  const cuenta = {}
  for (const n of negocios) cuenta[n.tipo || '(sin tipo)'] = (cuenta[n.tipo || '(sin tipo)'] || 0) + 1
  console.log(`RAÍCES por defecto: ${r.join(', ')}`)
  for (const [t, c] of Object.entries(cuenta).sort((a, b) => b[1] - a[1]).slice(0, 25)) {
    const entra = r.some((x) => sinTildes(t).includes(x))
    console.log(`${entra ? 'ENTRA' : 'fuera'}  ${String(c).padStart(5)}  ${t}`)
  }
}

function filtrar(o) {
  const dir = carpeta(o)
  const zona = leer(path.join(dir, 'zona.json'))
  const negocios = leer(path.join(dir, 'negocios.json'))
  const re = o.tipos && o.tipos !== true ? new RegExp(sinTildes(o.tipos), 'i') : null
  const r = raices(zona.negocio)
  const vale = (n) => o.todos || (re ? re.test(textoTipo(n)) : r.some((x) => textoTipo(n).includes(x) || sinTildes(n.nombre).includes(x)))
  const candidatos = negocios.filter((n) => (o['con-alrededores'] || n.dentro) && vale(n)).sort((a, b) => (b.resenas || 0) - (a.resenas || 0))
  // Un mismo negocio con dos fichas en Maps: mismo teléfono y mismo nombre. Se queda la de más reseñas.
  const vistos = new Set()
  const sel = candidatos.filter((n) => {
    const tel = String(n.telefono || '').replace(/\D/g, '')
    if (!tel) return true
    const clave = `${tel}|${sinTildes(n.nombre).replace(/[^a-z0-9]/g, '').slice(0, 12)}`
    if (vistos.has(clave)) return false
    vistos.add(clave)
    return true
  })
  escribir(path.join(dir, 'seleccion.json'), sel)
  console.log(JSON.stringify({ seleccionados: sel.length, conTelefono: sel.filter((n) => n.telefono).length, conWeb: sel.filter((n) => n.web).length, repetidos: candidatos.length - sel.length, descartados: negocios.length - candidatos.length }))
}

// ---------- correos ----------

const RE_CORREO = /[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,12}/g
const BASURA = /\.(png|jpe?g|gif|webp|svg|css|js|ico)$|@www\.|@(sentry[\w.-]*|[\w.-]*wixpress|example|ejemplo|domain|dominio|tudominio|midominio|sudominio|email|correo|company|empresa|miempresa|tuempresa|tuweb|miweb|godaddy|yourdomain|test)\.|^(nombre|name|tu|tucorreo|your|you|user|usuario|email|correo|filler|xxx+|ejemplo|example)@|u003e|^[0-9a-f]{20,}@/i
const ERRATAS = /@(agmail|gmial|gmai|gamil|hotmial|hotmal|yaho)\.com$/i
// Webs que son en realidad una red social o una ficha: ahí no hay correo que sacar.
const NO_WEB = /^(www\.|m\.)?((facebook|instagram|twitter|x|tiktok|youtube|linkedin)\.com|wa\.me|linktr\.ee|maps\.app\.goo\.gl)$|(^|\.)business\.site$|^(www\.)?google\.[a-z.]+$/i
const ENLACE_CONTACTO = /href=["']([^"'#]*(contact|contacto|aviso-legal|aviso_legal|legal|quienes-somos|about|privacidad)[^"']*)["']/gi

function descifrar(html) {
  return html.replace(/&#64;|&commat;|\[at\]|\(at\)|\[arroba\]|\(arroba\)/gi, '@').replace(/&#46;|\[dot\]|\(dot\)|\[punto\]|\(punto\)/gi, '.')
}

async function pagina(url) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 9000)
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA_WEB, 'Accept-Language': 'es-ES,es;q=0.9' }, redirect: 'follow', signal: ctrl.signal })
    if (!r.ok || !(r.headers.get('content-type') || '').includes('html')) return null
    const buf = await r.arrayBuffer()
    return { url: r.url, html: Buffer.from(buf.slice(0, 1_500_000)).toString('utf8') }
  } catch {
    return null
  } finally {
    clearTimeout(t)
  }
}

function correosEn(html, dominio) {
  const vistos = new Set()
  for (const m of descifrar(html).matchAll(RE_CORREO)) {
    const c = m[0].toLowerCase().replace(/^mailto:/, '').replace(/\.$/, '')
    if (!BASURA.test(c) && !ERRATAS.test(c)) vistos.add(c)
  }
  // Primero los del propio dominio de la web.
  return [...vistos].sort((a, b) => Number(b.endsWith('@' + dominio) || b.endsWith('.' + dominio)) - Number(a.endsWith('@' + dominio) || a.endsWith('.' + dominio)))
}

async function correos(o) {
  const dir = carpeta(o)
  const sel = leer(path.join(dir, 'seleccion.json'))
  const t0 = Date.now()
  let i = 0, hechas = 0, conCorreo = 0
  async function obrero() {
    while (i < sel.length) {
      const n = sel[i++]
      n.correos = []
      if (!n.web) continue
      const url = /^https?:\/\//.test(n.web) ? n.web : `https://${n.web}`
      let host = ''
      try { host = new URL(url).hostname } catch { continue }
      if (NO_WEB.test(host)) continue
      const dominio = host.replace(/^www\./, '')
      const portada = await pagina(url)
      let encontrados = portada ? correosEn(portada.html, dominio) : []
      if (portada && !encontrados.length) {
        const enlaces = [...new Set([...portada.html.matchAll(ENLACE_CONTACTO)].map((m) => m[1]))].slice(0, 3)
        for (const e of enlaces) {
          let u
          try { u = new URL(e, portada.url).href } catch { continue }
          const p = await pagina(u)
          if (p) encontrados = correosEn(p.html, dominio)
          if (encontrados.length) break
        }
      }
      n.correos = encontrados.slice(0, 3)
      hechas++
      if (n.correos.length) conCorreo++
      if (hechas % 50 === 0) console.log(JSON.stringify({ seg: Math.round((Date.now() - t0) / 1000), webs: hechas, conCorreo }))
    }
  }
  await Promise.all(Array.from({ length: 16 }, obrero))
  escribir(path.join(dir, 'seleccion.json'), sel)
  console.log('FIN', JSON.stringify({ segundos: Math.round((Date.now() - t0) / 1000), webs: hechas, conCorreo }))
}

// ---------- CSV ----------

function csv(o) {
  const dir = carpeta(o)
  const zona = leer(path.join(dir, 'zona.json'))
  const sel = leer(path.join(dir, 'seleccion.json'))
  const busqueda = fs.existsSync(path.join(dir, 'busqueda.json')) ? leer(path.join(dir, 'busqueda.json')) : {}
  // Con punto y coma y decimales con coma: así lo abre bien Excel en español (y Google Sheets también).
  const celda = (v) => {
    const s = v == null ? '' : String(v)
    return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const dec = (x) => (typeof x === 'number' ? String(x).replace('.', ',') : '')
  const redondo = (x) => (typeof x === 'number' ? +x.toFixed(6) : x)
  const cab = ['nombre', 'tipo', 'direccion', 'telefono', 'web', 'correo', 'otros_correos', 'nota', 'resenas', 'google_maps', 'lat', 'lng']
  const filas = sel
    .sort((a, b) => (b.resenas || 0) - (a.resenas || 0))
    .map((n) => [
      n.nombre, n.tipo, n.direccion, n.telefono, n.web, (n.correos || [])[0] || '', (n.correos || []).slice(1).join(' '),
      dec(n.nota), n.resenas ?? '', `https://www.google.com/maps/place/?q=place_id:${n.place_id}`, dec(redondo(n.lat)), dec(redondo(n.lng)),
    ].map(celda).join(';'))
  const nombre = `${sinTildes(zona.negocio)}-${sinTildes(zona.ciudad)}`.replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  const fichero = path.join(dir, `${nombre}.csv`)
  fs.writeFileSync(fichero, '﻿' + [cab.join(';'), ...filas].join('\r\n'))
  console.log('CSV', fichero)
  console.log(JSON.stringify({
    negocios: sel.length,
    conTelefono: sel.filter((n) => n.telefono).length,
    conWeb: sel.filter((n) => n.web).length,
    conCorreo: sel.filter((n) => (n.correos || []).length).length,
    gastoUsd: busqueda.gastoUsd ?? null,
    segundosMaps: busqueda.segundos ?? null,
  }))
}

const ORDENES = { comprobar, estimar, buscar, tipos, filtrar, correos, csv }
const o = args()
if (!ORDENES[o.orden]) {
  console.log(`Órdenes: ${Object.keys(ORDENES).join(', ')}`)
  process.exit(1)
}
Promise.resolve(ORDENES[o.orden](o)).catch((e) => {
  console.error('ERROR', e.message)
  process.exit(1)
})
