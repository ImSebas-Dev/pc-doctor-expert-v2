/* Detección de componentes. El navegador solo revela una parte (procesador lógico, gráfica y sistema); el resto llega del
   comando de PowerShell que la persona ejecuta y pega. Nada se envía al servidor hasta que ella pulse Guardar. */

const GRAFICA_DEDICADA = /(GeForce|NVIDIA|RTX|GTX|Quadro|Radeon\s*(RX|Pro|R[579])|Arc\s*A\d)/i;
const GRAFICA_INTEGRADA = /Intel.*(UHD|HD Graphics|Iris)|Radeon.*Graphics|Vega|Apple/i;

function nombreGrafica() {
  try {
    const gl = document.createElement("canvas").getContext("webgl") || document.createElement("canvas").getContext("experimental-webgl");
    const ext = gl && gl.getExtension("WEBGL_debug_renderer_info");
    const bruto = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "";
    const partes = bruto.replace(/^ANGLE \(|\)$/g, "").split(",").map((x) => x.trim());
    const nombre = (partes.length > 1 ? partes[1] : partes[0]).replace(/\s+Direct3D.*$/i, "").replace(/\(0x[0-9a-f]+\)/gi, "").replace(/\s{2,}/g, " ").trim();
    return nombre;
  } catch { return ""; }
}

async function sistemaOperativo() {
  const ua = navigator.userAgentData;
  if (ua && ua.getHighEntropyValues) {
    const v = await ua.getHighEntropyValues(["platformVersion"]).catch(() => null);
    if (ua.platform === "Windows" && v) return parseInt(v.platformVersion, 10) >= 13 ? "Windows 11" : "Windows 10";
    if (ua.platform) return ua.platform;
  }
  const u = navigator.userAgent;
  return /Windows/.test(u) ? "Windows" : /Mac OS X/.test(u) ? "macOS" : /Android/.test(u) ? "Android" : /Linux/.test(u) ? "Linux" : "";
}

/* Lo que el navegador permite sin pedir ningún permiso. «hilos» son procesadores lógicos, no núcleos físicos. */
export async function detectarNavegador() {
  const gpu = nombreGrafica();
  return { so: await sistemaOperativo(), hilos: navigator.hardwareConcurrency || null, gpu, gpu_dedicada: gpu ? GRAFICA_DEDICADA.test(gpu) && !GRAFICA_INTEGRADA.test(gpu) : null };
}

const TIPOS_RAM = ["DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR5"];
const TIPOS_DISCO = ["SSD NVMe", "SSD SATA", "HDD"];
const texto = (v, max) => (typeof v === "string" ? v.replace(/[\u0000-\u001f\u007f]/g, "").trim().slice(0, max) : "");
const entero = (v) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Math.round(Number(v)) : "");
const lista = (v) => (Array.isArray(v) ? v : v && typeof v === "object" ? [v] : []);

/* Convierte el texto pegado en datos del formulario. Valida la forma; el servidor vuelve a validar todo al guardar. */
export function interpretarJson(entrada) {
  let d;
  try { d = JSON.parse(entrada); } catch { throw new Error("No pudimos leer ese resultado. Copia de nuevo el resultado completo del comando y pégalo aquí."); }
  if (!d || typeof d !== "object" || Array.isArray(d)) throw new Error("Ese resultado no tiene el formato esperado.");
  const ram = lista(d.ram).slice(0, 8).map((m) => ({ capacidad_gb: entero(m.capacidad_gb), tipo: TIPOS_RAM.includes(m.tipo) ? m.tipo : "DDR4", frecuencia_mhz: entero(m.frecuencia_mhz), marca: texto(m.marca, 40) }));
  let discos = lista(d.discos).slice(0, 8).map((x) => ({ tipo: TIPOS_DISCO.includes(x.tipo) ? x.tipo : "SSD SATA", capacidad_gb: entero(x.capacidad_gb), modelo: texto(x.modelo, 60), es_sistema: x.es_sistema === true }));
  let aviso = "";
  if (discos.length && discos.filter((x) => x.es_sistema).length !== 1) { discos = discos.map((x, i) => ({ ...x, es_sistema: i === 0 })); aviso = "No pudimos saber cuál es el disco del sistema: revisa que esté bien marcado."; }
  if (!ram.length && !discos.length) throw new Error("El resultado no trae memoria ni discos. Ejecuta el comando completo en PowerShell.");
  return { so: texto(d.so, 60), procesador: texto(d.procesador, 80), nucleos: entero(d.nucleos), gpu: texto(d.gpu, 80), gpu_dedicada: d.gpu_dedicada === true, ram, discos, aviso };
}
