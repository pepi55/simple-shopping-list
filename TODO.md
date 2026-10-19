# TODO – Security Hardening Roadmap

## P0 – Immediate (✓ done, ☐ pending)
- [x] P0‑1: Make rate limiting real (installed `django‑ratelimit`, middleware, memcached) – **done**
- [ ] P0‑2: Merge and deploy `agent/sec-test` branch
- [ ] P0‑3: Rotate admin password and verify/rotate `SECRET_KEY`
- [x] P0‑4: Fix the Caddyfile (dedicated host, request‑body limit, CSP header) – **done**
- [ ] P0‑5: Upgrade to Python 3.12 and Django 5.2 LTS – **repo side done** (`requirements.txt` pins Django 5.2.18, `pymemcache` restored, `uvicorn-worker`, uvloop dropped; verified: suite, `check --deploy`, pip-audit); pending: first CI run on 3.12, then the Pi runtime upgrade

## P1 – Next steps
- [x] P1‑1: Consolidate to a single `requirements.txt` with a lockfile, add CI workflow, remove `latest_requirements.txt`
- [ ] P1‑2: Scope cookies and CSRF to the dedicated host (`__Host-` cookies, adjust `CSRF_TRUSTED_ORIGINS`, disable HSTS preload)
- [ ] P1‑3: Close remaining rate‑limit gaps (unify destroy budget, verify IPv6 mask, test counters)
- [ ] P1‑4: Replace `logging.conf` with systemd unit and add proper Django `LOGGING` dict (journald output, log levels)
- [ ] P1‑5: Enable SQLite WAL (options in `DATABASES` after Django upgrade)
- [ ] P1‑6 (optional): Implement capability URLs (UUID PK, migration, routing changes)

## P2 – Cleanup & Tests
- [ ] Fix `HttpResponseBadRequest` to use `content_type="text/plain"`
- [ ] Replace hidden `confirm=yes` input with a visible required checkbox in `detail.html`
- [ ] Optimize `list_size()` query (use `Count` annotation in admin list view)
- [ ] Normalise trailing slashes in `shoppinglist/urls.py` (consistent `APPEND_SLASH` behaviour)
- [ ] Review and correct list ordering limit (`order_by("-list_name")[:10]`)
- [ ] Remove dead PWA code and related settings/templates
- [ ] Fix `settings.py:30` whitespace split and enforce `ADMIN_URL` trailing slash assert
- [ ] Ensure unique element IDs (remove duplicate `id="submit"` in templates)

## Test gaps to cover
- [ ] Add CI job for `RateLimitConcurrencyTests` against a memcached container (P1‑1)
- [ ] `test_admin_default_path_404s` – verify admin path protection
- [ ] `test_admin_lockout_after_five_failures` – axes lockout behaviour
- [ ] `test_update_delete_shares_destroy_budget` – ensure shared destroy budget (P1‑3)
- [ ] `test_oversized_body_rejected` – validate 400 response for >256 KB payload (P0‑4)
- [ ] `test_bad_request_is_text_plain` – confirm 400 responses are plain text (P2)
- [ ] `test_cookies_are_host_prefixed` – assert `__Host-` cookie names (P1‑2)
- [ ] `test_list_size_uses_single_query` – verify list size query optimisation (P2)
- [ ] `test_admin_changelist_query_count` – check admin changelist query count (P2)
