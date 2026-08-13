#!/usr/bin/env python3
"""
purge_by_directory.py
----------------------
Purga recursiva de un directorio completo en Akamai usando la ECCU API
(Enhanced Content Control Utility), que sí soporta purga recursiva por path
a diferencia de Fast Purge (CCU v3).

Requiere:
    pip install edgegrid-python requests --break-system-packages

Credenciales:
    Lee las credenciales EdgeGrid del archivo .edgerc ubicado en el mismo
    directorio que este script (sección [default]).

Uso:
    python3 purge_by_directory.py --property www.example.com --path seccion/imagenes
    python3 purge_by_directory.py --property www.example.com --path seccion \
        --property-type ARL_TOKEN --exact-match false

El path se interpreta como una cadena de directorios anidados: "seccion/imagenes"
genera <match:recursive-dirs value="seccion"><match:recursive-dirs value="imagenes">,
que purga recursivamente todo bajo /seccion/imagenes/.

Es asíncrono: el POST devuelve un requestId de inmediato, pero el request
puede tardar varios minutos en resolverse. Usá --wait para esperar el
resultado en la misma llamada, o consultá el estado más tarde con
check_eccu_status.sh <requestId>.

Referencias:
    https://techdocs.akamai.com/eccu/reference/post-request
    https://techdocs.akamai.com/purge-cache/docs/create-eccu-req-file
    https://techdocs.akamai.com/purge-cache/docs/digital-props
"""

import argparse
import json
import os
import sys
import time

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


def build_metadata_xml(path, action):
    """
    Construye el XML de metadata con tags <match:recursive-dirs> anidados,
    uno por cada segmento del path.

    Ej: path="store/images" ->
        <match:recursive-dirs value="store">
          <match:recursive-dirs value="images">
            <revalidate>now</revalidate>
          </match:recursive-dirs>
        </match:recursive-dirs>
    """
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        sys.exit("El path no puede estar vacío.")

    action_tag = "<revalidate>now</revalidate>" if action == "invalidate" else "<delete>now</delete>"

    inner = action_tag
    for segment in reversed(segments):
        inner = f'<match:recursive-dirs value="{segment}">{inner}</match:recursive-dirs>'

    return f'<?xml version="1.0"?>\n<eccu>\n  {inner}\n</eccu>'


def submit_eccu_request(
    session,
    base_url,
    property_name,
    property_type,
    exact_match,
    metadata_xml,
    request_name,
    notes,
    emails,
):
    endpoint = f"{base_url}/eccu-api/v1/requests"
    payload = {
        "requestName": request_name,
        "notes": notes,
        "propertyName": property_name,
        "propertyNameExactMatch": exact_match,
        "propertyType": property_type,
        "metadata": metadata_xml,
    }
    if emails:
        payload["statusUpdateEmails"] = emails

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
        return None

    return body.get("requestId")


def check_status(session, base_url, request_id):
    endpoint = f"{base_url}/eccu-api/v1/requests/{request_id}"
    response = session.get(endpoint, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return response.status_code, body


def main():
    parser = argparse.ArgumentParser(
        description="Purga recursiva de un directorio en Akamai vía ECCU API."
    )
    parser.add_argument(
        "--property",
        required=True,
        dest="property_name",
        help="Hostname o ARL de la propiedad a purgar (ej: www.example.com)",
    )
    parser.add_argument(
        "--path",
        required=True,
        help='Directorio a purgar recursivamente, ej: "store/images"',
    )
    parser.add_argument(
        "--property-type",
        choices=["HOST_HEADER", "ARL_TOKEN"],
        default="HOST_HEADER",
        help="Tipo de propiedad (default: HOST_HEADER)",
    )
    parser.add_argument(
        "--exact-match",
        choices=["true", "false"],
        default="true",
        help="Match exacto del hostname o substring RHS (default: true)",
    )
    parser.add_argument(
        "--action",
        choices=["invalidate", "delete"],
        default="invalidate",
        help="invalidate (recomendado) o delete (default: invalidate)",
    )
    parser.add_argument(
        "--request-name",
        default="Recursive directory purge",
        help="Nombre descriptivo del request",
    )
    parser.add_argument(
        "--notes",
        default="Purga generada por purge_by_directory.py",
        help="Notas adicionales del request",
    )
    parser.add_argument(
        "--email",
        action="append",
        dest="emails",
        default=None,
        help="Email para notificaciones de estado (se puede repetir)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Si se pasa, espera y consulta el estado del request cada 10s hasta que termine",
    )
    args = parser.parse_args()

    session, base_url = load_session()
    metadata_xml = build_metadata_xml(args.path, args.action)

    print("XML de metadata generado:")
    print(metadata_xml)
    print()

    request_id = submit_eccu_request(
        session,
        base_url,
        property_name=args.property_name,
        property_type=args.property_type,
        exact_match=(args.exact_match == "true"),
        metadata_xml=metadata_xml,
        request_name=args.request_name,
        notes=args.notes,
        emails=args.emails,
    )

    if request_id is None:
        sys.exit(1)

    print(f"\nRequest creado con requestId={request_id}")

    if args.wait:
        print("Consultando estado (Ctrl+C para dejar de esperar)...")
        while True:
            time.sleep(10)
            status_code, body = check_status(session, base_url, request_id)
            status = body.get("status", "UNKNOWN")
            print(f"  status: {status} | detalle: {body.get('statusMessage', '')}")
            if status in ("SUCCEEDED", "FAILED", "IGNORED"):
                break


if __name__ == "__main__":
    main()
