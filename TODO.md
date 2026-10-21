# TODO – Security Hardening Roadmap

## P0 – Immediate (✓ done, ☐ pending)
- [x] P0‑1: Make rate limiting real (installed `django‑ratelimit`, middleware, memcached) – **done**
- [ ] P0‑2: Merge and deploy `agent/sec-test` branch (deploy now also needs Python 3.12, `pip install --require-hashes -r requirements.txt` and `migrate` for django‑axes 8)
- [ ] P0‑3: Rotate admin password and verify/rotate `SECRET_KEY`
- [x] P0‑4: Fix the Caddyfile (dedicated host `list.petar-dev.com`, 256 KB request‑body limit, CSP report‑only header, `DATA_UPLOAD_MAX_MEMORY_SIZE`; `ALLOWED_HOSTS` stays an env var, set to `list.petar-dev.com` on the Pi) – **done**; follow‑ups:
  - [ ] Admin login throttle in Caddy (still commented out; needs an `xcaddy` build with `caddy-ratelimit`)
  - [ ] Move the inline style at `forms.py:13` into `style.css`
  - [ ] Switch CSP from report‑only to enforcing after a clean week
- [ ] P0‑5: Upgrade to Python 3.12 and Django 5.2 LTS – **repo side done** (hash‑locked Django 5.2.18, `pymemcache` restored, `uvicorn-worker`, uvloop dropped; suite, `check --deploy` and pip‑audit pass on a fresh 3.13 venv); pending: first CI run on 3.12, then the Pi runtime upgrade

## P1 – Next steps
- [x] P1‑1: `requirements.in` + hash‑pinned `requirements.txt` (pip‑compile), separate dev lock, `latest_requirements.txt` removed; CI runs the suite, `makemigrations --check`, `check --deploy` + rate‑limit tests against memcached, ruff (rule set pinned in `ruff.toml`) and weekly pip‑audit; dependabot; gitleaks pre‑commit hook (v8.30.0) – **done**; first CI run pending push
- [ ] P1‑2: Scope cookies and CSRF to the dedicated host (`__Host-` cookies, `SESSION_COOKIE_AGE`, disable HSTS preload); `CSRF_TRUSTED_ORIGINS` is already scoped to `https://list.petar-dev.com` (`7a4396f`)
- [ ] P1‑3: Close remaining rate‑limit gaps (unify destroy budget, verify IPv6 mask, test counters)
- [ ] P1‑4: Replace `logging.conf` with systemd unit and add proper Django `LOGGING` dict (journald output, log levels)
- [ ] P1‑5: Enable SQLite WAL (options in `DATABASES`) – unblocked now that the branch is on Django 5.2
- [ ] P1‑6 (optional): Implement capability URLs (UUID PK, migration, routing changes)

## P2 – Cleanup & Tests
- [ ] Fix `HttpResponseBadRequest` to use `content_type="text/plain"`
- [ ] Replace hidden `confirm=yes` input with a visible required checkbox in `detail.html`
- [ ] Optimize `list_size()` query (use `Count` annotation in admin list view)
- [ ] Normalise trailing slashes in `shoppinglist/urls.py` (consistent `APPEND_SLASH` behaviour)
- [ ] Review and correct list ordering limit (`order_by("-list_name")[:10]`)
- [ ] Remove dead PWA code and related settings/templates
- [ ] Fix `settings.py:30` whitespace split (`ALLOWED_HOSTS` stays an env var – decided 2026‑10‑19) and enforce `ADMIN_URL` trailing slash assert
- [ ] Ensure unique element IDs (remove duplicate `id="submit"` in templates)

## Test gaps to cover
- [x] Add CI job for `RateLimitConcurrencyTests` against a memcached container (P1‑1)
- [ ] `test_admin_default_path_404s` – verify admin path protection
- [ ] `test_admin_lockout_after_five_failures` – axes lockout behaviour
- [ ] `test_update_delete_shares_destroy_budget` – ensure shared destroy budget (P1‑3)
- [ ] `test_oversized_body_rejected` – validate 400 response for >256 KB payload (P0‑4)
- [ ] `test_bad_request_is_text_plain` – confirm 400 responses are plain text (P2)
- [ ] `test_cookies_are_host_prefixed` – assert `__Host-` cookie names (P1‑2)
- [ ] `test_list_size_uses_single_query` – verify list size query optimisation (P2)
- [ ] `test_admin_changelist_query_count` – check admin changelist query count (P2)
