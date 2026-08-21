# simple-shopping-list
Simple applet for tracking shopping lists for multiple users.

## Required environment variables

 - `SECRET_KEY` — Django secret key. Generate with:
   `SECRET_KEY="$(python -c 'from django.core.management import utils; print(utils.get_random_secret_key())')"`
 - `ALLOWED_HOSTS` — comma-separated list of hosts Django will serve, e.g.
   `ALLOWED_HOSTS="<hostname>.com,www.<hostname>.com"`
 - `ADMIN_URL` — path to mount the Django admin at, instead of the default
   `admin/`. Must end with a trailing slash, e.g. `ADMIN_URL="mgmt-a1b2c3/"`.
   The app fails to start if this is unset.

## Running

The app must sit behind a reverse proxy (Caddy, see `Caddyfile`) that
terminates TLS and forwards `X-Forwarded-Proto`. It must **not** be reachable
directly on its bind port from off-box — that bypasses TLS and the
`SECURE_SSL_REDIRECT`/HSTS settings entirely.

 - Run server: `python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn.workers.UvicornWorker -c gunicorn_conf.py`
     - Run server (no gunicorn): `python -m uvicorn simple_shoppinglist.asgi:application --reload --port $PORT --host $HOST`
