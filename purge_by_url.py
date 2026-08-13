#!/usr/bin/env python3
"""
purge_by_url.py
----------------
Purga contenido en Akamai usando la Fast Purge API v3 (CCU), a partir de un
archivo de texto con una URL por línea.

Requiere:
    pip install edgegrid-python requests --break-system-packages

Credenciales:
    Lee las credenciales EdgeGrid del archivo .edgerc ubicado en el mismo
    directorio que este script (sección [default]).

Uso:
    python3 purge_by_url.py urls.txt
    python3 purge_by_url.py urls.txt --network staging
    python3 purge_by_url.py urls.txt --action delete

--network selecciona el ambiente de Akamai a purgar: "production" (default)
o "staging". Si la propiedad que estás purgando solo está activada/desplegada
en staging, tenés que pasar explícitamente --network staging o el purge no
tendrá efecto sobre ese contenido.

Formato de urls.txt (una URL completa por línea, con esquema y host):
    https://www.example.com/path/imagen.png
    http://www.example.com/otro/recurso.js

Las líneas vacías o que empiezan con # se ignoran.

Referencias:
    https://techdocs.akamai.com/purge-cache/reference/api-summary
    https://techdocs.akamai.com/purge-cache/docs/rate-limiting
"""

import argparse
import json
import os
import sys

try:
    import requests
    from akamai.edgegrid import EdgeGridAuth, EdgeRc
except ImportError:
    sys.exit(
        "Faltan dependencias. Instalá con:\n"
        "  pip install edgegrid-python requests --break-system-packages"
    )

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EDGERC_PATH = os.path.join(SCRIPT_DIR, ".edgerc")
EDGERC_SECTION = "default"

# Límite documentado por Akamai: hasta 50.000 URLs por request de Fast Purge.
MAX_URLS_PER_REQUEST = 50000


def load_session():
    """Crea una sesión requests firmada con EdgeGrid a partir del .edgerc local."""
    if not os.path.isfile(EDGERC_PATH):
        sys.exit(f"No se encontró el archivo de credenciales: {EDGERC_PATH}")

    edgerc = EdgeRc(EDGERC_PATH)
    section = EDGERC_SECTION if edgerc.has_section(EDGERC_SECTION) else "default"

    session = requests.Session()
    session.auth = EdgeGridAuth(
        client_token=edgerc.get(section, "client_token"),
        client_secret=edgerc.get(section, "client_secret"),
        access_token=edgerc.get(section, "access_token"),
    )
    base_url = "https://" + edgerc.get(section, "host")
    return session, base_url


def read_urls(path):
    """Lee el archivo de URLs, ignorando líneas vacías y comentarios (#)."""
    if not os.path.isfile(path):
        sys.exit(f"No se encontró el archivo de URLs: {path}")

    with open(path, "r", encoding="utf-8") as f:
        urls = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not urls:
        sys.exit("El archivo de URLs está vacío.")

    return urls


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def submit_purge(session, base_url, urls, network, action):
    """Envía un batch de URLs al endpoint de Fast Purge v3."""
    endpoint = f"{base_url}/ccu/v3/{action}/url/{network}"
    payload = {"objects": urls}

    response = session.post(endpoint, json=payload, timeout=30)

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    print(f"POST {endpoint}")
    print(f"  status: {response.status_code}")
    print(f"  respuesta: {json.dumps(body, indent=2, ensure_ascii=False)}")

    if response.status_code >= 300:
        print("  -> ERROR: la API devolvió un error, revisá el detalle arriba.", file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Purga URLs en Akamai vía Fast Purge API v3, leyendo un archivo de texto."
    )
    parser.add_argument("file", help="Archivo con una URL por línea")
    parser.add_argument(
        "--network",
        choices=["production", "staging"],
        default="production",
        help="Red a purgar: production (default) o staging",
    )
    parser.add_argument(
        "--action",
        choices=["invalidate", "delete"],
        default="invalidate",
        help=(
            "invalidate marca el contenido como stale (recomendado). "
            "delete lo elimina de la caché de inmediato (default: invalidate)"
        ),
    )
    args = parser.parse_args()

    session, base_url = load_session()
    urls = read_urls(args.file)

    print(f"Se leyeron {len(urls)} URLs de {args.file}")
    print(f"Red: {args.network} | Acción: {args.action}\n")

    all_ok = True
    for i, batch in enumerate(chunk(urls, MAX_URLS_PER_REQUEST), start=1):
        print(f"--- Enviando lote {i} ({len(batch)} URLs) ---")
        ok = submit_purge(session, base_url, batch, args.network, args.action)
        all_ok = all_ok and ok

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
