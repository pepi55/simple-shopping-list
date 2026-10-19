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
 - `MEMCACHED_LOCATION` — optional, defaults to `127.0.0.1:11211`.

## Running

Requires Python 3.12 (Django 5.2 LTS supports 3.10–3.13): `pip install -r
requirements.txt`.

Rate limiting needs memcached, whose atomic counters are what make the limit
hold under concurrent requests. On Debian/Raspberry Pi OS: `apt install
memcached` (it binds to loopback by default). If memcached is down, write
endpoints fail with a 500 rather than going unthrottled.

The app must sit behind a reverse proxy (Caddy, see `Caddyfile`) that
terminates TLS and forwards `X-Forwarded-Proto`. It must **not** be reachable
directly on its bind port from off-box — that bypasses TLS and the
`SECURE_SSL_REDIRECT`/HSTS settings entirely.

 - Run server: `python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn_worker.UvicornWorker -c gunicorn_conf.py`
     - Run server (no gunicorn): `python -m uvicorn simple_shoppinglist.asgi:application --reload --port $PORT --host $HOST`

## Testing

From `django_code/`, with no env vars or memcached needed:

`python manage.py test shoppinglist --settings=simple_shoppinglist.settings_test`
