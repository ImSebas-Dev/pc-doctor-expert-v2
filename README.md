# PC Doctor Expert v2 · sistema web

Sistema experto para diagnosticar problemas frecuentes en computadores personales. Motor de inferencia propio (reglas SI–ENTONCES + pesos probabilísticos) sobre una base de conocimiento en PostgreSQL, con interfaz web en el lenguaje de diseño Fluent.

## Novedades de la versión 2

- **Componentes que sí cuentan en el diagnóstico.** Cada equipo registra su procesador (núcleos), su tarjeta gráfica (dedicada o integrada), sus **módulos de RAM uno por uno** (capacidad, tipo, frecuencia y marca; pueden ser de distinta marca o frecuencia si son del mismo tipo) y **todos sus discos** (tipo, capacidad, cuál tiene el sistema). El motor los recibe como evidencia (`SesionDiagnostico.registrar_equipo`) y reglas nuevas (RH-14 a RH-16, P26 a P30) los usan: con poca memoria sube «RAM insuficiente», con mucha sube «programas consumiendo memoria», un HDD como disco del sistema pesa en la lentitud al iniciar, etc.
- **Varios discos.** Las preguntas sobre espacio libre y errores se hacen por disco y el resultado dice cuáles discos están afectados.
- **Compatibilidad de RAM.** No se aceptan módulos de distinto tipo (DDR4 con DDR5); frecuencias o capacidades distintas se aceptan con un aviso (funcionan a la velocidad del más lento).
- **Detección automática.** El navegador aporta lo que permite sin permisos (sistema, gráfica). Para memoria y discos hay un comando de PowerShell de solo lectura (`static/detectar.ps1`) cuyo resultado se pega en el formulario; nada se guarda hasta pulsar «Guardar».
- **Explicaciones sin jerga** y diseño adaptado a cualquier celular (ver `tests/` y las pruebas de interfaz).

## Tecnología (sin dependencias innecesarias)

| Capa | Tecnología |
|---|---|
| Servidor | Python 3.12, Flask, gunicorn (3 paquetes: `requirements.txt`) |
| Base de datos | PostgreSQL (psycopg 3) |
| Interfaz | HTML, CSS y JavaScript nativos (módulos ES). Sin frameworks, sin CDN, sin fuentes externas |

## Estructura

```
app.py                  crea la aplicación (cabeceras, errores, rutas)
sistema/
  motor/                motor de inferencia (entidades, derivador, estimador, selector, sesión)
  rutas/                auth, equipos, diagnostico, admin (API JSON)
  seguridad.py          sesión, CSRF, control de acceso, límite de intentos, cabeceras
  claves.py             hash scrypt y política de contraseñas
  validacion.py         validación estricta de entrada
  conocimiento.py       instantánea en memoria de la base de conocimiento
  instalador.py         crea esquema, conocimiento y primer administrador (idempotente)
sql/                    esquema kb (4 tablas) + tx (11 tablas), conocimiento, roles y casos de prueba
static/                 interfaz (css/fluent.css, js/vistas/*)
tests/                  pruebas de API y seguridad
render.yaml             despliegue gratuito en Render
```

## Ejecutar en local

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://usuario:clave@localhost:5432/pcdoctor"
export ADMIN_CORREO="tu@correo.com" ADMIN_CLAVE="una-clave-larga-y-unica"
python -m sistema.instalador          # crea tablas, conocimiento y administrador
gunicorn app:app --workers 1 --threads 4
python -m unittest tests.test_api     # pruebas (usan la misma base)
```

Variables: `DATABASE_URL` (obligatoria), `SECRET_KEY` (obligatoria en producción; en local se genera sola), `PCDOCTOR_ENV=production` (activa cookies seguras, HSTS e instalación automática), `ADMIN_CORREO` y `ADMIN_CLAVE` (solo para crear el primer administrador).

Se usa **un solo proceso** de gunicorn: el límite de intentos de inicio de sesión y la instantánea del conocimiento viven en memoria.

## Seguridad (OWASP Top 10:2021)

| Riesgo | Control |
|---|---|
| A01 Control de acceso | Denegar por defecto: `@requiere_sesion` / `@requiere_admin`; cada consulta filtra por el dueño (`WHERE usuario_id = …`), por lo que un usuario recibe 404 ante datos ajenos; un administrador no puede quitarse su rol. |
| A02 Fallos criptográficos | Contraseñas con scrypt y sal única; cookie `__Host-` con `Secure`, `HttpOnly`, `SameSite=Lax`; HSTS; secretos solo en variables de entorno. |
| A03 Inyección | Solo consultas parametrizadas; validación de tipo, longitud, formato y caracteres de control; la interfaz construye el DOM con `textContent` (nunca `innerHTML`) y la CSP prohíbe scripts y estilos en línea. |
| A04 Diseño inseguro | Límites de negocio en el servidor (máx. 10 respuestas, valores permitidos por hecho), cuerpo máximo de 32 KB, límite de registros por IP. |
| A05 Configuración | Cabeceras CSP estricta, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, `no-store` en la API; errores genéricos sin trazas. |
| A06 Componentes vulnerables | Solo 3 dependencias, versiones fijas; `pip-audit` sin vulnerabilidades conocidas. |
| A07 Autenticación | Política de contraseña (10–128, sin claves comunes), mensaje único «correo o contraseña incorrectos», verificación en tiempo constante, bloqueo temporal (5 fallos por correo y 20 por IP cada 15 min), sesión nueva al ingresar, vencimiento por inactividad (30 min) y absoluto (8 h), CSRF en toda escritura. |
| A08 Integridad | Cookie de sesión firmada; sin deserialización de datos de usuario; el servidor exige `Content-Type: application/json` y token CSRF. |
| A09 Registro y monitoreo | `tx.auditoria_acceso` registra ingresos, intentos denegados y cambios de administración; los errores inesperados quedan en el registro del servicio. |
| A10 SSRF | El servidor no realiza solicitudes salientes a partir de datos del usuario. |

## Accesibilidad (WCAG 2.2 AA)

Estructura semántica y puntos de referencia (`header`, `nav`, `main`, `footer`), enlace «Saltar al contenido», un `h1` por página con foco y título actualizados en cada navegación, etiquetas y ayudas asociadas a cada campo, resumen de errores enfocable, objetivos táctiles de al menos 44 px (2.5.8), foco visible de doble anillo (2.4.7, 2.4.11), contraste verificado en modo claro y oscuro, reflujo a 320 px (1.4.10), sin dependencia del color (el estado siempre lleva texto), diálogos nativos con foco atrapado y devuelto, `autocomplete` y pegado permitido en contraseñas (3.3.7, 3.3.8), ayuda en el mismo lugar en todas las páginas (3.2.6), respeto de `prefers-reduced-motion`, `prefers-color-scheme` y `forced-colors`. Verificado con axe-core (reglas WCAG 2.0/2.1/2.2 A y AA) en todas las vistas, claro y oscuro: 0 incumplimientos.
