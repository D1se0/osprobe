# 🏗️ Arquitectura interna de OSProbe

Documento dirigido a quien quiera **entender el flujo completo por
dentro** o contribuir código. La regla de oro: los probes no tocan
HTTP a mano, el motor no sabe de detalles HTTP, y la UI no sabe de OS.

---

## 1. Diagrama de flujo de un escaneo

```text
CLI (cli.py)
  ├── parse_args (argparse) ── opciones del usuario
  ├── UI() ─────────────── banner animado, progreso, tablas
  ├── [opcional] --demo → demo.start_fake_server() x2
  └── async_main()
        ├── Target(url)              normaliza host/puerto/ruta
        ├── ScanSession                 envuelve HttpClient + opciones
        ├── OSProbeEngine.run(session, on_event)
        │     ├── ProbeContext(client, target, seed, delay, deep)
        │     ├── for probe in ALL_PROBES:
        │     │     ├── events "probe_inicio"
        │     │     ├── await probe.run(ctx) -> ProbeResult(votes)
        │     │     └── events "probe_fin"
        │     ├── agregación ponderada → score_linux / score_windows
        │     ├── confianza = peso votado / peso total
        │     └── FinalVerdict
        ├── UI.render_verdict(verdict)  medidor animado + tabla evidencia
        └── report.to_json / to_markdown  (si --export)
```

## 2. Los actores, módulo a módulo

### `osprobe/models.py` — el almacen de datos
- **`Target`**: normaliza URL con `urllib.parse`; expone `scheme`,
  `host`, `port`, `origin` (sin ruta) y `base_path` (sin esquema).
  Rechaza esquemas != http/https con `ValueError`.
- **`OSType`** (enum): `LINUX` / `WINDOWS` / `UNKNOWN`.
- **`ProbeCertainty`** enum: `CONFIRMED` / `SUSPICION` / `NO_VOTE`.
- **`ProbeResult`**: el paquete estándar que todo probe produce.
- **`FinalVerdict`**: veredicto agregado + lista de `ProbeResult` +
  marca temporal.

### `osprobe/http_client.py` — la puerta HTTP
- `HttpClient` envuelve `aiohttp.ClientSession` (keep-alive por
  escaneo entero, un solo pool TCP).
- `send(RequestSpec)`: retries con backoff `0.15*2^n` (cap 1.5s),
  timeout total configurable, proxy global y semáforo de 8 para no
  saturar al objetivo por accidente.
- `path_exists(base, path)`: azúcar sintáctico del probe para pedir
  una ruta y devolver `ResponseSnap` (fotografía inmutable: status,
  headers, cuerpo truncado a 2KB, elapsed). El cuerpo truncado basta:
  las firmas 404 caben en 2KB y no queremos descargar el banner de
  3MB del WordPress de tu víctimas.
- `ResponseSnap.is_not_found`: abstrae `status in (404, 410)` para
  que los probes no repitan la misma magia.

### `osprobe/probes/` — los experimentos
- `base.Probe` (ABC): obliga a `run(ctx)`; aporta `make_result`,
  `ProbeContext` y helpers. Regla: **un probe que explota debe
  devolver el error en `ProbeResult`, nunca relanzar la excepción**.
- `ProbeContext`: agrupa `client + target + delay + deep + seed_path`
  y da `random_notfound_path()` (token hex determinista) y `url(path)`.

### `osprobe/engine.py` — el juez
- `OSProbeEngine(probes=None)` corre por defecto la lista `ALL_PROBES`
  (case → headers → notfound → backslash), en **serie** (respetar
  `--delay` global).
- Agregación: para cada probes que votó (no abstención, sin error),
  `contrib = vote × weight`. Porcentajes:
  `score = contrib / peso_posible_total × 100` (el base son los
  probes que participaron), por eso un objetivo con proxy total
  combativo queda menos peso).
- `FinalVerdict.confidence`: Σ pesos de los probes que realmente
  votaron / Σ pesos totales — los abstenciones bajan la fe.

### `osprobe/ui.py` — la fachada
- Banner `ascii art` + gradiente HSL (lerp de `hue/saturation/light`)
  sobre el texto de cada línea.
- `Progress` de Rich con spinner magenta, barra, contador, y tiempo.
- `Live`/medidor del veredicto: barras ▮/▯ en 24 ancho, integración
  porcentual normalizada.
- `render_verdict` añade la tabla detalle por probe con certezas y
  evidencia sanitizada.
- Respeta `NO_COLOR` + `--no-color` + `--quiet` (narrow mode).

### `osprobe/demo.py` — los simuladores
- `make_fake_app(os_type)` construye una app aiohttp con un mini-DFS
  en memoria (`_VIRTUAL_FILES`).
- `linux`: lookup por clave exacta (case-sensitive), `\\` como
  carácter de ruta; 404 nativo Apache.
- `windows`: `.lower()` + `\\ → /` en la ruta de búsqueda; headers
  IIS/ASP.NET; 404 nativo IIS; el mismo cuerpo para `/IMAGES`.
- Es el mismo simulador que usan los `pytest` — montado con el
  runner de aiohttp en un puerto aleatorio sobre `127.0.0.1`.

### `osprobe/report.py` — informes
- `to_json`: serialización disciplina con datetime ISO, evidencia
  lista, error + certainty.
- `to_markdown`: tabla legible con la evidencia y el veredicto —
  diseñada para pegar en Google Docs / Notion.

---

## 3. Decisiones de diseño (el por qué)

| Decisión | Por qué |
|---|---|
| aiohttp async en vez de requests sync | 4 probes × varias peticiones son mucho más fluidas sin bloquear el event loop, y Rich puede animar entre requests |
| Probes en serie, no paralelos | Paralelizar contra un servidor con rate-limit muerde, y las peticiones del case-sensitivity tienen orden lógico (semilla → variantes) |
| "Existencia" = no 404/410 (no sólo 200) | un handler con autenticación contesta 302→login o 403; eso también informa tanto como un 200 |
| Veredicto por consenso ponderado, no booleano | un solo probe puede mentir (proxy, WAF); 4 vectores con pesos distintos descans mejor entre sí |
| HTTP puro: nada de ICMP ni raw sockets | atraviesa firewalls corporativos que cortan ICMP; y es la técnica que pide el usuario: «recursos web de la URL» |
| Peso humilde para backslash (w20) | los WAF suelen bloquear `\`; la técnica la consideramos sospecha siempre |
| 3 peticiones de 404 en vez de 1 | amortiza páginas de error personalizadas del admin |

## 4. Extensión

- **Probe nuevo** → ver `probes/base.py` y el § COER de `PROBES.md`.
- **Nueva clase de OS (BSD? macOS server?)** → añade miembro a
  `OSType`, votos adicionales en los probes y una fila nueva en
  `ui.render_verdict` + `report`.
- **Benchmark CI**: los simuladores viven en `demo.py`; su
  comportamiento Linux/Windows está clavado por los tests — no lo
  cambies sin actualizar los tests primero.
