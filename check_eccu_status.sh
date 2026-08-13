#!/usr/bin/env bash
#
# check_eccu_status.sh
# ---------------------
# Consulta el estado de un requestId de ECCU (GET /eccu-api/v1/requests/{requestId}).
# El endpoint requiere autenticación EdgeGrid, así que este script usa
# edgegrid-python solo para firmar el request y generar el header
# Authorization; la consulta en sí se hace con curl.
#
# Requiere:
#   pip install edgegrid-python requests --break-system-packages
#
# Credenciales:
#   Lee las credenciales EdgeGrid del archivo .edgerc ubicado en el mismo
#   directorio que este script (sección [default]).
#
# Uso:
#   ./check_eccu_status.sh <requestId>
#
# Ejemplo:
#   ./check_eccu_status.sh 357713780
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDGERC_PATH="$SCRIPT_DIR/.edgerc"

if [ "$#" -ne 1 ]; then
  echo "Uso: $0 <requestId>" >&2
  exit 1
fi

REQUEST_ID="$1"

if [ ! -f "$EDGERC_PATH" ]; then
  echo "No se encontró el archivo de credenciales: $EDGERC_PATH" >&2
  exit 1
fi

HOST=$(python3 -c "from akamai.edgegrid import EdgeRc; print(EdgeRc('$EDGERC_PATH').get('default', 'host'))")

AUTH_HEADER=$(python3 -c "
from akamai.edgegrid import EdgeGridAuth, EdgeRc
import requests

edgerc = EdgeRc('$EDGERC_PATH')
req = requests.Request('GET', 'https://$HOST/eccu-api/v1/requests/$REQUEST_ID').prepare()
auth = EdgeGridAuth(
    client_token=edgerc.get('default', 'client_token'),
    client_secret=edgerc.get('default', 'client_secret'),
    access_token=edgerc.get('default', 'access_token'),
)
signed = auth(req)
print(signed.headers['Authorization'])
")

curl -s -H "Authorization: $AUTH_HEADER" "https://$HOST/eccu-api/v1/requests/$REQUEST_ID"
echo
