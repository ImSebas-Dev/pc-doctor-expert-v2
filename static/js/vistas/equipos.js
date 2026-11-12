/* Equipos y sus componentes (RF-01): memoria RAM por módulos, varios discos, tarjeta gráfica y procesador.
   Estos datos los usa el motor de diagnóstico, por eso se piden con detalle y se pueden detectar automáticamente. */
import { api } from "../api.js";
import { anunciar, avisar, campo, confirmar, formulario, h, icono, mensaje } from "../ui.js";
import { detectarNavegador, interpretarJson } from "../deteccion.js";

const TIPOS_RAM = ["DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR5"];
const TIPOS_DISCO = ["SSD NVMe", "SSD SATA", "HDD"];
const MAXIMO = 8;
const ramVacia = () => ({ capacidad_gb: "", tipo: "DDR4", frecuencia_mhz: "", marca: "" });
const discoVacio = (es_sistema = false) => ({ tipo: "SSD NVMe", capacidad_gb: "", modelo: "", es_sistema });
const nota = (texto) => h("p", { class: "nota" }, icono("info"), h("span", null, texto));
const items = (textos) => h("ul", { class: "limpia compacta" }, textos.map((t) => h("li", null, t)));
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

/* ---------- Lista ---------- */
function tarjeta(e, recargar) {
  const id = `eq-${e.id}`, r = e.resumen;
  const fila = (t, v) => [h("dt", null, t), h("dd", null, v)];
  return h("section", { class: "tarjeta equipo", "aria-labelledby": id },
    h("h2", { id }, e.nombre), h("p", { class: "meta" }, e.sistema_operativo),
    h("dl", { class: "datos" },
      ...fila("Procesador", `${e.procesador} · ${plural(e.cpu_nucleos, "núcleo", "núcleos")}`),
      ...fila("Tarjeta gráfica", `${e.gpu} (${e.gpu_dedicada ? "dedicada" : "integrada"})`),
      ...fila("Memoria RAM", h("div", null, `${r.ram_total_gb} GB en ${plural(r.ram_modulos, "módulo", "módulos")}`, items(e.ram.map((m) => m.etiqueta)))),
      ...fila("Almacenamiento", items(e.discos.map((d) => d.etiqueta)))),
    r.avisos.map(nota),
    h("div", { class: "acciones" },
      h("a", { class: "boton primario", href: `#/diagnostico?equipo=${e.id}` }, "Diagnosticar", h("span", { class: "solo-lector" }, ` ${e.nombre}`)),
      h("a", { class: "boton", href: `#/equipos/${e.id}/editar` }, "Editar", h("span", { class: "solo-lector" }, ` ${e.nombre}`)),
      h("button", { class: "boton peligro", type: "button", onclick: async () => {
        if (await confirmar("Eliminar equipo", `Se eliminará «${e.nombre}» y también sus diagnósticos. Esta acción no se puede deshacer.`, "Eliminar")) {
          await api("delete", `/api/equipos/${e.id}`, {}); await recargar(`Equipo ${e.nombre} eliminado`); document.querySelector("#contenido h1").focus(); } } }, "Eliminar", h("span", { class: "solo-lector" }, ` ${e.nombre}`))));
}

export async function equipos() {
  const lista = h("div", { class: "rejilla" });
  const pintar = async (anuncio) => {
    const { equipos: es } = await api("get", "/api/equipos");
    lista.replaceChildren(...(es.length ? es.map((e) => tarjeta(e, pintar)) : [mensaje("info", "Aún no tienes equipos. Agrega el primero para poder hacer un diagnóstico.")]));
    if (anuncio) anunciar(anuncio);
  };
  await pintar();
  return { titulo: "Mis equipos", nodo: h("div", null, h("div", { class: "cabecera-pagina" }, h("h1", null, "Mis equipos"), h("a", { class: "boton primario", href: "#/equipos/nuevo" }, "Agregar equipo")), lista) };
}

