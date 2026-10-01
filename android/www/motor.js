// Motor de Videosyt para el teléfono: guion → escenas → voz → imagen → video,
// todo dentro de la app. El montaje se graba desde un <canvas> con MediaRecorder.

export const ESTILOS = {
  cinematico: { nombre: "Cinemático", formato: "16:9", fondo: "#1a1a2e", texto: "#ffffff",
    fuente: "Georgia, 'Times New Roman', serif", zoom: 0.0010,
    prompt: "cinematic film still, dramatic lighting, shallow depth of field, 35mm, high detail" },
  anime: { nombre: "Anime", formato: "16:9", fondo: "#ff7eb6", texto: "#ffffff",
    fuente: "system-ui, Roboto, sans-serif", zoom: 0.0015,
    prompt: "anime style, studio ghibli inspired, vibrant colors, soft cel shading" },
  shorts: { nombre: "Shorts vertical", formato: "9:16", fondo: "#0f9b8e", texto: "#ffff00",
    fuente: "system-ui, Roboto, sans-serif", zoom: 0.0020,
    prompt: "bold modern illustration, high contrast, clean background, vertical composition" },
};
const TAMANOS = { "16:9": [1280, 720], "9:16": [720, 1280] };
const FPS = 25;

// ---------- 1. Escenas ----------

async function escenas(guion, estilo, claves) {
  if (!claves.ANTHROPIC_API_KEY) {
    return guion.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
      .map(p => ({ narracion: p, prompt_visual: p }));
  }
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": claves.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({
      model: claves.CLAUDE_MODEL || "claude-sonnet-5-5",
      max_tokens: 4000,
      messages: [{ role: "user", content:
        `Divide este guion en escenas para un video.\nEstilo visual: ${estilo.prompt}\n` +
        `Devuelve SOLO un JSON: una lista de objetos con "narracion" (texto que se lee en voz alta, ` +
        `en el idioma del guion) y "prompt_visual" (descripción en inglés de la imagen de esa escena, ` +
        `sin texto escrito en la imagen).\n\nGuion:\n${guion}` }],
    }),
  });
  if (!r.ok) throw new Error(`Claude respondió ${r.status}: ${await r.text()}`);
  // La respuesta puede traer varios bloques (por ejemplo de razonamiento); se usan solo los de texto.
  const texto = ((await r.json()).content || []).filter(b => b.type === "text").map(b => b.text).join("");
  const inicio = texto.indexOf("["), fin = texto.lastIndexOf("]");
  if (inicio < 0 || fin < inicio) throw new Error("Claude no devolvió la lista de escenas. Intenta de nuevo.");
  return JSON.parse(texto.slice(inicio, fin + 1));
}

// ---------- 2. Voz ----------

async function voz(texto, claves, audio) {
  if (!claves.ELEVENLABS_API_KEY) {
    const segundos = Math.max(3, texto.split(/\s+/).length / 2.5);
    return audio.createBuffer(2, Math.ceil(segundos * audio.sampleRate), audio.sampleRate);
  }
  const id = claves.ELEVENLABS_VOICE_ID || "21m00Tcm4TlvDq8ikWAM";
  const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${id}`, {
    method: "POST",
    headers: { "content-type": "application/json", "xi-api-key": claves.ELEVENLABS_API_KEY, accept: "audio/mpeg" },
    body: JSON.stringify({ text: texto, model_id: "eleven_multilingual_v2" }),
  });
  if (!r.ok) throw new Error(`ElevenLabs respondió ${r.status}: ${await r.text()}`);
  return audio.decodeAudioData(await r.arrayBuffer());
}

// ---------- 3. Imagen (y clip animado opcional) ----------

async function falPost(modelo, cuerpo, clave) {
  const r = await fetch(`https://fal.run/${modelo}`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Key ${clave}` },
    body: JSON.stringify(cuerpo),
  });
  if (!r.ok) throw new Error(`fal.ai respondió ${r.status}: ${await r.text()}`);
  return r.json();
}

async function urlLocal(url) {
  const r = await fetch(url);
  return URL.createObjectURL(await r.blob());
}

async function imagen(escena, estilo, claves, numero, [ancho, alto]) {
  if (!claves.FAL_KEY) return tarjetaDemo(escena.prompt_visual, estilo, numero, ancho, alto);
  const r = await falPost("fal-ai/flux/schnell", {
    prompt: `${escena.prompt_visual}, ${estilo.prompt}`,
    image_size: estilo.formato === "9:16" ? "portrait_16_9" : "landscape_16_9",
  }, claves.FAL_KEY);
  const url = r.images[0].url;
  const img = new Image();
  img.src = await urlLocal(url);
  await img.decode();
  img.urlRemota = url;
  return img;
}

