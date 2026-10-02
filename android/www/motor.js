// Motor de Videosyt para el teléfono, en dos fases y todo dentro de la app:
//   1. crearStoryboard: guion → escenas → imágenes (se pueden revisar, editar y regenerar)
//   2. renderizar: voces (+ clips opcionales) → montaje grabado desde un <canvas> con MediaRecorder.
// Si una escena falla se usa un respaldo para que el video siempre termine.

// Catálogo compartido con la app de escritorio (estilos/estilos.json, se copia al compilar).
export const ESTILOS = {};
const FUENTES = { sans: "system-ui, Roboto, sans-serif", serif: "Georgia, 'Times New Roman', serif" };

export async function cargarEstilos() {
  const lista = await (await fetch("./estilos.json")).json();
  for (const e of lista) ESTILOS[e.id] = { ...e, fuente: FUENTES[e.fuente], texto: e.color_texto, prompt: e.prompt_imagen };
  return ESTILOS;
}

/** El estilo del proyecto con su formato: el formato se elige aparte del estilo. */
function estiloDe(proyecto) {
  return { ...(ESTILOS[proyecto.estilo] || Object.values(ESTILOS)[0]), formato: proyecto.formato || "16:9",
           modelo: CALIDADES[proyecto.calidad] || CALIDADES.rapida, subtitulos: proyecto.subtitulos ?? true };
}

const TAMANOS = { "16:9": [1280, 720], "9:16": [720, 1280] };
const FPS = 25;
const LIMITES = { imagen: 4, voz: 2, video: 2 };  // llamadas a la vez por API (ElevenLabs gratis admite 2)
const NOMBRES = { imagen: "fal.ai (imágenes)", voz: "ElevenLabs (voz)", video: "fal.ai (clips de video)" };

// ---------- 1. Escenas (sin IA; formato de Scripzy) ----------

const VISUAL = /^\s*(?:visual|imagen|image|prompt|toma|plano)\s*:\s*(.+)$/i;
const CORCHETES = /^\s*[[(](.+)[\])]\s*$/;
const ETIQUETA = /^\s*(?:escena|scene|parte|part)\s*\d+\s*[:.\-–—]?\s*$/i;
const NARRADOR = /^\s*(?:narrador|narraci[oó]n|voz(?: en off)?|locutor|narrator)\s*:\s*/i;

