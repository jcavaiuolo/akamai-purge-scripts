#!/usr/bin/env python3
"""
purge_by_tag.py
----------------
Purga contenido en Akamai usando la Fast Purge API v3 (CCU), por cache tag
(header Edge-Cache-Tag) en vez de por URL.

Requiere:
    pip install edgegrid-python requests --break-system-packages

Credenciales:
    Lee las credenciales EdgeGrid del archivo .edgerc ubicado en el mismo
    directorio que este script (sección [default]).

Uso:
    python3 purge_by_tag.py tags.txt
    python3 purge_by_tag.py --tag black-friday
    python3 purge_by_tag.py --tag black-friday --tag electronics
    python3 purge_by_tag.py --tag black-friday --network staging --action delete

Se puede pasar un archivo con un tag por línea (mismo formato que
urls_ejemplo.txt), o uno o más tags puntuales con --tag (repetible). No se
pueden combinar ambos modos en la misma llamada.

--network selecciona el ambiente de Akamai a purgar: "production" (default)
o "staging". Si la propiedad que estás purgando solo está activada/desplegada
en staging, tenés que pasar explícitamente --network staging o el purge no
tendrá efecto sobre ese contenido.

Importante: para que un objeto sea purgable por tag, el content tiene que
tener el header de respuesta Edge-Cache-Tag configurado (en Property Manager
o desde el origin) ANTES de que se cachee. Un tag que nunca fue asignado a
ningún objeto no purga nada (no da error, simplemente no hay nada que hacer).

Formato de tags.txt (un tag por línea):
    black-friday
    electronics

Las líneas vacías o que empiezan con # se ignoran.

Referencias:
    https://techdocs.akamai.com/purge-cache/reference/post-invalidate-tag
    https://techdocs.akamai.com/purge-cache/docs/assign-cache-tags
    https://techdocs.akamai.com/purge-cache/reference/rate-limiting
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

# A diferencia de las URLs (hasta 50.000 por request), los cache tags tienen
# su propio token bucket de rate limiting: 5.000 tokens, que se recargan a
# 500/min. Usamos ese número como tope de lote para no vaciar el bucket de
# un solo request.
MAX_TAGS_PER_REQUEST = 5000


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


def read_tags(path):
    """Lee el archivo de tags, ignorando líneas vacías y comentarios (#)."""
    if not os.path.isfile(path):
        sys.exit(f"No se encontró el archivo de tags: {path}")

    with open(path, "r", encoding="utf-8") as f:
        tags = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    if not tags:
        sys.exit("El archivo de tags está vacío.")

    return tags


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def submit_purge(session, base_url, tags, network, action):
    """Envía un batch de tags al endpoint de Fast Purge v3."""
    endpoint = f"{base_url}/ccu/v3/{action}/tag/{network}"
    payload = {"objects": tags}

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
        description="Purga cache tags en Akamai vía Fast Purge API v3, desde un archivo o puntualmente."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Archivo con un tag por línea (omitir si se usa --tag)",
    )
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Tag puntual a purgar, sin necesidad de archivo (repetible: --tag a --tag b)",
    )
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

    if args.file and args.tags:
        parser.error("Usá un archivo o --tag, no ambos a la vez.")
    if not args.file and not args.tags:
        parser.error("Falta el archivo de tags o al menos un --tag.")

    tags = args.tags if args.tags else read_tags(args.file)

    session, base_url = load_session()

    print(f"Se van a purgar {len(tags)} tag(s)" + (f" de {args.file}" if args.file else " (puntual)"))
    print(f"Red: {args.network} | Acción: {args.action}\n")

    all_ok = True
    for i, batch in enumerate(chunk(tags, MAX_TAGS_PER_REQUEST), start=1):
        print(f"--- Enviando lote {i} ({len(batch)} tags) ---")
        ok = submit_purge(session, base_url, batch, args.network, args.action)
        all_ok = all_ok and ok

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
