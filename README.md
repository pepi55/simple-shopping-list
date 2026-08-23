# simple-shopping-list

Simple applet for tracking shopping lists for multiple users.

## Setup

- Generate a secret key: `SECRET_KEY="$(python -c 'from django.core.management import utils; print(utils.get_random_secret_key())')"`
- Export it before running any `manage.py` command. Treat it as a secret; never commit it.

## Local development

```
cd django_code
SECRET_KEY="$(python -c 'from django.core.management import utils; print(utils.get_random_secret_key())')" \
    python manage.py runserver
```

Plain HTTP will redirect-loop because `SECURE_SSL_REDIRECT = True` and
`SECURE_HSTS_SECONDS = 60` are hard-coded. For local work either:

- set `DJANGO_DEBUG=1 SECURE_SSL_REDIRECT=0` in the environment (both
  default to their secure production values), or
- terminate TLS locally with a reverse proxy (e.g. `caddy run --config Caddyfile`).

## Production

TLS is terminated at the Caddy front proxy. Gunicorn binds to
`127.0.0.1:8080` only and is not reachable from the network directly.

1. `pip install -r requirements.txt`
2. `SECRET_KEY=… ALLOWED_HOSTS=petar-dev.com,.petar-dev.com,pie3 python manage.py migrate` (defaults already include these hosts)
3. `cd django_code && caddy run --config Caddyfile` (auto-issues and renews Let's Encrypt certs; `pie3` uses Caddy's built-in local CA — trust its root on LAN clients to avoid browser warnings)
4. `cd django_code && bash run.sh`

`run.sh` invokes `gunicorn -c gunicorn_conf.py`; `gunicorn_conf.py` is the single source of truth for the loopback bind, `forwarded_allow_ips`, and worker count.
