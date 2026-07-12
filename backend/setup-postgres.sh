#!/usr/bin/env bash
# Generate a local-only PostgreSQL password, start the licensed PostgreSQL container,
# and print the DATABASE_URL exports. Secrets stay in backend/.postgres.env,
# which is gitignored and mode 600.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS="$HERE/.postgres.env"

if [[ ! -f "$SECRETS" ]]; then
  umask 077
  password="$(openssl rand -hex 24)"
  {
    printf 'POSTGRES_PASSWORD=%s\n' "$password"
    printf 'POSTGRES_PORT=55432\n'
    printf 'DATABASE_URL=postgresql://sankat:%s@127.0.0.1:55432/sankat_mochan\n' "$password"
    printf 'SANKAT_DATABASE_REQUIRED=true\n'
  } >"$SECRETS"
fi

set -a
# shellcheck disable=SC1090
source "$SECRETS"
set +a
docker compose --env-file "$SECRETS" -f "$HERE/compose.yaml" up -d postgres
echo "PostgreSQL is starting. Before launching uvicorn, run:"
echo "  set -a; source '$SECRETS'; set +a"
