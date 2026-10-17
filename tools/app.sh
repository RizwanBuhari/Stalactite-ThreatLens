#!/usr/bin/env bash
# Start, stop or check the ThreatLens app inside the shared notebook container.
#
#   THREATLENS_KEY=/path/to/private_key tools/app.sh start|stop|status|logs
#
# Then open the app from your laptop with an SSH tunnel to its socket:
#   ssh -N -L 8050:/home/linux1/shared/threatlens/run/threatlens.sock -i KEY linux1@<server-ip>
#   http://localhost:8050
set -euo pipefail
HOST="${THREATLENS_HOST:?set THREATLENS_HOST, e.g. linux1@<server-ip>}"
KEY="${THREATLENS_KEY:?set THREATLENS_KEY to your private key path}"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 "$HOST")
DIR=/home/ibm-user/shared/threatlens

case "${1:-status}" in
  start)
    "${SSH[@]}" "podman exec notebook mkdir -p $DIR/outputs/logs $DIR/run && \
      podman exec -d -w $DIR notebook sh -c 'python -u app/server.py >> outputs/logs/app.log 2>&1'"
    echo "starting; model load takes ~20 s. Check with: $0 status" ;;
  stop)
    "${SSH[@]}" "podman exec -w $DIR notebook sh -c 'test -f run/server.pid && kill \$(cat run/server.pid) && rm -f run/server.pid && echo stopped || echo not running'" ;;
  status)
    "${SSH[@]}" "podman exec -w $DIR notebook sh -c 'ls -la run/ 2>/dev/null; tail -3 outputs/logs/app.log 2>/dev/null'" ;;
  logs)
    "${SSH[@]}" "podman exec -w $DIR notebook tail -40 outputs/logs/app.log" ;;
  *) echo "usage: $0 start|stop|status|logs" >&2; exit 2 ;;
esac
