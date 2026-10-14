# 📖 Manual de uso de OSProbe

Referencia completa de todos los parámetros, ejemplos reales y casos
borde. Para la anatomía interna de cada probe ve a [`PROBES.md`](PROBES.md),
y para el flujo del motor, [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Sinopsis

```bash
python3 -m osprobe [objetivo] [opciones]
# ó, si lo instalaste con pip install .:
osprobe [objetivo] [opciones]
```

- **`objetivo`** — posicional, opcional (obligatorio salvo con `--demo`).
  Formatos aceptados:
  | Formato | Interpretación |
  |---|---|
  | `http://host:puerto/ruta` | tal cual; `/ruta` es la ruta semilla |
  | `https://host` | TLS verificado por defecto |
  | `host` | asume `http://host`, puerto 80 |
  | `host:8080` | asume `http://host:8080` |
  | `ftp://...` | ✗ error de esquema (exit 2) |

---

## Parámetros, uno a uno

### `-p, --path RUTA` — la ruta semilla
Es **la decisión más importante del escaneo**. Es la ruta que tú
confirmaS que existe en el servidor (una carpeta de imágenes, un
`/static`, `/assets`, ...). El probe estrella necesita al menos una
ruta real para comparar variantes de mayúsculas.

- Si **no la pasas**, OSProbe usa la ruta de la URL objetivo. Pasa
  `http://host/images` y la semilla es `images`.
- Si la semilla responde `404`, el probe case-sensitivity se abstiene
  y **lo dice en el informe**: nada de comparar contra fantasmas.
- Si ninguna te suena, la propia portada (200), `/assets`, `/static`, `/images`, `/js`, `/css`... y con `--deep` el motor prueba más variantes.

### `-t, --timeout SEG`
Timeout **total por petición** en segundos (default `8.0`).
- Red local / lab: `2`–`3` es de sobra.
- Wi-Fi 3G o redes saturadas: `15`.
- Con `--proxy` por Tor: `30` (Tor es lento con las redes muertas).
El HttpClient establece este valor como `aiohttp.ClientTimeout(total=...)`
y lo aplica a cada petición de cada probe.

### `-r, --retries N`
Reintentos ante `aiohttp.ClientError` u `asyncio.TimeoutError`
(default `2`). Backoff exponencial entre intentos:
`0.15s → 0.30s → 0.60s (cap 1.5s)`. Un `404` no cuenta como fallo de
red — los reintentos NO duplican peticiones 404.

### `-d, --delay SEG`
**Rate limiting amable**. Espera un valor aleatorio entre el 50 % y el
100 % de `delay` antes de cada petición, y un extra de `delay/2` entre
probes. Con `--delay 0.5` y ~15 peticiones el escaneo tarda ~8 s pero no
dispara ningún rate-limit anti-bruteforce. Default: `0` (sin espera);
para auditar responsablemente: `0.3`–`1.0`.

### `-x, --proxy URL`
Enruta **todas** las peticiones HTTP por el proxy dado.
- `http://` / `https://`: Burp (`http://127.0.0.1:8080`), mitmproxy, ...
- `socks5://`: Tor (`socks5://127.0.0.1:9050`) — requiere
  `pip install aiohttp-socks`.
Los 404 y 200 del proxy no confunden al motor: los probes miran el
cuerpo del 404 contra firmas de IIS/Apache, no la cabecera del proxy.

### `-k, --insecure`
Deshabilita la verificación del certificado TLS (equivalente nmap
`-k`, curl `-k`). Necesario con self-signed en labs internos. Sin
esto, aiohttp lanza `SSLError` y el motor lo reporta como `NetworkError`
corto y bonito.

### `-a, --user-agent`
Custom User-Agent. Defaults a `OSProbe/1.0 (+link)`. ¿Por qué importantes?
- Las ACL con heurística UA-mock pueden dejar pasar UA de navegador.
- Un UA de navegador (`Mozilla/5.0 ...`) reproduce el comportamiento
  de un humano — menos fingerprints de «scanner detectado».

### `--deep`
Vuelve el escaneo agresivo:
- Casing: añade camelCase intercalado (`a1b2c3` → en `deep` testeaa
  `A1B2c3`) por cada fragmento de la semilla.
- Backslash: añade rutas como `\{seed}` y `{seed}\%2e%2e\web.config`.
Use con moderación en producción: duplica requests.

### `--export json|md|txt|both`
Exporta el informe a `osprobe-informe.{json,md,txt}` en `--export-dir`
(default `.`). `both` = JSON (máquina) + MD (persona). Los archivos
siempre se generan y **se imprime la ruta exacta** al terminar.

### `-q, --quiet`
Sin banner, spinner ni animaciones: solamente errores + el panel del
veredicto en modo mínimo. Perfecto para `cron` y para `curl | bash`
instaladores. **Nota**: incluso con `-q`, los códigos de salidase mantienen (eso es lo que importa en pipelines).

### `--no-color`
Fuerza salida sin ANSI-scape aparte de `--quiet`. Respeta también la
variable de entorno `NO_COLOR` (estándar POSIX-ISH).

### `--demo`
Corre OSProbe contra **dos servidores simulados residentes**:
1. `linux-mock`: FS case-sensitive, Apache headers, 404-nativo Apache.
2. `windows-mock`: NTFS case-insensitive, IIS/ASP.NET headers, 404-nativo IIS.
Cada uno escanea como un objetivo real en `127.0.0.1:<puerto libres>`,
y se cierra al terminar. Sirve para:
- ver las animaciones sin tocar nada,
- verificar tu instalación,
- y que los devs validen su código (los mismos mocks usa `pytest`).

---

## Códigos de salida

| Código | Significado |
|---|---|
| `0` | Escaneo completo; veredicto emitido |
| `2` | `objetivo` inválido (esquema no soportado, host vacío) |
| `3` | Fallo de red total tras los reintentos (host muerto, DNS, TLS) |
| `130` | Interrumpido por el usuario (Ctrl-C) |

## Preguntas frecuentes

**¿Puedo usarlo en CTFs?** Sí, es su hábitat natural (HackTheBox, TryHackMe...).
**¿Lo detecta un WAF?** Las peticiones son GET normales, pero las
rutas con `\` y `%2e%2e` del `--deep` pueden disparar WAFs.
**¿Y si hay un Cloudflare delante?** El motor seguirá midiendo el comportamiento del FS del *origin*, siempre que el 404 llegue transparente;
con cacheo agresivo los 404 también se cachean y la señal sale
ambigua — tendrás «sospecha», no certeza.
