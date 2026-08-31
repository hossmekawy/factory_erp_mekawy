#!/bin/sh
# Run manage.py against the development database, never production.
# The production DB is only ever migrated after Hussien says so.
# Usage: ./dev.sh migrate   ./dev.sh shell   ./dev.sh runserver
DB_NAME=factory_erp_dev exec "$(dirname "$0")/venv/bin/python" "$(dirname "$0")/manage.py" "$@"
