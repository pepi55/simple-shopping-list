# Global agent instructions

Cross-repository convention for this machine. These apply in every repo; a project's own
`CLAUDE.md` / `AGENTS.md` layers repo-specific rules on top.

Use `mktemp` for temporary files, and `mktemp -d` for temporary directories.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`
(`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, ...). Tools like
release-please drive the next version and changelog from these prefixes, so the format is
load-bearing rather than cosmetic. Signal breaking changes with a `!` after the type (`feat!:`) or a `BREAKING CHANGE:` footer.

## Creating commits

Hand the real commit off to the user with a commit.sh script they run:

- Outside a worktree — don't run git commit at all. Write commit.sh at the repo root containing the exact git add / git commit invocations you intended (one commit per git commit call, real Conventional-Commit messages, trailers, etc.), then tell the user to run it.
- Inside a worktree — commit normally at sensible stopping points; those land unsigned on the agent/<name> branch. Still write commit.sh at the worktree root, but its job is to reflect the range you authored this session. Pick <base> as the parent of your first commit (e.g. HEAD~3 for three commits, or $(git merge-base HEAD <parent-branch>) when the count is dynamic).
- The script should handle removing itself on succesful execution.

## Pushing changes

Do not push directly to `main` or `master`. Create a script `./push.sh` for the user to push to a branch named `agent/<name>`.
Do not execute the script yourself and let the user run it manually.

---

# Repo-specific: simple-shopping-list

A small Django 6.1 app for shared shopping lists. The Django project lives in `django_code/`
(not the repo root). Everything below is relative to that subdir unless stated otherwise.

## Layout

- `django_code/manage.py` — standard Django entrypoint.
- `django_code/simple_shoppinglist/` — project package: `settings.py`, `urls.py`, `asgi.py`, `wsgi.py`.
- `django_code/shoppinglist/` — single app: `models.py` (`List`, `ShoppingItem`), `views.py`, `urls.py`, `admin.py`, `middleware.py`, `migrations/`, `templates/`, `static/`.
- `django_code/run.sh` — production launch (gunicorn + uvicorn worker, logging config).
- `django_code/gunicorn_conf.py`, `django_code/logging.conf` — server config.
- `django_code/Caddyfile` — production reverse proxy; terminates TLS on :443.
- `requirements.txt` at repo root — pip dependencies (pinned). No `pyproject.toml`, no
  `Pipfile`, no `setup.cfg`. `Django==6.1`, `gunicorn`, `whitenoise`, `uvicorn`.
- `TODO.md` — phased security hardening plan; check it before proposing large changes.

## Required env

- `SECRET_KEY` is read directly in `simple_shoppinglist/settings.py:25` (no default).
  Generate one: `python -c 'from django.core.management import utils; print(utils.get_random_secret_key())'`.
- `DEBUG` is off by default; set `DJANGO_DEBUG=1` to enable. `SECURE_SSL_REDIRECT`
  defaults to on; set `SECURE_SSL_REDIRECT=0` for plain-HTTP local dev. Without that,
  local dev over HTTP will redirect-loop.
- `ALLOWED_HOSTS` is a comma-separated env var (default `petar-dev.com,.petar-dev.com,pie3`).
  Serving from a new hostname requires updating both `ALLOWED_HOSTS` and
  `CSRF_TRUSTED_ORIGINS` in `settings.py`, or POSTs will fail CSRF validation.

## Common commands

Always `cd django_code` first; `manage.py` expects that as CWD so `BASE_DIR` and the
SQLite path resolve correctly.

- Migrate: `python manage.py migrate`
- Dev server: `python manage.py runserver` (HTTP only — see env note above).
- Tests: `python manage.py test` (no test framework other than `django.test`; `shoppinglist/tests.py` is currently a stub).
- Prod launch: `bash run.sh` (gunicorn ASGI via uvicorn worker, bound to `127.0.0.1:8080`; TLS is terminated by Caddy — start it with `caddy run --config Caddyfile`).
- Collect static: `python manage.py collectstatic` — `STATIC_ROOT = BASE_DIR / "staticfiles"`, served by WhiteNoise.

## Architecture notes

- `SECRET_KEY`, `DEBUG` (default off), HSTS, and secure-cookie flags are baked into
  `settings.py` — do not loosen them without an explicit reason.
- TLS topology: Caddy terminates TLS on :443 and proxies to gunicorn on `127.0.0.1:8080`
  (`SECURE_PROXY_SSL_HEADER` trusts Caddy's overwritten `X-Forwarded-Proto`). Never expose
  gunicorn on a public interface — that bypasses every other security control.
- `AdminRateLimiter` (`shoppinglist/middleware.py`) only rate-limits requests from `127.0.0.1` and `192.168.2.43` to `/admin/`. Update that allowlist if the admin is served from elsewhere.
- `shoppinglist/views.py` is intentionally unauthenticated by design (decision D1, referenced in module docstring). The project relies on URL secrecy, not login, for the public list views. Do not add `login_required` without revisiting that decision.
- State-modifying views (`update`, `delete`, `add`) use `@csrf_protect` and reject non-POST with `HttpResponseForbidden`. Keep that contract when adding new write endpoints.
- `ShoppingItem.bought_all` in `models.py:18-19` is a latent bug — it references the bare name `quantity` instead of `self.quantity`. Don't copy that pattern; fix it if you touch the file.
- `simple_shoppinglist/urls.py` has `django-pwa` URLs commented out and `INSTALLED_APPS` no longer includes `pwa` (see commit `3f91523`).

## Workflow

- There is no CI config, no pre-commit, no linter, and no type-checker wired up. Don't invent one; if you want one, ask first.
- Migrations live in `django_code/shoppinglist/migrations/`. After model changes, run `python manage.py makemigrations shoppinglist` from `django_code/`.
- The DB is SQLite at `django_code/db.sqlite3` (gitignored). For schema experiments, copy it aside rather than relying on backups.
