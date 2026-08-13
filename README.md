# Scripts de purga de caché Akamai

Este directorio contiene dos scripts independientes para purgar contenido en Akamai, un script de verificación de estado de caché, y el archivo de credenciales que los scripts usan.

## Contenido

- `.edgerc` — credenciales EdgeGrid (client_secret, host, access_token, client_token). **No compartir ni subir a ningún repositorio.**
- `purge_by_url.py` — purga por URL vía **Fast Purge API v3**, leyendo una lista de URLs desde un archivo de texto. Soporta `production` y `staging`.
- `purge_by_directory.py` — purga recursiva de un directorio vía **ECCU API** (Fast Purge no soporta purga recursiva por path).
- `urls_ejemplo.txt` — archivo de ejemplo con el formato esperado por `purge_by_url.py`. Reemplazá las URLs por las tuyas.
- `verify_cache_keys.sh` — hace curl con el header `Pragma` de debug de Akamai a una o más URLs y muestra `X-Cache` (HIT/MISS), `X-Check-Cacheable`, `X-Cache-Key` y `X-True-Cache-Key`. Útil para confirmar el estado de caché antes y después de purgar.
- `eccu_properties_visibles.txt` — listado de propiedades (hostnames) visibles vía ECCU para las credenciales configuradas en `.edgerc` (generado con `GET /eccu-api/v1/properties`). Útil para elegir contra qué propiedad probar cuando no sabés qué ve tu client.

## Instalación

```bash
pip install edgegrid-python requests --break-system-packages
```

## Configuración de credenciales (`.edgerc`)

Los dos scripts Python leen las credenciales EdgeGrid del archivo `.edgerc` en este mismo directorio, sección `[default]`. Si no existe, creálo con este formato:

```ini
[default]
client_secret = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=
host = akab-xxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxx.luna.akamaiapis.net
access_token = akab-xxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxx
client_token = akab-xxxxxxxxxxxxxxxx-xxxxxxxxxxxxxxxx
```

Estas 4 credenciales (`client_secret`, `host`, `access_token`, `client_token`) se generan creando un **API client** en Akamai Control Center (Identity & Access Management → API clients), con permisos sobre **Fast Purge** (CCU) y/o **ECCU** según qué script vayas a usar. Al crear el client, Akamai te muestra el `.edgerc` completo una sola vez — hay que guardarlo ahí en ese momento.

**No subas `.edgerc` a ningún repositorio ni lo compartas** — son credenciales activas equivalentes a una contraseña.

## Uso: purga por URL (Fast Purge)

1. Editá `urls_ejemplo.txt` (o creá tu propio archivo) con una URL completa por línea (esquema + host + path).
2. Ejecutá:

```bash
python3 purge_by_url.py urls_ejemplo.txt
python3 purge_by_url.py urls_ejemplo.txt --network staging
python3 purge_by_url.py urls_ejemplo.txt --action delete
```

- `--network`: `production` (**default**) o `staging`. Si la propiedad que purgás solo está desplegada en staging, tenés que pasar `--network staging` explícitamente o la purga no tendrá efecto.
- `--action`: `invalidate` (recomendado, default) o `delete`.

## Uso: purga recursiva de directorio (ECCU)

```bash
python3 purge_by_directory.py --property www.example.com --path seccion/imagenes
```

Opciones útiles:

- `--property-type HOST_HEADER|ARL_TOKEN` (default `HOST_HEADER`)
- `--exact-match true|false` (default `true`)
- `--action invalidate|delete` (default `invalidate`)
- `--email tu@correo.com` (repetible, para notificaciones de estado)
- `--wait` — consulta el estado del request cada 10s hasta que termine (útil porque ECCU es asíncrono y puede tardar minutos u horas). Si tu terminal corta la llamada antes de que termine `--wait`, podés chequear el estado más tarde haciendo un GET manual a `/eccu-api/v1/requests/{requestId}` con las mismas credenciales.

**Limitación importante (verificada, no solo documentada):** la ECCU API no tiene parámetro de red (no existe un `--network` como en Fast Purge). El schema oficial de `/eccu-api/v1/requests` (`additionalProperties: false`) no admite ningún campo de red, y probarlo empíricamente con campos no documentados (`network`, `environment`, `targetEnvironment`) no cambió el comportamiento de la API. Si tu configuración está desplegada únicamente en staging, usá `purge_by_url.py --network staging` en su lugar.

Ejemplo completo:

```bash
python3 purge_by_directory.py \
  --property www.example.com \
  --path seccion/imagenes \
  --email tu@correo.com \
  --wait
```

## Uso: verificación de cache key

```bash
./verify_cache_keys.sh https://www.example.com/ruta/imagen.png
```

Hace curl con `Pragma: akamai-x-cache-on, akamai-x-check-cacheable, akamai-x-get-cache-key, akamai-x-get-true-cache-key` a cada URL pasada como argumento y muestra la respuesta de debug de Akamai, incluyendo el resultado HIT/MISS (leído de `X-Cache`, no de `X-Cache-Key`) y la cache key interna. Requiere al menos una URL como argumento — no tiene URLs por default.

Ejemplo de salida real:

```
=== https://www.example.com/ruta/imagen.png ===
  status:            HTTP/1.1 200 OK
  resultado:         MISS
  X-Cache: TCP_MISS from a23-50-51-39.deploy.akamaitechnologies.com (AkamaiGHost/22.6.1-...) (-)
  X-Check-Cacheable: YES
  X-Cache-Key: /L/15/1206924/30d/www.example.com/ruta/imagen.png
  X-True-Cache-Key: /L/www.example.com/ruta/imagen.png vcd=840
```

Si el hostname de destino no tiene certificado TLS propio (el handshake HTTPS devuelve el certificado default de Akamai `CN=a248.e.akamai.net`), usá `http://` para esa URL en lugar de `https://`.

## Diferencia entre ambos scripts de purga

| | `purge_by_url.py` (Fast Purge) | `purge_by_directory.py` (ECCU) |
|---|---|---|
| Qué purga | URLs exactas, listadas una por una | Un directorio completo, recursivamente |
| Velocidad | Segundos | Minutos a horas (asíncrono) |
| Selector de red (staging/production) | Sí, explícito (`--network`) | No existe (ver limitación arriba) |
| Cuándo usarlo | Sabés exactamente qué URLs cambiaron | Necesitás limpiar toda una sección/carpeta sin enumerar cada archivo |

## Referencias

- Fast Purge API v3: https://techdocs.akamai.com/purge-cache/reference/api-summary
- Purge by URL, CP Code, or Cache Tag: https://techdocs.akamai.com/purge-cache/docs/purge-by-url-cp-code-or-cache-tag
- ECCU API — Create request: https://techdocs.akamai.com/eccu/reference/post-request
- ECCU API v1 — spec OpenAPI oficial: https://github.com/akamai/akamai-apis/tree/main/apis/eccu-api/v1
- Enhanced CCU Request Format (formato del XML metadata): https://techdocs.akamai.com/purge-cache/docs/create-eccu-req-file
- Autenticación EdgeGrid: https://techdocs.akamai.com/developer/docs/authenticate-with-edgegrid
- Pragma headers (debug de caché): https://techdocs.akamai.com/edge-diagnostics/docs/pragma-headers
