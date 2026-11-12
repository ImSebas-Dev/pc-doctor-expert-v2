-- PC Doctor Expert v2 · PostgreSQL 16 (despliegue web)
-- Esquema kb: base central de conocimiento (4 tablas). Esquema tx: sistema transaccional.
CREATE SCHEMA IF NOT EXISTS kb;
CREATE SCHEMA IF NOT EXISTS tx;

-- ============ BASE DE CONOCIMIENTO (4 tablas) ============
CREATE TABLE kb.hipotesis (            -- fallas diagnosticables (P01–P25) y cierre P00
  id               smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  codigo           varchar(3)  NOT NULL UNIQUE CHECK (codigo ~ '^P[0-9]{2}$'),
  nombre           varchar(80) NOT NULL,
  categoria        varchar(40) NOT NULL CHECK (categoria IN ('Hardware','Rendimiento y software','Monitor, red y periféricos','Sin clasificar')),
  confianza        varchar(5)  NOT NULL CHECK (confianza IN ('alta','media','baja','n/a')),
  causa_probable   text        NOT NULL,
  recomendaciones  text[]      NOT NULL CHECK (cardinality(recomendaciones) >= 2),   -- RF-03
  fuente           text        NOT NULL,
  validada         boolean     NOT NULL DEFAULT false
);
CREATE TABLE kb.hecho (                -- síntomas, datos medidos y hechos derivados
  id               smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre           varchar(40) NOT NULL UNIQUE,
  tipo             varchar(10) NOT NULL CHECK (tipo IN ('dato','respuesta','derivado','equipo')),   -- 'equipo': hechos que salen de los componentes registrados
  descripcion      text        NOT NULL,
  unidad           varchar(5),
  valores          text[],              -- valores categóricos usados por las reglas
  nodo             varchar(4),          -- nodo del árbol (N0–N14) cuya pregunta lo obtiene
  pregunta         text,
  ambito           varchar(5) CHECK (ambito IN ('disco')),      -- la pregunta se hace por componente (p. ej., por cada disco)
  pregunta_varios  text                                          -- texto de la pregunta cuando el equipo tiene varios componentes de ese ámbito
);
CREATE TABLE kb.regla (                -- reglas SI–ENTONCES: diagnóstico (R-Pxx) y derivación (RH-xx)
  id               smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  codigo           varchar(8)  NOT NULL UNIQUE,
  tipo             varchar(11) NOT NULL CHECK (tipo IN ('diagnostico','derivacion')),
  conector         char(1)     NOT NULL DEFAULT 'Y' CHECK (conector IN ('Y','O')),
  hipotesis_id     smallint REFERENCES kb.hipotesis(id),       -- conclusión de una regla de diagnóstico
  hecho_id         smallint REFERENCES kb.hecho(id),           -- conclusión de una regla de derivación
  valor_conclusion text,
  confianza        varchar(5)  CHECK (confianza IN ('alta','media','baja','n/a')),
  ruta             text,
  texto            text        NOT NULL,
  fuente           text        NOT NULL,
  CONSTRAINT regla_conclusion_ck CHECK (
    (tipo = 'diagnostico' AND hipotesis_id IS NOT NULL AND hecho_id IS NULL AND valor_conclusion IS NULL) OR
    (tipo = 'derivacion'  AND hecho_id IS NOT NULL AND valor_conclusion IS NOT NULL AND hipotesis_id IS NULL))
);
CREATE TABLE kb.regla_condicion (      -- tabla puente regla–hecho (evita N:N): una fila por condición
  regla_id         smallint NOT NULL REFERENCES kb.regla(id) ON DELETE CASCADE,
  orden            smallint NOT NULL,
  hecho_id         smallint NOT NULL REFERENCES kb.hecho(id),
  operador         varchar(2) NOT NULL CHECK (operador IN ('=','>','<','>=','<=')),
  valor            text NOT NULL,
  PRIMARY KEY (regla_id, orden)
);
CREATE INDEX ix_regla_hipotesis ON kb.regla(hipotesis_id);
CREATE INDEX ix_cond_hecho ON kb.regla_condicion(hecho_id);

