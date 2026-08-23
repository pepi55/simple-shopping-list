# Gunicorn is bound to loopback only. TLS terminates at the Caddy front
# proxy (see Caddyfile). Caddy forwards to 127.0.0.1:8080 and sets
# X-Forwarded-Proto; only Caddy is trusted to set forwarded headers.
bind = "127.0.0.1:8080"
forwarded_allow_ips = "127.0.0.1"
workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