/* ---------- Formulario ---------- */
export async function editorEquipo(params) {
  const actual = params.id ? (await api("get", "/api/equipos")).equipos.find((e) => String(e.id) === params.id) : null;
  if (params.id && !actual) throw new Error("No encontramos ese equipo.");
  const est = {
    ram: actual ? actual.ram.map((m) => ({ ...m, marca: m.marca ?? "" })) : [ramVacia()],
    discos: actual ? actual.discos.map((d) => ({ ...d, modelo: d.modelo ?? "" })) : [discoVacio(true)],
  };
  const basicos = {
    nombre: campo({ nombre: "nombre", etiqueta: "Nombre del equipo", valor: actual?.nombre ?? "", maximo: 60, ayuda: "Por ejemplo: Portátil de la oficina." }),
    sistema_operativo: campo({ nombre: "sistema_operativo", etiqueta: "Sistema operativo", valor: actual?.sistema_operativo ?? "", maximo: 60, ayuda: "Por ejemplo: Windows 11." }),
    procesador: campo({ nombre: "procesador", etiqueta: "Procesador", valor: actual?.procesador ?? "", maximo: 80, ayuda: "Por ejemplo: Intel Core i7-12700H." }),
    cpu_nucleos: campo({ nombre: "cpu_nucleos", etiqueta: "Núcleos del procesador", tipo: "number", valor: actual?.cpu_nucleos ?? "", minimo: 1, maximo: 128, ayuda: "En Windows: Administrador de tareas, pestaña Rendimiento, CPU." }),
    gpu: campo({ nombre: "gpu", etiqueta: "Tarjeta gráfica", valor: actual?.gpu ?? "", maximo: 80, ayuda: "Por ejemplo: NVIDIA GeForce GTX 1660 o Intel UHD Graphics." }),
    gpu_dedicada: campo({ nombre: "gpu_dedicada", etiqueta: "Es una tarjeta gráfica dedicada (no integrada en el procesador)", tipo: "casilla", valor: actual?.gpu_dedicada ?? false }),
  };

  /* Filas dinámicas: el estado vive en `est`; al agregar o quitar se vuelven a dibujar y los campos se nombran por posición (ram.0.tipo). */
  const filas = { ram: [], discos: [] };
  const cajas = { ram: h("div", { class: "modulos" }), discos: h("div", { class: "modulos" }) };
  const botones = {};
  const resumenRam = h("div", { class: "resumen-componentes", "aria-live": "polite" });
  const grupoSistema = { nombre: "discos.0.es_sistema", requerido: false, raiz: null, entrada: null, valor: () => null,
    fallar(t) { errorSistema.textContent = t; }, limpiar() { errorSistema.textContent = ""; } };
  const errorSistema = h("p", { class: "error-campo", id: "error-sistema" });

  function avisosRam() {
    const ram = est.ram.filter((m) => m.capacidad_gb && m.frecuencia_mhz);
    const tipos = [...new Set(est.ram.map((m) => m.tipo))];
    const out = [];
    if (tipos.length > 1) out.push(["error", `No se pueden mezclar ${tipos.join(" y ")}: no son compatibles entre sí.`]);
    if (est.ram.length === 1) out.push(["info", "Con un solo módulo la memoria trabaja en canal único, más lento que con dos módulos iguales."]);
    const frec = [...new Set(ram.map((m) => m.frecuencia_mhz))];
    if (frec.length > 1) out.push(["info", `Frecuencias distintas: todos los módulos funcionarán a ${Math.min(...frec)} MHz, la del más lento.`]);
    if (new Set(ram.map((m) => m.capacidad_gb)).size > 1) out.push(["info", "Capacidades distintas: funcionan, pero parte de la memoria puede trabajar en canal único."]);
    return out;
  }
  function actualizarResumen() {
    const total = est.ram.reduce((s, m) => s + (Number(m.capacidad_gb) || 0), 0);
    resumenRam.replaceChildren(h("p", { class: "total" }, `Total: ${total} GB en ${plural(est.ram.length, "módulo", "módulos")}`),
      ...avisosRam().map(([t, x]) => (t === "error" ? mensaje("error", x) : nota(x))));
  }

  function filaRam(i) {
    const m = est.ram[i], n = `Módulo ${i + 1}`, k = `ram.${i}.`;
    const c = {
      capacidad_gb: campo({ nombre: `${k}capacidad_gb`, etiqueta: `${n} · capacidad (GB)`, tipo: "number", valor: m.capacidad_gb, minimo: 1, maximo: 256 }),
      tipo: campo({ nombre: `${k}tipo`, etiqueta: `${n} · tipo`, tipo: "select", valor: m.tipo, opciones: TIPOS_RAM.map((t) => ({ valor: t, texto: t })) }),
      frecuencia_mhz: campo({ nombre: `${k}frecuencia_mhz`, etiqueta: `${n} · frecuencia (MHz)`, tipo: "number", valor: m.frecuencia_mhz, minimo: 400, maximo: 10000, ayuda: "Ejemplo: 3200." }),
      marca: campo({ nombre: `${k}marca`, etiqueta: `${n} · marca`, valor: m.marca, requerido: false, maximo: 40 }),
    };
    Object.entries(c).forEach(([campoNombre, cp]) => cp.entrada.addEventListener("input", () => { m[campoNombre] = cp.valor(); actualizarResumen(); }));
    filas.ram[i] = c;
    return fila(n, Object.values(c).map((x) => x.raiz), "ram", i);
  }

  function filaDisco(i) {
    const d = est.discos[i], n = `Disco ${i + 1}`, k = `discos.${i}.`;
    const c = {
      tipo: campo({ nombre: `${k}tipo`, etiqueta: `${n} · tipo`, tipo: "select", valor: d.tipo, opciones: TIPOS_DISCO.map((t) => ({ valor: t, texto: t })) }),
      capacidad_gb: campo({ nombre: `${k}capacidad_gb`, etiqueta: `${n} · capacidad (GB)`, tipo: "number", valor: d.capacidad_gb, minimo: 8, maximo: 100000, ayuda: "1 TB = 1000 GB." }),
      modelo: campo({ nombre: `${k}modelo`, etiqueta: `${n} · marca o modelo`, valor: d.modelo, requerido: false, maximo: 60 }),
    };
    Object.entries(c).forEach(([campoNombre, cp]) => cp.entrada.addEventListener("input", () => { d[campoNombre] = cp.valor(); }));
    filas.discos[i] = c;
    const radio = h("input", { type: "radio", name: "disco-sistema", id: `sis-${i}`, checked: d.es_sistema, "aria-describedby": "error-sistema",
      onchange: () => { est.discos.forEach((x, j) => { x.es_sistema = j === i; }); } });
    if (i === 0) grupoSistema.entrada = radio;
    return fila(n, [...Object.values(c).map((x) => x.raiz), h("div", { class: "campo casilla" }, radio, h("label", { for: `sis-${i}` }, "Aquí está instalado el sistema operativo"))], "discos", i);
  }

  function fila(titulo, hijos, tipo, i) {
    const hay = est[tipo].length;
    return h("fieldset", { class: "modulo" }, h("legend", null, titulo), h("div", { class: "fila-campos" }, hijos),
      hay > 1 ? h("button", { type: "button", class: "boton sutil peligro", onclick: () => quitar(tipo, i) }, "Quitar", h("span", { class: "solo-lector" }, ` ${titulo}`)) : null);
  }

  function pintar(tipo) {
    filas[tipo] = [];
    cajas[tipo].replaceChildren(...est[tipo].map((_, i) => (tipo === "ram" ? filaRam(i) : filaDisco(i))));
    botones[tipo].disabled = est[tipo].length >= MAXIMO;
    if (tipo === "ram") actualizarResumen();
  }
  function agregar(tipo) {
    est[tipo].push(tipo === "ram" ? { ...ramVacia(), ...(est.ram.length ? { tipo: est.ram[0].tipo } : {}) } : discoVacio());
    pintar(tipo);
    const nuevo = cajas[tipo].lastElementChild.querySelector("input, select");
    nuevo.focus();
    anunciar(`${tipo === "ram" ? "Módulo" : "Disco"} ${est[tipo].length} agregado`);
  }
  function quitar(tipo, i) {
    est[tipo].splice(i, 1);
    if (tipo === "discos" && !est.discos.some((d) => d.es_sistema)) est.discos[0].es_sistema = true;
    pintar(tipo);
    botones[tipo].focus();
    anunciar(`${tipo === "ram" ? "Módulo" : "Disco"} quitado`);
  }
  botones.ram = h("button", { type: "button", class: "boton", onclick: () => agregar("ram") }, "Agregar otro módulo de RAM");
  botones.discos = h("button", { type: "button", class: "boton", onclick: () => agregar("discos") }, "Agregar otro disco");

  /* ---------- Detección automática ---------- */
  const estado = h("div", { class: "estado-deteccion", role: "status" });
  const resultado = h("textarea", { id: "resultado-ps", rows: 4, spellcheck: false, autocomplete: "off", class: "codigo", "aria-describedby": "ayuda-resultado" });
  const decir = (tipo, texto) => estado.replaceChildren(mensaje(tipo, texto));
  const poner = (cp, v) => { if (v !== "" && v != null) cp.entrada.value = v; };
  const llenarBasicos = (d) => {
    poner(basicos.sistema_operativo, d.so); poner(basicos.procesador, d.procesador); poner(basicos.cpu_nucleos, d.nucleos); poner(basicos.gpu, d.gpu);
    if (d.gpu_dedicada != null) basicos.gpu_dedicada.entrada.checked = d.gpu_dedicada;
  };
  let guion = null;
  const cargarGuion = async () => guion || (guion = await (await fetch("detectar.ps1")).text());

  const detectar = h("button", { type: "button", class: "boton", onclick: async () => {
    const d = await detectarNavegador();
    llenarBasicos({ so: d.so, gpu: d.gpu, gpu_dedicada: d.gpu_dedicada });
    const hallado = [d.so && `sistema ${d.so}`, d.gpu && `gráfica ${d.gpu}`, d.hilos && `${d.hilos} procesadores lógicos (los núcleos físicos suelen ser la mitad)`].filter(Boolean);
    decir(hallado.length ? "info" : "advertencia", hallado.length ? `El navegador detectó: ${hallado.join(", ")}. Revisa los datos. La memoria, los discos y el modelo del procesador solo se pueden leer con el comando de Windows.` : "El navegador no reveló ningún dato. Usa el comando de Windows o escribe los datos a mano.");
  } }, "Detectar con el navegador");
  const copiar = h("button", { type: "button", class: "boton", onclick: async () => {
    try { await navigator.clipboard.writeText(await cargarGuion()); decir("exito", "Comando copiado. Ábrelo en PowerShell (tecla Windows, escribe «PowerShell»), pégalo y pulsa Enter."); }
    catch { decir("advertencia", "No pudimos copiar automáticamente. Abre «Ver el comando», selecciónalo y cópialo."); }
  } }, "Copiar el comando");
  const pegar = h("button", { type: "button", class: "boton", onclick: async () => {
    try { resultado.value = await navigator.clipboard.readText(); resultado.focus(); }
    catch { decir("advertencia", "El navegador no dio permiso para leer el portapapeles. Pega el resultado en el cuadro con Ctrl+V."); }
  } }, "Pegar del portapapeles");
  const aplicar = h("button", { type: "button", class: "boton primario", onclick: () => {
    try {
      const d = interpretarJson(resultado.value);
      llenarBasicos(d);
      if (d.ram.length) est.ram = d.ram;
      if (d.discos.length) est.discos = d.discos;
      pintar("ram"); pintar("discos");
      decir(d.aviso ? "advertencia" : "exito", `Cargamos ${plural(d.ram.length, "módulo de RAM", "módulos de RAM")} y ${plural(d.discos.length, "disco", "discos")}. ${d.aviso || "Revisa los datos y pulsa Guardar."}`);
    } catch (e) { decir("error", e.message); resultado.focus(); }
  } }, "Aplicar resultado");
  const detectarPanel = h("section", { class: "tarjeta deteccion", "aria-labelledby": "det" },
    h("h2", { id: "det" }, "Detectar mis componentes"),
    h("p", null, "Ahorra tiempo: detectamos lo que se pueda y tú solo revisas. Nada se guarda hasta que pulses «Guardar»."),
    h("div", { class: "acciones" }, detectar),
    h("details", null, h("summary", null, "Detección completa en Windows (memoria y discos)"),
      h("ol", { class: "pasos" },
        h("li", null, "Pulsa «Copiar el comando». Es de solo lectura: no instala nada ni envía datos por Internet."),
        h("li", null, "Abre PowerShell: tecla Windows, escribe «PowerShell» y Enter. Pega el comando (clic derecho) y pulsa Enter."),
        h("li", null, "El resultado se copia solo. Vuelve aquí y pulsa «Pegar del portapapeles» (el navegador te pedirá permiso) o pégalo en el cuadro."),
        h("li", null, "Pulsa «Aplicar resultado» y revisa los datos.")),
      h("div", { class: "acciones" }, copiar, pegar),
      h("div", { class: "campo" }, h("label", { for: "resultado-ps" }, "Resultado del comando"), resultado, h("p", { id: "ayuda-resultado", class: "ayuda" }, "Si no usas Windows, escribe los datos a mano en el formulario.")),
      h("div", { class: "acciones" }, aplicar),
      h("details", { ontoggle: async (ev) => { const pre = ev.target.querySelector("pre"); if (ev.target.open && !pre.textContent) pre.textContent = await cargarGuion().catch(() => "No se pudo cargar el comando."); } },
        h("summary", null, "Ver el comando antes de usarlo"), h("pre", { class: "codigo", tabindex: "0", "aria-label": "Comando de PowerShell" }))),
    estado);

  /* ---------- Armado ---------- */
  const seccion = (id, titulo, ayuda, ...hijos) => h("section", { class: "bloque", "aria-labelledby": id }, h("h2", { id }, titulo), ayuda ? h("p", { class: "ayuda" }, ayuda) : null, ...hijos);
  const cuerpo = h("div", null,
    seccion("s-general", "Datos generales", null, h("div", { class: "fila-campos" }, ...["nombre", "sistema_operativo", "procesador", "cpu_nucleos"].map((k) => basicos[k].raiz))),
    seccion("s-gpu", "Tarjeta gráfica", null, h("div", { class: "fila-campos" }, basicos.gpu.raiz), basicos.gpu_dedicada.raiz),
    seccion("s-ram", "Memoria RAM", "Registra cada módulo instalado. Pueden ser de distinta marca o frecuencia si son del mismo tipo (por ejemplo, todos DDR4).", cajas.ram, botones.ram, resumenRam),
    seccion("s-disc", "Almacenamiento", "Registra cada disco o SSD del equipo y marca el que tiene el sistema operativo.", cajas.discos, errorSistema, botones.discos));
  pintar("ram"); pintar("discos");

  const form = formulario({
    campos: () => [...Object.values(basicos), ...filas.ram.flatMap((f) => Object.values(f)), ...filas.discos.flatMap((f) => Object.values(f)), grupoSistema], cuerpo,
    boton: "Guardar equipo", extra: h("a", { class: "boton", href: "#/equipos" }, "Cancelar"),
    enviar: async (d) => {
      const cuerpoApi = { nombre: d.nombre, sistema_operativo: d.sistema_operativo, procesador: d.procesador, cpu_nucleos: d.cpu_nucleos, gpu: d.gpu, gpu_dedicada: d.gpu_dedicada,
        ram: est.ram.map((m) => ({ capacidad_gb: Number(m.capacidad_gb), tipo: m.tipo, frecuencia_mhz: Number(m.frecuencia_mhz), marca: m.marca || null })),
        discos: est.discos.map((x) => ({ tipo: x.tipo, capacidad_gb: Number(x.capacidad_gb), modelo: x.modelo || null, es_sistema: x.es_sistema })) };
      await api(actual ? "put" : "post", actual ? `/api/equipos/${actual.id}` : "/api/equipos", cuerpoApi);
      avisar("exito", actual ? "Equipo actualizado." : "Equipo guardado. Ya puedes hacer un diagnóstico.");
      location.hash = "#/equipos";
    },
  });
  const titulo = actual ? `Editar ${actual.nombre}` : "Agregar equipo";
  return { titulo, nodo: h("div", { class: "formulario-equipo" }, h("h1", null, titulo),
    h("p", { class: "subtitulo" }, "Con estos datos el diagnóstico se ajusta a tu equipo: por ejemplo, tu memoria y tus discos cambian qué causas son más probables. Los campos con asterisco (*) son obligatorios."), detectarPanel, form) };
}