-- ============ SISTEMA TRANSACCIONAL ============
CREATE TABLE tx.rol (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre varchar(15) NOT NULL UNIQUE CHECK (nombre IN ('usuario','administrador')),   -- RF-01
  descripcion text NOT NULL
);
CREATE TABLE tx.usuario (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre varchar(80) NOT NULL,
  correo varchar(120) NOT NULL UNIQUE CHECK (correo ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  clave_hash text NOT NULL,
  rol_id smallint NOT NULL REFERENCES tx.rol(id),
  activo boolean NOT NULL DEFAULT true,
  creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tx.equipo (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id integer NOT NULL REFERENCES tx.usuario(id) ON DELETE CASCADE,
  nombre varchar(60) NOT NULL,
  sistema_operativo varchar(60) NOT NULL,
  procesador varchar(80) NOT NULL, cpu_nucleos smallint NOT NULL CHECK (cpu_nucleos BETWEEN 1 AND 128),
  gpu varchar(80) NOT NULL, gpu_dedicada boolean NOT NULL,
  UNIQUE (usuario_id, nombre)                                                          -- RF-04
);
CREATE TABLE tx.equipo_ram (            -- un registro por módulo de memoria instalado
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  equipo_id integer NOT NULL REFERENCES tx.equipo(id) ON DELETE CASCADE,
  capacidad_gb smallint NOT NULL CHECK (capacidad_gb BETWEEN 1 AND 256),
  tipo varchar(6) NOT NULL CHECK (tipo IN ('DDR3','DDR4','DDR5','LPDDR4','LPDDR5')),
  frecuencia_mhz smallint NOT NULL CHECK (frecuencia_mhz BETWEEN 400 AND 10000),
  marca varchar(40)
);
CREATE INDEX ix_ram_equipo ON tx.equipo_ram(equipo_id);
CREATE TABLE tx.equipo_disco (          -- un registro por unidad de almacenamiento
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  equipo_id integer NOT NULL REFERENCES tx.equipo(id) ON DELETE CASCADE,
  tipo varchar(8) NOT NULL CHECK (tipo IN ('SSD NVMe','SSD SATA','HDD')),
  capacidad_gb integer NOT NULL CHECK (capacidad_gb BETWEEN 8 AND 100000),
  modelo varchar(60),
  es_sistema boolean NOT NULL DEFAULT false
);
CREATE INDEX ix_disco_equipo ON tx.equipo_disco(equipo_id);
CREATE UNIQUE INDEX ux_un_disco_sistema ON tx.equipo_disco(equipo_id) WHERE es_sistema;
CREATE TABLE tx.diagnostico (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  equipo_id integer NOT NULL REFERENCES tx.equipo(id) ON DELETE CASCADE,
  creado_en timestamptz NOT NULL DEFAULT now(),
  estado varchar(11) NOT NULL DEFAULT 'en_curso' CHECK (estado IN ('en_curso','finalizado'))
);
CREATE TABLE tx.diagnostico_hecho (    -- evidencias aportadas por el usuario
  diagnostico_id integer NOT NULL REFERENCES tx.diagnostico(id) ON DELETE CASCADE,
  hecho_id smallint NOT NULL REFERENCES kb.hecho(id),
  valor text NOT NULL,
  origen varchar(8) NOT NULL CHECK (origen IN ('usuario','derivado','equipo')),   -- quién aportó el hecho: la persona, una deducción o los componentes
  detalle text,                                   -- p. ej., qué discos tienen el problema (texto al momento del diagnóstico)
  PRIMARY KEY (diagnostico_id, hecho_id)
);
CREATE TABLE tx.diagnostico_hipotesis ( -- resultado: las 5 hipótesis con su peso (RF-02)
  diagnostico_id integer NOT NULL REFERENCES tx.diagnostico(id) ON DELETE CASCADE,
  hipotesis_id smallint NOT NULL REFERENCES kb.hipotesis(id),
  coincidencia numeric(5,2) NOT NULL CHECK (coincidencia BETWEEN 0 AND 100),
  es_principal boolean NOT NULL DEFAULT false,
  PRIMARY KEY (diagnostico_id, hipotesis_id)
);
CREATE UNIQUE INDEX ux_un_principal ON tx.diagnostico_hipotesis(diagnostico_id) WHERE es_principal;
CREATE TABLE tx.diagnostico_regla (     -- reglas activadas = explicación (RF-03)
  diagnostico_id integer NOT NULL REFERENCES tx.diagnostico(id) ON DELETE CASCADE,
  regla_id smallint NOT NULL REFERENCES kb.regla(id),
  coincidencia numeric(5,2) NOT NULL,
  PRIMARY KEY (diagnostico_id, regla_id)
);
CREATE TABLE tx.caso_prueba (
  id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre varchar(80) NOT NULL UNIQUE,
  hipotesis_esperada_id smallint NOT NULL REFERENCES kb.hipotesis(id)
);
CREATE TABLE tx.caso_prueba_hecho (
  caso_id smallint NOT NULL REFERENCES tx.caso_prueba(id) ON DELETE CASCADE,
  hecho_id smallint NOT NULL REFERENCES kb.hecho(id),
  valor text NOT NULL,
  PRIMARY KEY (caso_id, hecho_id)
);
CREATE TABLE tx.ejecucion_prueba (
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  caso_id smallint NOT NULL REFERENCES tx.caso_prueba(id) ON DELETE CASCADE,
  usuario_id integer NOT NULL REFERENCES tx.usuario(id),
  hipotesis_obtenida_id smallint NOT NULL REFERENCES kb.hipotesis(id),
  aprobado boolean NOT NULL,
  ejecutado_en timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tx.auditoria_acceso (       -- RF-01: intentos denegados
  id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id integer REFERENCES tx.usuario(id),
  funcion varchar(60) NOT NULL,
  resultado varchar(10) NOT NULL CHECK (resultado IN ('permitido','denegado')),
  fecha timestamptz NOT NULL DEFAULT now()
);
