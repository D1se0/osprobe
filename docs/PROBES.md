# 🔬 Anatomía de los probes de OSProbe

Documento técnico: qué petición HTTP exacta manda cada probe, qué
compara, cómo vota y qué fallos gestiona. Los pesos del consenso los
fijamos según el **poder discriminatorio real** de cada técnica
(case-sensitivity manda: 40; headers 25; backslash 20; finger-404 15).

Todos los probes comparten `ProbeContext` (`probes/base.py`):

| Campo | Significado |
|---|---|
| `client` | `HttpClient` aiohttp ya configurado (UA, timeout, proxy, delay) |
| `target` | `Target` normalizado; `target.origin` = `http://host:puerto` |
| `seed_path` | ruta confirmada existente (o path de la URL) |
| `delay` | rate-limit del CLI |
| `deep` | modo agresivo |

Cada `Probe.run(ctx)` → `ProbeResult(probe_name, certainty, votes,
evidence, error, elapsed)`. Los `votes` son `{OSType: 0.0-1.0}` y la
suma ≤ 1. Abstención = `ProbeCertainty.NO_VOTE` + `votes={}`.

---

## 1. `case-sensitivity` — pesa 40 (`probes/case_probe.py`)

### Protocolo exacto
1. `GET {origin}/{seed}` → requiere ≠ 404/410; si sale un ghost,
   abstención con `error` explicativo (ver `evidence`).
2. Genera variantes **mutando un fragmento por vez** con
   `case_variants(seed, deep)`:
   - `images` → `Images`, `IMAGES`, `imageS`
     (primera capital, todo mayúsculas, última capital).
   - Multi-fragmento `a/b`: muta `a/b → A/b` y `a/b → a/B`.
   - `deep`: extra `iMaGeS` (camel intercalado) por si el
     middleware "normaliza" sólo la primera letra.
3. `GET {origin}/{variante}` por cada variante (delay entre peticiones).
4. Clasificación: `is_not_found = status in (404, 410)`.

### Interpretación
| Resultado | Certeza | Votos |
|---|---|---|
| 0/12 variantes ª existen | CONFIRMADO | `Linux: 1.0` |
| todas «existen» | CONFIRMADO | `Windows: 1.0` |
| ≥ 80 % o ≤ 20 % | SOSPECHA | `dominante: 0.55` |
| mezcla (20–80 %) | SOSPECHA | nada — reconocemos los grises |

Por qué se da la clasificación: NTFS resuelve `Images == images`
gracias a sus APIs Win32 (el IIS simplemente traduce la ruta), mientras
que los FS POSIX retornan `ENOENT` — el servidor responde 404 (o
403 según el handler) para la variante mutada.

### Modos de fallo controlados
- Semilla fantasma → abstención + mensaje accionable (`--seed-path`).
- Proxy que devuelve 200 para TODO → el finger-404 no encontrará
  404s y avisará; el case-sensitivity votaría CONFIRMADO como Windows
  (falso positivo conocido). Lee siempre la tabla de evidencia del
  informe para detectar este caso.

---

## 2. `header-signatures` — pesa 25 `probes/headers_probe.py`

- > `GET {origin}/` sin redirecciones (`follow_redirects=False`).
- Búsqueda de **patrones ponderados** en `{header}: {value}` (un
  mismo patrón no vale lo mismo si el proxy lo inserta o el server).

| Firma | OS | Peso |
|---|---|---|
| `microsoft-iis` | Windows | 1.00 |
| `x-aspnet-version` | Windows | 1.00 |
| `x-powered-by: asp.net` | Windows | 0.90 |
| `x-aspnetmvc-version` | Windows | 0.90 |
| `windows-azure` | Windows | 0.80 |
| `frontpage` | Windows | 0.90 |
| `x-recursive` (vía traza Azure) | Windows | 0.30 |
| `apache` | Linux | 0.70 |
| `nginx` | Linux | 0.55 |
| `litespeed` / `openresty` | Linux | 0.60/0.50 |
| `unix` | Linux | 0.60 |
| `php` | Linux | 0.35 (también corre en Win) |
| `express` (node) | Linux | 0.45 |

- La clase ganadora se normaliza a `1.0` y marca CONFIRMADO si
  acumula > 1 punto; si no, se emite SOSPECHA. Así, un `nginx`
  aislado vota menos que un `Microsoft-IIS/10.0 + X-AspNet`.

---

## 3. `finger-404` — pesa 15 `probes/notfound_probe.py`

- Envía **3 peticiones** contra `/osprobe-not-found-{16 alfanum aleatorios}.html`.
  El token aleatorio evita cacheos del CDN y de proxies intermedios.
- Por cada 404, busca en `cuerpo + headers` (todo en minúsculas):

| Firma | OS | Peso | Qué es realmente |
|---|---|---|---|
| `the resource you are looking for` | Windows | 0.90 | Mensaje nativo IIS 7+ |
| `server error in '/' application` | Windows | 1.00 | Pantalla amarilla ASP.NET |
| `runtime error` | Windows | 0.55 | Error runtime ASP.NET |
| `httperror` | Windows | 0.50 | Handlers MS |
| `a 404 error was encountered` | Linux | 0.60 | Handler de error estilo unix |
| `apache` | Linux | 0.50 | La 404 firma Apache |
| `nginx` | Linux | 0.45 | 404 nginx (*debil* del host) |
| + cabeceras `microsoft-iis / x-aspnet-version / x-powered-by` | | | |

- El ratio de puntos decide: `CONFIRMADO` si ≥ 0.9, `SOSPECHA` en
  medio (quizá el admin definió una 404 personalizada que mezcla
  frases). Las 3 peticiones redundantes amortiguan el ruido.

---

## 4. `backslash-separator` — pesa 20 `probes/backslash_probe.py`

- Baseline: `GET {seed}` (≠404, igual que case-sensitivity).
- Variantes normal: `{seed}` con `\` en vez de `/`.
- Variantes `--deep`: además `\{seed}` y `{seed}\%2e%2e\...`.
- Interpretación: Win32 normaliza la ruta (para NTFS, `c:\dir` y
  `c:/dir` son lo mismo) y el IIS la resuelve igual; un FS POSIX
  considera el `\` parte del nombre del fichero → 404.
- **Siempre «sospecha»** (voto 0.8 hacia Windows / 0.6 hacia Linux)
  porque un WAF puede bloquear el backslash en bloque y confundirnos
  con un falso 404. Por eso su peso (20) es intermedio.

---

## Cómo extender un nuevo probe

1. Crea `probes/mi_probe.py` y hereda de `Probe` (`probes/base.py`).
2. Define `name`, `weight`, `description`.
3. Implementa `async run(ctx) -> ProbeResult`:
   - usa `ctx.client.send()`/`ctx.client.path_exists()` — no abras
     sockets a mano ni toques aiohttp distinto;
   - vota con `ProbeCertainty.CONFIRMED` sólo si la técnica
     discrimina el OS independientemente de proxies/WAF delante; si
     no, `SUSPICION`.
4. Registra la clase en `probes/__init__.py → ALL_PROBES`.
5. Añade un caso de test en `tests/` contra los mocks de `demo.py`.
6. Ajusta el peso si tu técnica es más discriminante — y rebaja los
   pesos de otros probes si son redundantes con el tuyo.
