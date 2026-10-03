// Historial de videos hechos, guardado en el teléfono (IndexedDB de la app).
// Los datos (título, fecha, miniatura) y el video van en almacenes separados para
// que la lista se cargue rápido sin leer los videos. Con cada video se guarda también su
// storyboard (escenas e imágenes) para poder rehacerlo sin volver a pagar las imágenes.

const BASE = "videosyt", VERSION = 2;

function abrir() {
  return new Promise((ok, mal) => {
    const pedido = indexedDB.open(BASE, VERSION);
    pedido.onupgradeneeded = () => {  // la versión 1 no tenía "proyectos"
      const db = pedido.result;
      if (!db.objectStoreNames.contains("videos")) db.createObjectStore("videos", { keyPath: "id" });
      if (!db.objectStoreNames.contains("archivos")) db.createObjectStore("archivos");
      if (!db.objectStoreNames.contains("proyectos")) db.createObjectStore("proyectos");
    };
    pedido.onsuccess = () => ok(pedido.result);
    pedido.onerror = () => mal(pedido.error);
  });
}

async function operar(almacenes, modo, trabajo) {
  const db = await abrir();
  return new Promise((ok, mal) => {
    const tx = db.transaction(almacenes, modo);
    const resultado = trabajo(tx);
    tx.oncomplete = () => { db.close(); ok(resultado?.result); };
    tx.onerror = tx.onabort = () => { db.close(); mal(tx.error); };
  });
}

/**
 * Guarda un video terminado y devuelve sus datos. `storyboard` ({ proyecto, imagenes }) es
 * opcional: el proyecto sin objetos del navegador y una imagen (Blob) por escena.
 */
export async function guardarVideo({ blob, titulo, estilo, miniatura, storyboard }) {
  navigator.storage?.persist?.();  // pide que Android no borre el historial si falta espacio
  const datos = { id: `${Date.now()}`, titulo, estilo, miniatura, fecha: new Date().toISOString(),
                  tamano: blob.size, tipo: blob.type, rehacer: Boolean(storyboard) };
  await operar(["videos", "archivos", "proyectos"], "readwrite", tx => {
    tx.objectStore("videos").put(datos);
    tx.objectStore("archivos").put(blob, datos.id);
    if (storyboard) tx.objectStore("proyectos").put(storyboard, datos.id);
  });
  return datos;
}

/** El storyboard con que se hizo un video ({ proyecto, imagenes }), o undefined. */
export function leerStoryboard(id) {
  return operar(["proyectos"], "readonly", tx => tx.objectStore("proyectos").get(id));
}

/** Datos de todos los videos, del más nuevo al más viejo. */
export async function listarVideos() {
  const todos = await operar(["videos"], "readonly", tx => tx.objectStore("videos").getAll());
  return todos.sort((a, b) => b.fecha.localeCompare(a.fecha));
}

export function leerVideo(id) {
  return operar(["archivos"], "readonly", tx => tx.objectStore("archivos").get(id));
}

export function borrarVideo(id) {
  return operar(["videos", "archivos", "proyectos"], "readwrite", tx => {
    tx.objectStore("videos").delete(id);
    tx.objectStore("archivos").delete(id);
    tx.objectStore("proyectos").delete(id);
  });
}

/** Anota el nombre con que se guardó en Documentos/Videosyt, para no listarlo dos veces. */
export async function marcarArchivo(id, archivo) {
  const db = await abrir();
  return new Promise((ok, mal) => {
    const tx = db.transaction(["videos"], "readwrite"), almacen = tx.objectStore("videos");
    const pedido = almacen.get(id);
    pedido.onsuccess = () => { if (pedido.result) almacen.put({ ...pedido.result, archivo }); };
    tx.oncomplete = () => { db.close(); ok(); };
    tx.onerror = tx.onabort = () => { db.close(); mal(tx.error); };
  });
}