// Ritmo: palabras por escena (a ~2,5 palabras por segundo).
export const RITMOS = { pocas: 25, normal: 12, muchas: 8 };
// Calidad de imagen → modelo de fal.ai.
export const CALIDADES = { rapida: "fal-ai/flux/schnell", buena: "fal-ai/flux/dev", maxima: "fal-ai/flux-pro/v1.1" };
const ORACION = /(?<=[.!?…])["'»”)]*\s+/;
const PAUSA = /(?<=[,;:])\s+/;
const contar = t => t.split(/\s+/).filter(Boolean).length;

/** Divide la narración en trozos de unas `objetivo` palabras sin cortar oraciones si se puede. */
export function partir(texto, objetivo) {
  const piezas = [];
  for (const oracion of texto.trim().split(ORACION)) {
    if (contar(oracion) > objetivo * 1.6) {  // oración muy larga: se corta en comas y, si hace falta, por palabras
      for (const parte of oracion.split(PAUSA)) {
        let palabras = parte.split(/\s+/).filter(Boolean);
        while (palabras.length > objetivo * 1.6) { piezas.push(palabras.slice(0, objetivo).join(" ")); palabras = palabras.slice(objetivo); }
        piezas.push(palabras.join(" "));
      }
    } else piezas.push(oracion);
  }
  const trozos = [];
  let actual = "";
  for (const pieza of piezas.map(p => p.trim()).filter(Boolean)) {
    const n = contar(actual), junto = n + contar(pieza);
    // Se une la pieza si deja el trozo más cerca del objetivo (o si el trozo aún es muy corto).
    if (n >= objetivo * 0.6 && Math.abs(junto - objetivo) > Math.abs(n - objetivo)) { trozos.push(actual); actual = pieza; }
    else actual = `${actual} ${pieza}`.trim();
  }
  if (actual) {
    if (trozos.length && contar(actual) < objetivo * 0.4) trozos[trozos.length - 1] += " " + actual;
    else trozos.push(actual);
  }
  return trozos;
}

/** Trozos cortos para mostrar de a uno mientras se narra (como en los Shorts). */
export function subtitulos(texto, maximo) {
  const palabras = texto.split(/\s+/).filter(Boolean);
  const tam = Math.ceil(palabras.length / Math.max(1, Math.ceil(palabras.length / maximo)));
  const res = [];
  for (let i = 0; i < palabras.length; i += tam) res.push(palabras.slice(i, i + tam).join(" "));
  return res;
}

/**
 * Cada párrafo da una o más escenas (los largos se parten por oraciones).
 * "Imagen: ..." o "[...]" describen la imagen de su primera escena y no se narran.
 */
export function escenas(texto, palabrasPorEscena = RITMOS.normal) {
  const resultado = [];
  let visualPendiente = null;
  for (const parrafo of texto.trim().split(/\n\s*\n/)) {
    const narracion = [], visuales = [];
    for (const linea of parrafo.split("\n")) {
      if (!linea.trim() || ETIQUETA.test(linea)) continue;
      const m = linea.match(VISUAL) || linea.match(CORCHETES);
      if (m) visuales.push(m[1].trim());
      else narracion.push(linea.replace(NARRADOR, "").trim());
    }
    if (visualPendiente) { visuales.unshift(visualPendiente); visualPendiente = null; }
    if (!narracion.length) {  // un párrafo solo con indicación visual describe la escena siguiente
      visualPendiente = visuales.join(" ") || null;
      continue;
    }
    const visual = visuales.join(" ");
    partir(narracion.join(" "), palabrasPorEscena).forEach((t, n) =>
      resultado.push({ narracion: t, prompt_visual: visual && n === 0 ? visual : t, visual_propio: Boolean(visual) && n === 0 }));
  }
  return resultado;
}

// ---------- Reintentos, límites y proveedores bloqueados ----------

const CODIGOS_DE_CUENTA = new Set([401, 402, 403]);

class ErrorHttp extends Error {
  constructor(servicio, status, cuerpo, reintentarEn) {
    super(`${servicio} respondió ${status}: ${cuerpo.slice(0, 300)}`);
    Object.assign(this, { status, reintentarEn });
  }
}
/** La cuenta no puede seguir (sin saldo, clave inválida): no tiene sentido reintentar. */
export class ErrorDeCuenta extends Error {}

const esperar = ms => new Promise(ok => setTimeout(ok, ms));

async function conReintentos(funcion, intentos = 4, base = 1000) {
  for (let n = 0; ; n++) {
    let espera;
    try {
      return await funcion();
    } catch (e) {
      if (e instanceof ErrorHttp) {
        if (CODIGOS_DE_CUENTA.has(e.status)) throw new ErrorDeCuenta(e.message);
        if (e.status !== 429 && e.status < 500) throw e;
        espera = e.reintentarEn ? e.reintentarEn * 1000 : base * 2 ** n;
      } else if (e instanceof TypeError) {  // sin conexión o la red se cortó
        espera = base * 2 ** n;
      } else throw e;
      if (n === intentos - 1) throw e;
    }
    await esperar(Math.min(espera, 30000) + Math.random() * base / 2);
  }
}

function limitador(maximo) {
  let activos = 0;
  const cola = [];
  return async funcion => {
    if (activos >= maximo) await new Promise(ok => cola.push(ok));
    activos++;
    try { return await funcion(); } finally { activos--; cola.shift()?.(); }
  };
}

function nuevaSesion() {
  const limites = Object.fromEntries(Object.entries(LIMITES).map(([k, v]) => [k, limitador(v)]));
  const bloqueados = {};
  return {
    bloqueados,
    async llamar(tipo, funcion) {
      return limites[tipo](async () => {
        if (bloqueados[tipo]) throw new ErrorDeCuenta(bloqueados[tipo]);
        try { return await conReintentos(funcion); }
        catch (e) { if (e instanceof ErrorDeCuenta) bloqueados[tipo] = e.message; throw e; }
      });
    },
  };
}

function avisosDeBloqueo(sesion) {
  return Object.entries(sesion.bloqueados)
    .map(([tipo, motivo]) => `${NOMBRES[tipo]} dejó de responder por un problema de la cuenta ` +
      `(saldo o clave): ${motivo}. Revisa la cuenta y vuelve a intentarlo.`);
}

async function pedir(servicio, url, opciones, como = "json") {
  const r = await fetch(url, opciones);
  if (!r.ok) throw new ErrorHttp(servicio, r.status, await r.text(), Number(r.headers.get("retry-after")) || 0);
  return como === "json" ? r.json() : r.arrayBuffer();
}

// ---------- 2. Voz ----------

function silencio(texto, audio) {
  const segundos = Math.max(3, texto.split(/\s+/).length / 2.5);
  return audio.createBuffer(2, Math.ceil(segundos * audio.sampleRate), audio.sampleRate);
}

async function voz(texto, claves, audio) {
  const id = claves.ELEVENLABS_VOICE_ID || "21m00Tcm4TlvDq8ikWAM";
  const datos = await pedir("ElevenLabs", `https://api.elevenlabs.io/v1/text-to-speech/${id}`, {
    method: "POST",
    headers: { "content-type": "application/json", "xi-api-key": claves.ELEVENLABS_API_KEY, accept: "audio/mpeg" },
    body: JSON.stringify({ text: texto, model_id: "eleven_multilingual_v2" }),
  }, "binario");
  return audio.decodeAudioData(datos);
}

// ---------- 3. Imagen (y clip animado opcional) ----------

function falPost(modelo, cuerpo, clave) {
  return pedir("fal.ai", `https://fal.run/${modelo}`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Key ${clave}` },
    body: JSON.stringify(cuerpo),
  });
}

async function urlLocal(url) {
  const r = await fetch(url);
  if (!r.ok) throw new ErrorHttp("La descarga", r.status, "");
  return URL.createObjectURL(await r.blob());
}

const SIN_TEXTO = "purely visual scene, no written words, no captions, no signs, no lettering anywhere";

/**
 * Primero lo que pasa en la escena, luego el estilo y al final el personaje fijo (si sale).
 * Antes la biblia iba primero en todas las escenas y Flux dibujaba siempre el mismo personaje
 * en el mismo lugar. El texto de la escena va como algo a ilustrar, no a escribir: si no, Flux
 * tiende a dibujar letras inventadas en carteles, libros o pantallas.
 */
export function componerPrompt(prompt, estilo, biblia = "") {
  const escena = prompt.trim().replace(/^["«“]+|["»”]+$/g, "");
  return [escena && `Scene illustrating: ${escena}`, estilo.prompt,
          biblia.trim() && `Recurring character: ${biblia.trim()}`, SIN_TEXTO].filter(Boolean).join(". ");
}

const SUAVE = "family friendly, symbolic and non-violent depiction, no blood, no gore, no nudity";

async function imagenIA(escena, proyecto, claves) {
  const estilo = estiloDe(proyecto);
  const prompt = componerPrompt(escena.prompt_visual, estilo, escena.personaje === false ? "" : proyecto.biblia);
  const cuerpo = { prompt, image_size: estilo.formato === "9:16" ? "portrait_16_9" : "landscape_16_9",
                   seed: escena.semilla ?? proyecto.semilla };
  for (let intento = 0; intento < 3; intento++) {
    const r = await falPost(estilo.modelo, cuerpo, claves.FAL_KEY);
    if (!(r.has_nsfw_concepts || []).some(Boolean)) return r.images[0].url;
    // El filtro de contenido de fal devuelve la imagen en negro (pasa con temas como violencia).
    // Se reintenta con otra semilla y una versión más suave de la escena.
    cuerpo.seed = (cuerpo.seed || 0) + 7919 * (intento + 1);
    cuerpo.prompt = `${prompt}. ${SUAVE}`;
  }
  throw new Error("el filtro de contenido de fal.ai la dejó en negro; prueba a cambiar la descripción");
}

async function cargarImagen(src) {
  const img = new Image();
  img.src = src;
  await img.decode();
  return img;
}

async function animar(escena, proyecto, claves) {
  const r = await falPost("fal-ai/kling-video/v2.1/standard/image-to-video", {
    prompt: `${escena.prompt_visual}, ${estiloDe(proyecto).prompt}, smooth camera motion`,
    image_url: escena.url, duration: "5",
  }, claves.FAL_KEY);
  const v = document.createElement("video");
  v.muted = true; v.loop = true; v.playsInline = true;
  v.src = await urlLocal(r.video.url);
  await new Promise((ok, mal) => { v.oncanplay = ok; v.onerror = () => mal(new Error("No se pudo cargar el clip")); });
  return v;
}

function tarjetaDemo(texto, estilo, numero) {
  const [ancho, alto] = TAMANOS[estilo.formato];
  const c = document.createElement("canvas");
  c.width = ancho; c.height = alto;
  const ctx = c.getContext("2d"), lado = Math.min(ancho, alto);
  ctx.fillStyle = estilo.fondo; ctx.fillRect(0, 0, ancho, alto);
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  ctx.fillStyle = "rgba(255,255,255,.35)";
  ctx.font = `bold ${Math.round(lado / 8)}px ${estilo.fuente}`;
  ctx.fillText(`ESCENA ${numero}`, ancho / 2, alto * 0.15);
  ctx.fillStyle = "rgba(255,255,255,.5)";
  ctx.font = `bold ${Math.round(lado / 28)}px ${estilo.fuente}`;
  lineas(ctx, texto, ancho * 0.6).forEach((l, i) => ctx.fillText(l, ancho / 2, alto * 0.45 + i * lado / 22));
  return c;
}

// ---------- Vistas previas de los estilos ----------

const ESCENA_DE_MUESTRA = ["sitting at a desk late at night, focused and determined",
                           "a desk with an open notebook and a warm lamp late at night"];

/** Imagen de muestra de un estilo, reducida para guardarla en el teléfono (data URL JPEG). */
export async function vistaPrevia(id, claves) {
  const estilo = ESTILOS[id];
  const proyecto = { estilo: id, formato: "16:9", calidad: "buena", biblia: estilo.personaje, semilla: 7 };
  const escena = { prompt_visual: ESCENA_DE_MUESTRA[estilo.personaje ? 0 : 1] };
  const url = await conReintentos(() => imagenIA(escena, proyecto, claves), 2);
  const img = await cargarImagen(await conReintentos(() => urlLocal(url)));
  const c = document.createElement("canvas");
  c.width = 384; c.height = 216;
  const escala = Math.max(c.width / img.width, c.height / img.height);
  c.getContext("2d").drawImage(img, (c.width - img.width * escala) / 2, (c.height - img.height * escala) / 2,
                               img.width * escala, img.height * escala);
  return c.toDataURL("image/jpeg", 0.8);
}

// ---------- Director: qué se ve en cada escena ----------
// Igual que proveedores/director.py: un modelo de texto barato (vía fal, con la misma FAL_KEY)
// lee el guion completo y describe cada escena con lugar, época, objetos y plano distintos.

const MODELOS_DIRECTOR = ["google/gemini-2.5-flash", "openai/gpt-4.1-mini"];
const POR_LOTE = 25, MAX_GUION = 12000;
const INSTRUCCIONES = `You are the art director of a faceless YouTube channel. You receive a narration script split into numbered scenes. For each scene write one prompt for an AI image model that shows what that part of the script is actually about: the concrete subject, place, era, objects and action.
Rules:
- English, 20 to 45 words per scene.
- Neighbouring scenes must look different: change the setting, the subject and the shot (wide establishing shot, close-up of an object, crowd, aerial view, detail of hands, silhouette, over-the-shoulder...).
- Follow the eras and places of the story (for example a smoky 1930s jazz club, a 1960s pirate radio ship, a modern phone screen).
- Turn abstract ideas and metaphors into concrete visual symbols.
- Never ask for written words, letters, logos, captions or readable signs.
- Show violent, cruel or tragic events symbolically (shadows, empty places, meaningful objects, faces reacting), never graphic violence, bodies, blood or nudity: the image model blacks those images out.
- Do not describe the art style; it is added later.
- If there is a recurring character, it is the protagonist of the video: put it in about three of every four scenes, acting out or reacting to what that scene is about, inside that scene's own setting and era. Start those prompts with the character's full description and set "personaje" to true. Leave it out (false) only for establishing shots, close-ups of objects or scenes about specific real people. If there is no recurring character, "personaje" is always false.
Reply only with a JSON array, one object per scene with the same numbers: [{"n": 1, "imagen": "...", "personaje": false}]`;

export function leerRespuesta(texto, numeros) {
  const m = (texto || "").match(/\[[\s\S]*\]/);
  if (!m) throw new Error("el director no devolvió una lista");
  const resultado = {};
  for (const item of JSON.parse(m[0]))
    if (item && numeros.has(item.n) && String(item.imagen || "").trim())
      resultado[item.n] = [String(item.imagen).trim(), Boolean(item.personaje)];
  if (!Object.keys(resultado).length) throw new Error("el director no describió ninguna escena");
  return resultado;
}

async function describirLote(guion, lote, personaje, clave) {
  const prompt = `Recurring character: ${personaje || "none"}\n\nFull script (context):\n${guion.slice(0, MAX_GUION)}` +
    `\n\nScenes to describe:\n${lote.map(([n, t]) => `${n}. ${t}`).join("\n")}`;
  let error;
  for (const model of MODELOS_DIRECTOR) {  // si un modelo no está disponible, se prueba el siguiente
    try {
      const r = await conReintentos(() => falPost("openrouter/router",
        { model, system_prompt: INSTRUCCIONES, prompt, temperature: 0.8 }, clave), 3);
      if (r.error) throw new Error(r.error);
      return leerRespuesta(r.output, new Set(lote.map(([n]) => n)));
    } catch (e) { error = e; }
  }
  throw error;
}

/** Devuelve {número de escena (desde 1): [descripción en inglés, aparece el personaje]}. */
async function describir(guion, narraciones, personaje, clave) {
  const numeradas = narraciones.map((t, i) => [i + 1, t]), lotes = [];
  for (let i = 0; i < numeradas.length; i += POR_LOTE) lotes.push(numeradas.slice(i, i + POR_LOTE));
  const resultados = await Promise.allSettled(lotes.map(l => describirLote(guion, l, personaje, clave)));
  const resultado = Object.assign({}, ...resultados.filter(r => r.status === "fulfilled").map(r => r.value));
  if (!Object.keys(resultado).length) throw resultados.find(r => r.status === "rejected").reason;
  return resultado;
}

/** Cambia el texto narrado de cada escena por una descripción visual; respeta las "Imagen:" del guion. */
async function dirigir(proyecto, guion, claves) {
  try {
    const descripciones = await describir(guion, proyecto.escenas.map(e => e.narracion), proyecto.biblia, claves.FAL_KEY);
    proyecto.escenas.forEach((e, i) => {
      if (descripciones[i + 1] && !e.visual_propio) [e.prompt_visual, e.personaje] = descripciones[i + 1];
    });
    return null;
  } catch (e) {
    console.error(e);
    return `No se pudo describir cada escena con IA (${e.message}); las imágenes se basan en el texto del guion.`;
  }
}

// ---------- Storyboard (fase 1) ----------

async function crearImagen(proyecto, i, claves, sesion) {
  const e = proyecto.escenas[i], estilo = estiloDe(proyecto);
  Object.assign(e, { aviso: null, respaldo_de: null });
  if (!claves.FAL_KEY) {
    e.fuente = tarjetaDemo(e.prompt_visual, estilo, i + 1);
    Object.assign(e, { src: e.fuente.toDataURL("image/jpeg", 0.8), url: null, estado: "demo" });
  } else {
    try {
      const url = await sesion.llamar("imagen", () => imagenIA(e, proyecto, claves));
      const src = await conReintentos(() => urlLocal(url));
      Object.assign(e, { fuente: await cargarImagen(src), src, url, estado: "ia" });
    } catch (err) {
      console.error(err);
      Object.assign(e, { fuente: null, src: null, url: null, estado: "fallida",
                         aviso: `No se pudo crear la imagen: ${err.message}` });
    }
  }
  e.version = (e.version || 0) + 1;
}

/** Las escenas sin imagen toman la imagen IA más cercana (preferentemente la anterior). */
function resolverRespaldos(proyecto) {
  const { escenas: lista } = proyecto, estilo = estiloDe(proyecto);
  for (const [i, e] of lista.entries()) {
    if (e.estado !== "fallida" && e.estado !== "respaldo") continue;
    const candidatas = lista.map((x, j) => [j, x]).filter(([, x]) => x.estado === "ia")
      .sort(([a], [b]) => (Math.abs(a - i) - Math.abs(b - i)) || (a > i) - (b > i));
    if (candidatas.length) {
      const [j, x] = candidatas[0];
      Object.assign(e, { fuente: x.fuente, src: x.src, url: x.url, estado: "respaldo", respaldo_de: j + 1 });
    } else {
      e.fuente = tarjetaDemo(e.prompt_visual, estilo, i + 1);
      Object.assign(e, { src: e.fuente.toDataURL("image/jpeg", 0.8), url: null, estado: "respaldo", respaldo_de: null });
    }
  }
}

/**
 * Crea las escenas y sus imágenes, sin voz ni montaje, para revisarlas antes de gastar más.
 * Devuelve el proyecto que luego reciben regenerarEscena y renderizar.
 */
export async function crearStoryboard({ guion, estilo, formato = "16:9", ritmo = "normal", calidad = "buena",
                                       subtitulos = true, biblia = "", claves, avisar }) {
  const lista = escenas(guion, RITMOS[ritmo]);
  if (!lista.length) throw new Error("El guion no tiene escenas con texto para narrar");
  const semilla = Math.floor(Math.random() * 2 ** 31);  // cada escena con la suya: composiciones distintas
  const proyecto = { estilo, formato, calidad, subtitulos, biblia, semilla, avisos: [],
                     escenas: lista.map((e, i) => ({ ...e, semilla: (semilla + i + 1) % 2 ** 31, personaje: true,
                                                     estado: "pendiente", version: 0 })) };
  let avisoDirector = null;
  if (claves.FAL_KEY) {
    avisar(1, "Pensando qué mostrar en cada escena");
    avisoDirector = await dirigir(proyecto, guion, claves);
  }
  const sesion = nuevaSesion();
  let hechas = 0;
  avisar(2, "Creando imágenes");
  await Promise.all(proyecto.escenas.map(async (_, i) => {
    await crearImagen(proyecto, i, claves, sesion);
    hechas++;
    avisar(2 + Math.round(96 * hechas / lista.length), `Imágenes (${hechas} de ${lista.length})`);
  }));
  resolverRespaldos(proyecto);
  proyecto.avisos = [...(avisoDirector ? [avisoDirector] : []), ...avisosDeBloqueo(sesion)];
  avisar(100, "Revisa las escenas");
  return proyecto;
}

/** Vuelve a crear la imagen de una escena con otra semilla (útil si salió mal o falló). */
export async function regenerarEscena(proyecto, i, claves) {
  proyecto.escenas[i].semilla = Math.floor(Math.random() * 2 ** 31);
  await crearImagen(proyecto, i, claves, nuevaSesion());
  resolverRespaldos(proyecto);
  return proyecto.escenas[i];
}

// ---------- 4. Montaje ----------

function lineas(ctx, texto, maximo) {
  const res = [];
  let linea = "";
  for (const palabra of texto.split(/\s+/)) {
    const prueba = linea ? `${linea} ${palabra}` : palabra;
    if (ctx.measureText(prueba).width > maximo && linea) { res.push(linea); linea = palabra; }
    else linea = prueba;
  }
  if (linea) res.push(linea);
  return res;
}

function dibujar(ctx, e, t, estilo, ancho, alto) {
  const fuente = e.clip || e.fuente;
  const fw = fuente.videoWidth || fuente.width, fh = fuente.videoHeight || fuente.height;
  // Una imagen de respaldo se recorre con zoom inverso para que no parezca repetida.
  const avance = Math.min(estilo.zoom * FPS * t, 0.3);
  const zoom = e.clip ? 1 : e.estado === "respaldo" ? 1.3 - avance : 1 + avance;
  const escala = Math.max(ancho / fw, alto / fh) * zoom;
  ctx.drawImage(fuente, (ancho - fw * escala) / 2, (alto - fh * escala) / 2, fw * escala, fh * escala);

  if (estilo.subtitulos) dibujarSubtitulo(ctx, e, t, estilo, ancho, alto);
}

/** Subtítulo corto (máximo 2 líneas) que cambia al ritmo de la voz, en vez de todo el texto de golpe. */
function dibujarSubtitulo(ctx, e, t, estilo, ancho, alto) {
  const vertical = alto > ancho;
  e.trozos ||= subtitulos(e.narracion, vertical ? 5 : 7);
  // Cada trozo dura en proporción a sus letras, que es más o menos lo que tarda en leerse.
  const total = e.trozos.reduce((s, x) => s + x.length, 0), meta = total * Math.min(t / (e.audio?.duration || 1), 0.999);
  let acumulado = 0, trozo = e.trozos[e.trozos.length - 1];
  for (const x of e.trozos) { acumulado += x.length; if (acumulado > meta) { trozo = x; break; } }

  const tam = Math.round(Math.min(ancho, alto) / 16), borde = 10;
  ctx.font = `bold ${tam}px ${estilo.fuente}`;
  ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.lineJoin = "round";
  const ls = lineas(ctx, trozo, ancho * (vertical ? 0.8 : 0.6)).slice(0, 2);
  const altoTexto = ls.length * tam * 1.2;
  const anchoTexto = Math.max(...ls.map(l => ctx.measureText(l).width));
  const y = alto - altoTexto - alto * (vertical ? 0.18 : 0.07);
  ctx.fillStyle = "rgba(0,0,0,.35)";
  ctx.fillRect((ancho - anchoTexto) / 2 - borde, y - borde, anchoTexto + 2 * borde, altoTexto + 2 * borde);
  ctx.lineWidth = Math.max(4, tam / 8); ctx.strokeStyle = "rgba(0,0,0,.85)"; ctx.fillStyle = estilo.texto;
  ls.forEach((l, i) => { ctx.strokeText(l, ancho / 2, y + i * tam * 1.2); ctx.fillText(l, ancho / 2, y + i * tam * 1.2); });
}

function formatoGrabacion() {
  const opciones = ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4",
                    "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  return opciones.find(t => MediaRecorder.isTypeSupported(t)) || "";
}

/**
 * Fase 2: voces (y clips) en paralelo y luego el montaje. Devuelve un Blob.
 * `audio` debe ser un AudioContext creado al tocar el botón (requisito del navegador).
 */
export async function renderizar({ proyecto, clips, claves, audio, lienzo, avisar }) {
  const estilo = estiloDe(proyecto), lista = proyecto.escenas;
  const [ancho, alto] = TAMANOS[estilo.formato];
  const sesion = nuevaSesion();
  const tareas = lista.length * (clips && claves.FAL_KEY ? 2 : 1);
  let hechas = 0;
  const paso = msg => { hechas++; avisar(Math.round(50 * hechas / tareas), `${msg} (${hechas} de ${tareas})`); };

  avisar(1, "Narrando escenas");
  await Promise.all(lista.map(async e => {
    e.aviso_voz = null; e.clip = null; e.trozos = null;
    const trabajos = [(async () => {
      if (!claves.ELEVENLABS_API_KEY) e.audio = silencio(e.narracion, audio);
      else {
        try { e.audio = await sesion.llamar("voz", () => voz(e.narracion, claves, audio)); }
        catch (err) { console.error(err); e.audio = silencio(e.narracion, audio); e.aviso_voz = err.message; }
      }
      paso("Voces y clips");
    })()];
    if (clips && claves.FAL_KEY) trabajos.push((async () => {
      if (e.estado === "ia") {
        try { e.clip = await sesion.llamar("video", () => animar(e, proyecto, claves)); }
        catch (err) { console.error(err); }  // sin clip: la escena usa la imagen con zoom
      }
      paso("Voces y clips");
    })());
    await Promise.all(trabajos);
  }));

  // Grabación en tiempo real: el video tarda en montarse lo mismo que dura.
  lienzo.width = ancho; lienzo.height = alto;
  const ctx = lienzo.getContext("2d");
  const destino = audio.createMediaStreamDestination();
  const flujo = lienzo.captureStream(FPS);
  flujo.addTrack(destino.stream.getAudioTracks()[0]);
  const tipo = formatoGrabacion();
  const grabadora = new MediaRecorder(flujo, { mimeType: tipo, videoBitsPerSecond: 5_000_000 });
  const partes = [];
  grabadora.ondataavailable = ev => ev.data.size && partes.push(ev.data);
  const terminado = new Promise(ok => { grabadora.onstop = ok; });

  const total = lista.reduce((s, e) => s + e.audio.duration, 0);
  let hecho = 0;
  dibujar(ctx, lista[0], 0, estilo, ancho, alto);
  grabadora.start(1000);
  for (const [i, e] of lista.entries()) {
    const msg = `Montando escena ${i + 1} de ${lista.length}`;
    if (e.clip) { e.clip.currentTime = 0; await e.clip.play(); }
    const narracion = audio.createBufferSource();
    narracion.buffer = e.audio; narracion.connect(destino);
    const inicio = audio.currentTime + 0.05;
    narracion.start(inicio);
    await new Promise(ok => {
      const cuadro = () => {
        const t = Math.max(0, audio.currentTime - inicio);
        dibujar(ctx, e, t, estilo, ancho, alto);
        if (t >= e.audio.duration) return ok();
        avisar(50 + Math.round(48 * (hecho + t) / total), msg);
        requestAnimationFrame(cuadro);
      };
      cuadro();
    });
    if (e.clip) e.clip.pause();
    hecho += e.audio.duration;
  }
  grabadora.stop();
  await terminado;
  proyecto.avisos = [...avisosDeBloqueo(sesion), ...resumenRespaldos(proyecto)];
  avisar(100, "Listo");
  return new Blob(partes, { type: tipo.split(";")[0] || "video/webm" });
}

export function resumenRespaldos(proyecto) {
  const avisos = [];
  const imagenes = proyecto.escenas.filter(e => e.estado === "respaldo").length;
  const voces = proyecto.escenas.filter(e => e.aviso_voz).length;
  if (imagenes) avisos.push(`${imagenes} escena(s) usaron una imagen de respaldo.`);
  // El motivo (p. ej. 429 por demasiadas a la vez, o cuota agotada) dice qué hay que arreglar.
  const motivo = proyecto.escenas.find(e => e.aviso_voz)?.aviso_voz;
  if (voces) avisos.push(`${voces} escena(s) quedaron sin voz porque ElevenLabs falló: ${motivo}`);
  return avisos;
}
