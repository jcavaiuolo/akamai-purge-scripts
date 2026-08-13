#!/usr/bin/env bash
#
# verify_cache_keys.sh
# ---------------------
# Hace curl a una o más URLs con el header Pragma de debug de Akamai, y
# muestra si el resultado fue HIT o MISS (extraído del header X-Cache, ej.
# "TCP_HIT from ..."), junto con la cache key interna (X-Cache-Key) de cada
# objeto. Útil para confirmar el estado de caché antes y después de una
# purga (con purge_by_url.py o purge_by_directory.py).
#
# Uso:
#   ./verify_cache_keys.sh https://www.example.com/ruta/imagen.png [otra-url ...]
#
# Requiere al menos una URL como argumento.
#
# Referencia:
#   https://techdocs.akamai.com/edge-diagnostics/docs/pragma-headers
#
# NOTA: si el hostname de destino no tiene certificado TLS propio configurado
# en la propiedad (el handshake HTTPS devuelve el certificado default de
# Akamai, CN=a248.e.akamai.net, que no matchea el hostname), usá http://
# en lugar de https:// para esa URL.
#

set -euo pipefail

# Pragma de debug: pedimos X-Cache (estado de hit/miss), X-Check-Cacheable
# (si el objeto es cacheable) y X-Cache-Key (la cache key interna del edge).
PRAGMA="akamai-x-cache-on, akamai-x-check-cacheable, akamai-x-get-cache-key, akamai-x-get-true-cache-key"

if [ "$#" -eq 0 ]; then
  echo "Uso: $0 <url> [url2 ...]" >&2
  echo "Ejemplo: $0 https://www.example.com/ruta/imagen.png" >&2
  exit 1
fi

URLS=("$@")

for url in "${URLS[@]}"; do
  echo "=== $url ==="
  headers=$(curl -s -D - -o /dev/null --max-time 15 -H "Pragma: ${PRAGMA}" "$url")

  # curl con -D imprime los headers con \r\n; normalizamos antes de grep.
  cache=$(echo "$headers" | tr -d '\r' | grep -i '^X-Cache:' || true)
  cache_key=$(echo "$headers" | tr -d '\r' | grep -i '^X-Cache-Key:' || true)
  true_cache_key=$(echo "$headers" | tr -d '\r' | grep -i '^X-True-Cache-Key:' || true)
  checkable=$(echo "$headers" | tr -d '\r' | grep -i '^X-Check-Cacheable:' || true)
  status_line=$(echo "$headers" | head -n 1 | tr -d '\r')

  # El estado HIT/MISS viene en X-Cache (ej: "TCP_HIT from ..."), no en
  # X-Cache-Key (esa es solo la clave interna de caché, no el resultado).
  result="DESCONOCIDO"
  if echo "$cache" | grep -qiE 'TCP_HIT|TCP_MEM_HIT|TCP_IMS_HIT'; then
    result="HIT"
  elif echo "$cache" | grep -qiE 'TCP_MISS|TCP_REFRESH|TCP_EXPIRED'; then
    result="MISS"
  fi

  echo "  status:            $status_line"
  echo "  resultado:         $result"
  [ -n "$cache" ]            && echo "  $cache"
  [ -n "$checkable" ]        && echo "  $checkable"
  if [ -n "$cache_key" ]; then
    echo "  $cache_key"
  else
    echo "  X-Cache-Key: (no devuelto — revisá que el debug de Pragma esté habilitado para esta propiedad)"
  fi
  [ -n "$true_cache_key" ]   && echo "  $true_cache_key"
  echo
done
