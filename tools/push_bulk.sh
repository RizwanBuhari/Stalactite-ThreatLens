#!/usr/bin/env bash
# Push whole folders (datasets, assets) into the shared notebook container.
#
#   THREATLENS_KEY=/path/to/private_key tools/push_bulk.sh PATH...
#
# PATHs are files or folders relative to the project root. They are packed
# locally into one tar archive, copied with scp to ~/staging, and unpacked in
# /home/ibm-user/shared/threatlens with --keep-old-files: files that already
# exist are never replaced (tar reports them and exits non-zero). Use
# tools/push_to_server.sh --overwrite to intentionally update single files.
set -euo pipefail

HOST="${THREATLENS_HOST:?set THREATLENS_HOST, e.g. linux1@<server-ip>}"
KEY="${THREATLENS_KEY:?set THREATLENS_KEY to your private key path}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_OPTS=(-i "$KEY" -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=30)
[ $# -gt 0 ] || { echo "usage: $0 PATH..." >&2; exit 2; }

safe='^[A-Za-z0-9_.][A-Za-z0-9._-]*(/[A-Za-z0-9_.][A-Za-z0-9._-]*)*$'
dotseg='(^|/)\.\.?(/|$)'
for rel in "$@"; do
  rel="${rel%/}"
  [[ "$rel" =~ $safe && ! "$rel" =~ $dotseg ]] || { echo "refusing unsafe path: $rel" >&2; exit 2; }
  [ -e "$ROOT/$rel" ] || { echo "not found locally: $rel" >&2; exit 2; }
done

name="bulk_$(date +%Y%m%d_%H%M%S).tar"
local_tar="$(mktemp -d)/$name"
tar -C "$ROOT" --exclude='.DS_Store' --exclude='__MACOSX' -cf "$local_tar" -- "${@%/}"
echo "packed $(tar -tf "$local_tar" | grep -vc '/$') files ($(du -h "$local_tar" | cut -f1))"

ssh "${SSH_OPTS[@]}" "$HOST" mkdir -p staging
scp -q "${SSH_OPTS[@]}" -- "$local_tar" "$HOST:staging/$name"
rm -f -- "$local_tar"

# Fixed remote script; the archive name is generated above and matches [A-Za-z0-9_.].
ssh "${SSH_OPTS[@]}" "$HOST" bash -s -- "$name" <<'REMOTE'
set -uo pipefail
tarfile="$HOME/staging/$1"
podman exec -i notebook tar -x --keep-old-files --no-same-owner --no-same-permissions \
  -C /home/ibm-user/shared/threatlens -f - < "$tarfile"
status=$?
rm -f -- "$tarfile"
[ $status -eq 0 ] && echo "unpacked into /home/ibm-user/shared/threatlens" \
                  || echo "tar exit $status (existing files were kept, see messages above)"
exit $status
REMOTE