async function animar(img, escena, estilo, claves) {
  const r = await falPost("fal-ai/kling-video/v2.1/standard/image-to-video", {
    prompt: `${escena.prompt_visual}, ${estilo.prompt}, smooth camera motion`,
    image_url: img.urlRemota, duration: "5",
  }, claves.FAL_KEY);
  const v = document.createElement("video");
  v.muted = true; v.loop = true; v.playsInline = true;
  v.src = await urlLocal(r.video.url);
  await new Promise((ok, mal) => { v.oncanplay = ok; v.onerror = () => mal(new Error("No se pudo cargar el clip")); });
  return v;
}

function tarjetaDemo(texto, estilo, numero, ancho, alto) {
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

function dibujar(ctx, fuente, t, escena, estilo, ancho, alto) {
  const fw = fuente.videoWidth || fuente.width, fh = fuente.videoHeight || fuente.height;
  const zoom = fuente.tagName === "VIDEO" ? 1 : Math.min(1 + estilo.zoom * FPS * t, 1.3);
  const escala = Math.max(ancho / fw, alto / fh) * zoom;
  ctx.drawImage(fuente, (ancho - fw * escala) / 2, (alto - fh * escala) / 2, fw * escala, fh * escala);

  const lado = Math.min(ancho, alto), tam = Math.round(lado / 20), borde = 14;
  ctx.font = `bold ${tam}px ${estilo.fuente}`;
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  const ls = lineas(ctx, escena.narracion, ancho * (alto > ancho ? 0.8 : 0.7));
  const altoTexto = ls.length * tam * 1.25;
  const anchoTexto = Math.max(...ls.map(l => ctx.measureText(l).width));
  const y = alto - altoTexto - alto * 0.08;
  ctx.fillStyle = "rgba(0,0,0,.55)";
  ctx.fillRect((ancho - anchoTexto) / 2 - borde, y - borde, anchoTexto + 2 * borde, altoTexto + 2 * borde);
  ctx.fillStyle = estilo.texto;
  ls.forEach((l, i) => ctx.fillText(l, ancho / 2, y + i * tam * 1.25));
}

function formatoGrabacion() {
  const opciones = ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4",
                    "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  return opciones.find(t => MediaRecorder.isTypeSupported(t)) || "";
}

// ---------- Flujo completo ----------

/**
 * Crea el video y devuelve un Blob. `avisar(porcentaje, mensaje)` informa el progreso.
 * `audio` debe ser un AudioContext creado al tocar el botón (requisito del navegador).
 */
export async function crearVideo({ guion, estilo: idEstilo, clips, claves, audio, lienzo, avisar }) {
  const estilo = ESTILOS[idEstilo];
  const [ancho, alto] = TAMANOS[estilo.formato];
  clips = clips && !!claves.FAL_KEY;

  avisar(2, "Dividiendo el guion en escenas");
  const lista = await escenas(guion, estilo, claves);

  for (const [i, e] of lista.entries()) {
    const avance = 5 + Math.round(45 * i / lista.length), cual = `Escena ${i + 1} de ${lista.length}`;
    avisar(avance, `${cual}: narrando`);
    e.audio = await voz(e.narracion, claves, audio);
    avisar(avance, `${cual}: creando imagen`);
    e.fuente = await imagen(e, estilo, claves, i + 1, [ancho, alto]);
    if (clips) {
      avisar(avance, `${cual}: animando (puede tardar unos minutos)`);
      e.fuente = await animar(e.fuente, e, estilo, claves);
    }
  }

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
  dibujar(ctx, lista[0].fuente, 0, lista[0], estilo, ancho, alto);
  grabadora.start(1000);
  for (const [i, e] of lista.entries()) {
    avisar(50 + Math.round(48 * hecho / total), `Montando escena ${i + 1} de ${lista.length}`);
    if (e.fuente.tagName === "VIDEO") { e.fuente.currentTime = 0; await e.fuente.play(); }
    const narracion = audio.createBufferSource();
    narracion.buffer = e.audio; narracion.connect(destino);
    const inicio = audio.currentTime + 0.05;
    narracion.start(inicio);
    await new Promise(ok => {
      const cuadro = () => {
        const t = audio.currentTime - inicio;
        dibujar(ctx, e.fuente, Math.max(0, t), e, estilo, ancho, alto);
        if (t >= e.audio.duration) return ok();
        avisar(50 + Math.round(48 * (hecho + Math.max(0, t)) / total), `Montando escena ${i + 1} de ${lista.length}`);
        requestAnimationFrame(cuadro);
      };
      cuadro();
    });
    if (e.fuente.tagName === "VIDEO") e.fuente.pause();
    hecho += e.audio.duration;
  }
  grabadora.stop();
  await terminado;
  avisar(100, "Listo");
  return new Blob(partes, { type: tipo.split(";")[0] || "video/webm" });
}
