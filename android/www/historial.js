// Historial de videos hechos, guardado en el teléfono (IndexedDB de la app).
// Los datos (título, fecha, miniatura) y el video van en almacenes separados para
// que la lista se cargue rápido sin leer los videos.

const BASE = "videosyt", VERSION = 1;

function abrir() {
  return new Promise((ok, mal) => {
    const pedido = indexedDB.open(BASE, VERSION);
    pedido.onupgradeneeded = () => {
      pedido.result.createObjectStore("videos", { keyPath: "id" });
      pedido.result.createObjectStore("archivos");
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

/** Guarda un video terminado y devuelve sus datos. */
export async function guardarVideo({ blob, titulo, estilo, miniatura }) {
  navigator.storage?.persist?.();  // pide que Android no borre el historial si falta espacio
  const datos = { id: `${Date.now()}`, titulo, estilo, miniatura, fecha: new Date().toISOString(),
                  tamano: blob.size, tipo: blob.type };
  await operar(["videos", "archivos"], "readwrite", tx => {
    tx.objectStore("videos").put(datos);
    tx.objectStore("archivos").put(blob, datos.id);
  });
  return datos;
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
  return operar(["videos", "archivos"], "readwrite", tx => {
    tx.objectStore("videos").delete(id);
    tx.objectStore("archivos").delete(id);
  });
}
