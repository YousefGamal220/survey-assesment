#!/usr/bin/env bash
set -euo pipefail

wait_for() {
    local host="$1"
    local port="$2"
    echo ">>> waiting for ${host}:${port}..."
    until nc -z "${host}" "${port}" >/dev/null 2>&1; do sleep 0.5; done
    echo ">>> ${host}:${port} is up."
}

if [[ "${DATABASE_URL:-}" =~ @([^:/]+):([0-9]+)/ ]]; then
    wait_for "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
fi
if [[ "${REDIS_URL:-}" =~ @?([^:/]+):([0-9]+) ]]; then
    wait_for "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
fi

case "${1:-web}" in
    web)
        python manage.py migrate --noinput
        python manage.py seed_rbac
        if [[ "${DJANGO_SETTINGS_MODULE:-}" == "config.settings.prod" ]]; then
            python manage.py collectstatic --noinput
            exec gunicorn config.wsgi:application \
                 --bind 0.0.0.0:8000 \
                 --workers 3 \
                 --access-logfile - \
                 --error-logfile -
        else
            exec python manage.py runserver 0.0.0.0:8000
        fi
        ;;
    worker)
        exec celery -A config worker -l info
        ;;
    beat)
        exec celery -A config beat -l info
        ;;
    manage)
        shift
        exec python manage.py "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
