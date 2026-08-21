#python -m gunicorn simple_shoppinglist.asgi:application -k uvicorn.workers.UvicornWorker --bind '127.0.0.1:8080' --access-logfile=./access.log --access-logformat "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s'" --error-logfile=./error.log

# Caddy terminates TLS and proxies here. The app must never be reachable on
# :8080 directly -- that would bypass TLS and every downstream control.
bind = '127.0.0.1:8080'
errorlog = "./error.log"
accesslog = "./access.log"

# Correct anyway on a Pi with SQLite (write contention), but also required
# for django-ratelimit's FileBasedCache counters to represent a real global
# rate rather than N independent per-worker counters -- see CACHES in
# settings.py.
workers = 1

access_log_format = "%(h)s %(l)s %(u)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s'"

# Only trust X-Forwarded-For from Caddy on loopback. Never set this to '*' --
# that makes the client IP spoofable, which silently breaks per-IP rate
# limiting (P0-5) and any future audit logging.
forwarded_allow_ips = '127.0.0.1'
