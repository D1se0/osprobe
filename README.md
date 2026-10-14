# OSProbe 🛰️

**Fingerprint del sistema operativo remoto mediante técnicas HTTP puras — sin tocar el kernel, sin sockets raros, sólo peticiones que cualquier navegador haría.**

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-6%2F6%20%E2%9C%94-brightgreen) ![Code style](https://img.shields.io/badge/style-rich%20terminal-purple)

```text
  ___  ____  ____    _  _____  ____     🐧  Linux  ▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯  83.3%
 / _ \|  _ \|  _ \  / \|_   _|/ ___|    🪟 Windows ▯▯▯▯▯▯▯▯▯▯▯▯▯  16.7%
| | | | |_) | |_) || |> || |  \___ \
| |_| |  __/|  __/ | |> || | _ ___) |   → Veredicto: LINUX (confianza 100%)
 \___/|_|   |_|    |_|\__/|_|(_)____/
```

---

## ⚠️ Aviso legal

OSProbe es una herramienta de **reconocimiento pasivo de huella** para auditorías autorizadas. Usarla contra sistemas que no te pertenecen o sin permiso escrito **puede ser ilegal** en tu jurisdicción (p. ej. CFAA en EE. UU., art. 197 CP en España). Úsala bajo tu propio riesgo y siempre con autorización. El código se entrega tal cual bajo licencia MIT.

---

## 🧠 La idea (y por qué funciona)

Piensa en la URL `http://victima/images`. Si el directorio existe, el servidor responde algo (200, 301, 403...). Ahora juega con las mayúsculas:

| Petición | **Linux** (ext4, case-sensitive) | **Windows/NTFS** (case-insensitive) |
|---|---|---|
| `/images` | ✅ 200 | ✅ 200 |
| `/Images` | ❌ 404 | ✅ 200 |
| `/IMAGES` | ❌ 404 | ✅ 200 |
| `/ImageS` | ❌ 404 | ✅ 200 |

**Windows (NTFS) es case-insensitive**: no distingue `images` de `IMAGES`; ambos resuelven al mismo directorio y la petición sigue cargando. **Linux (ext4/xfs/btrfs) es case-sensitive**: `Images` no existe, manda 404. Es una técnica clásica (circulaba en foros de seguridad hace ~dos décadas sobre IIS 5/6) y sigue siendo útil hoy, porque no depende del software del servidor sino del sistema de ficheros del host.

OSProbe corre esta técnica como probe estrella **y cuatro vectores más**, para que un 404 perdido o una cabecera pelando no te cuelen un veredicto equivocado.

---

## 🚀 Instalación

```bash
git clone https://github.com/D1se0/osprobe.git
cd osprobe
pip install -r requirements.txt        # o: pip install .
python3 -m osprobe --version
```

**Dependencias:** `rich` (UI/animaciones), `aiohttp` (HTTP async). Eso es todo; ninguna "mala magia".

## 🧪 Sandbox inmediato (sin Windows necesario)

```bash
python3 -m osprobe --demo
```

Levanta **dos servidores simulados en localhost** — uno especializado para el comportamiento de Linux/Apache y otro que se hace pasar por IIS/Windows — y corre el escaneo completo contra ambos. Verás cómo distingue cada simulador sin salir de tu máquina. Es también la forma recomendada de ver las animaciones.

## 🎯 Uso real

```bash
# Escaneo básico: asume que la ruta de la URL es la semilla
python3 -m osprobe http://192.168.1.50/images

# La semilla ideal es una ruta que SEPA que existe; la auto-detecta de la URL si no
python3 -m osprobe ejemplo.com -p static/resources

# Modo profundo: variantes extra de casing (más peticiones, más evidencia)
python3 -m osprobe https://target.com/web --deep

# Toda la artillería: delay + export
python3 -m osprobe http://10.0.0.5/admin -d 0.5 --export both
```

### Salida típica

```text
✔ case-sensitivity      · confirmado
✔ header-signatures     · confirmado
✔ finger-404            · confirmado
✔ backslash-separator   · sospecha
╭──────────────────────────── Veredicto ────────────────────────────╮
│  🐧  Linux · confianza alta 100%                                  │
│     Linux    ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯  83.3%                     │
│     Windows ▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▯▮  16.7%                     │
╰──────────────────────────────────────────────────────────────────╯
```

---

## 📜 Toda la lista de parámetros

| Flag | Default | Descripción |
|---|---|---|
| `objetivo` (posicional) | — | URL (`https://host/ruta`, `host`, `host:puerto`). El esquema `http` se asume si falta; rutas que ya llevan `https://` se respetan. |
| `-p`, `--path` | ruta de la URL | **Ruta semilla**: la que tú confirmas que existe (p.ej. `images`). Es el punto de partido del probe case-sensitivity; si no existe, ese probe se abstiene pero el resto siguen trabajando. |
| `-t`, `--timeout` | `8.0` | Timeout total por petición HTTP, en segundos. Valores bajos (`2-3`) para redes lentas del mismo segmento; sube hasta `15` si estás detrás de un proxy lento. |
| `-r`, `--retries` | `2` | Reintentos en errores de red o timeout. Entre intentos espera una estrategia exponencial: `0.15 * 2^n` segundos. |
| `-d`, `--delay` | `0.0` | Retardo máximo (aleatorio, 50-100 % del valor) entre peticiones. Considera usar `0.3-1.0` contra servidores en producción: evita rate-limiting sin ir lento en exceso. |
| `-x`, `--proxy` | ninguno | Enruta **todas** las peticiones por este proxy. Acepta `http://`, `https://` y `socks5://` (el último requiere `pip install aiohttp-socks`). Ideal con Burp/ZAP/Tor (`--proxy socks5://127.0.0.1:9050`). |
| `-k`, `--insecure` | off | No validar el certificado TLS (equivalente a `curl -k`). Útil contra self-signed en laboratorio. |
| `-a`, `--user-agent` | `OSProbe/1.0` | UA personalizado. Cámbialo si quieres mimetizarte con el tráfico normal del navegador. |
| `--deep` | off | Modo agresivo: añade variantes camelCase por fragmento y rutas transversales con backslash (`%2e%2e`). Más evidencia, más requests, más ruido. |
| `--export` | ninguno | Exporta el informe como `json`, `md`, `txt` o `both` (`.md` + `.json`). Se escribe a `osprobe-informe.{json,md,txt}`. |
| `--export-dir` | `.` | Carpeta de destino de los informes (se crea si no existe). |
| `--no-color` | off | Fuerza desactivar el color ANSI (útil al redirigir saída a un fichero). |
| `-q`, `--quiet` | off | Veredicto y errores solamente. Sin banner, sin animaciones, sin tablas — para pipelines/Cron. |
| `--demo` | off | Corra dos servidores mock de localhost (Linux e IIS-Windows) y escanea ambos: importante para demos/labs. |
| `--version` | — | Muestra la versión y se va. |

**Códigos de salida:** `0` éxito · `2` objetivo inválido · `3` fallo de red · `130` interrumpido por Ctrl-C.

---

## 🔬 Los cuatro vectores de detección

OSProbe nunca confía en una sola señal: corre 4 vectores y **pensa un veredicto de consenso ponderado**.

### 1. `case-sensitivity` (peso 40 — la estrella) 🌟
Alterna las mayúsculas de la ruta semilla (`images` → `Images`, `IMAGES`, `imageS`, y con `--deep` camelCase tipo `iMaGeS`). Si el 100 % de las variantes dan `404`, es FS **case-sensitive → Linux**. Si el 100 % siguen respondiendo algo (≠404/410), es FS **case-insensitive → Windows**. Si queda mezcla (20-80 %), existe un proxy o reescritura delante y sólo se emite sospecha, no certeza — humildad = calidad.

### 2. `header-signatures` (peso 25) 🧾
Lee todas las cabeceras de la respuesta raíz contra **~14 firmas ponderadas**: `Server: Microsoft-IIS`, `X-AspNet-Version`, `X-Powered-By: ASP.NET` → Windows; `Apache`, `nginx`, `OpenResty`, `Unix`, `PHP` (peso pequeño: PHP también corre en Windows) → Linux. ⚠️ Las cabeceras se pueden _ocultar_ desde el servidor (`ServerTokens ProductOnly` en Apache, etc.), por eso son un indicador, no un veredicto.

### 3. `finger-404` (peso 15) 💀
Pide **tres** rutas aleatorias inexistentes (`/osprobe-not-found-a1c9b2f3e4d5...html`) y agrega las huellas del cuerpo y las cabeceras de cada 404. «The resource you are looking for» es el **mensaje nativo de IIS**; el HTML amarillo de «Server Error in '/' Application» es ASP.NET puro; «Not Found» + «Apache» apunta Linux. Tres peticiones en lugar de una amortiguan el riesgo de que el admin defina una 404 personalizada que confunda al fingerprint.

### 4. `backslash-separator` (peso 20, «sospecha») 🔙
Win32 (y el IIS/ASP.NET que corre sobre él) normaliza el backslash como separador de rutas: pediremos `\images` y compararemos con `/images`. El FS de Linux (ext4) es tan estricto que esa barra invertida es parte del nombre y devuelve 404 — pero OSProbe emite siempre «sospecha», nunca «confirmado», porque un WAF puede bloquear todas las peticiones con backslash (y confundirnos).
### 🧮 Veredicto por consenso

```text
score_OS = (Σ votos_OS × peso_probe) / (Σ pesos de los probes votantes)
```

Cada probe vota `0.0` a `1.0` por clase. La **confianza final** es la proporción de peso de probes que de verdad votó (un probe cuya semilla resultó muerta no vota — no se suma). Ejemplo: contra el mock IIS, `case 100%·40 + headers 100%·25 + finger404·15 + backslash 0.8·20` → score Windows 96.4 / Linux 0 → 🪟 con confianza 100 %.

---

## 🧱 Arquitectura (cómo está montado por dentro)

```text
osprobe/
├── cli.py            argparse → crea cena UI + ScanSession + asyncio.run
├── engine.py         OSProbeEngine: corre probes, agrega votos → FinalVerdict
├── http_client.py    aiohttp: session keep-alive, reintentos, proxy, timeout
├── models.py         Target / ProbeResult / FinalVerdict  (almacen de datos)
├── probes/
│   ├── base.py       clase Probe abstracta + ProbeContext común
│   ├── case_probe.py           🌟 técnica estrella de casing
│   ├── headers_probe.py        🧾 firmas de cabeceras
│   ├── notfound_probe.py       💀 fingerprint del 404
│   └── backslash_probe.py      🔙 separador backslash
├── ui.py             Rich: banner animado, medidor vivo, tablas
├── report.py         export JSON / Markdown
└── demo.py           servidores simulados Linux + IIS para el sandbox
```

El pipeline es async: `asyncio.run` → `ScanSession` (envuelve `HttpClient` aiohttp con reintentos) → `ProbeContext` → cada `Probe.run(ctx)` devuelve `ProbeResult.votes` → el motor pondera y produce `FinalVerdict`, que `UI.render_verdict` pinta (o `report.py` exporta).

Documentación detallada:

* [`docs/USAGE.md`](docs/USAGE.md) — todos los parámetros, ejemplos y casos de borde.
* [`docs/PROBES.md`](docs/PROBES.md) — cómo funciona cada probe petición-a-petición (incluye qué petición exacta se manda).
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — el flujo completo, decisiones de diseño y cómo extender un nuevo probe.

---

## 🧪 Tests

```bash
python3 -m pytest tests/ -v
```

Los tests levantan los dos simuladores en puertos locales aleatorios y verifican que el motor vote correctamente Linux **y** Windows (veredicto, confianza, votos de cada probe). También comprueban que una semilla inexistente causa abstención (humildad del motor) y la normalización de `Target`.

## ✨ Thing que le hacen estar  maravillosa

* 🎨 Banner ASCII con gradiente HSL animado + efecto typewriter
* ⏳ Spinner Rich con barra de progreso viva mientras escanea
* 📊 Medidor animado Linux vs Windows con barra ▮▮▯
* 🎯 Panel de veredicto con emoji del OS ganador (🐧 / 🪟)
* 📝 Tabla detallada de evidencia por probe (si te importa el cómo)
* 📤 Export JSON + Markdown para adjuntar en reportes
* 🧪 Modo demo con servidores simulados integrados — sandbox rock solid
* 🔇 `--quiet` y `NO_COLOR` reales — para integrarlo en pipelines

---

## 🛣️ Roadmap

* [ ] Detección vía **formato de ETag** (IIS usa un formato distintivo: fileIndex + timestamp NTFS).
* [ ] Análisis de TTL y `Server:` de las respuestas caché (CDN delante).
* [ ] Detectar sistemas espejo (reverse proxy en la cúspide del stack).
* [ ] `-f lista_targets.txt` para escaneo en lote + export CSV.

---

**Licencia:** MIT · **Autor:** D1se0 · *Hecho con 🩸, 💦 y muchas peticiones 404.*
