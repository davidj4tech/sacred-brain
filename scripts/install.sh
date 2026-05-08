#!/usr/bin/env bash
# Backwards-compatible shim around the Makefile.
#
# Sacred Brain installation is driven by `make` targets — see Makefile and
# docs/INSTALL.md. This script is kept so existing muscle memory and any
# external docs that reference `./scripts/install.sh` continue to work.
#
# Usage:
#   sudo ./scripts/install.sh             →  make install
#   sudo ./scripts/install.sh --update    →  make install-update
#   sudo ./scripts/install.sh --uninstall →  make uninstall
#   sudo ./scripts/install.sh --uninstall --purge → make uninstall-purge

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

case "${1:-}" in
    "")            target=install ;;
    --update)      target=install-update ;;
    --uninstall)
        if [[ "${2:-}" == "--purge" ]]; then
            target=uninstall-purge
        else
            target=uninstall
        fi
        ;;
    -h|--help)
        sed -n '4,12p' "$0"
        exit 0
        ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
esac

exec make "$target"
