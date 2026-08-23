# TODO — `simple-shopping-list` Security Hardening

Phased plan distilled from
`simple-shopping-list/analyze-the-project-in-deep-hearth.md`. Time budgets per
phase are estimates, not commitments. Owner decisions are settled; not
revisited here.

> **Residual risk, stated once:** an open write-enabled endpoint on the public
> internet can be filled with junk or wiped by anyone who finds it. These
> controls bound the damage and make abuse slow and noisy; they cannot prevent
> it. If this data starts to matter, revisit auth.

---

## P0 — Do first (~6–9 h)

- [ ] **P0-1. Terminate TLS behind Caddy, rebind gunicorn to loopback** — ~2 h *(code complete; router repoint pending)*
  - [x] Set up Caddy with automatic Let's Encrypt issuance/renewal
        (~10-line config).
  - [x] Rebind `gunicorn_conf.py:3` from `Pie3:8080` to `127.0.0.1:8080`.
  - [ ] Repoint router forward at Caddy:443. **App must not remain reachable
        on `:8080`** (otherwise every other control is bypassed by hitting
        the origin directly). *(deployment-side; verify on the box)*
  - [x] `settings.py` — replace the explicit `CSRF_COOKIE_SECURE = False`
        at line 26 with:
        ```python
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        SECURE_SSL_REDIRECT = True
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = 60          # raise to 31536000 after a week clean
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        CSRF_TRUSTED_ORIGINS = ["https://petar-dev.com", "https://*.petar-dev.com"]
        SESSION_COOKIE_SAMESITE = "Lax"
        CSRF_COOKIE_SAMESITE = "Lax"
        ```
  - [x] Ensure Caddy **unconditionally overwrites** `X-Forwarded-Proto`
        (otherwise a client can spoof it and Django trusts a plaintext
        request as secure).
  - [x] Set `FORWARDED_ALLOW_IPS=127.0.0.1` — never `*` (otherwise
        `X-Forwarded-For` becomes spoofable and per-IP rate limits
        collapse into one bucket).
  - [x] Move `ALLOWED_HOSTS` to an env var; drop hardcoded IPs.

- [ ] **P0-2. Harden `/admin/`** — ~45 min
  - [ ] **Rotate the admin password now** (transmitted in cleartext over
        public internet on every login to date).
  - [ ] Install `django-axes`: `AXES_FAILURE_LIMIT = 5`,
        `AXES_COOLOFF_TIME = 1`. Wire `INSTALLED_APPS`,
        `AXES_MIDDLEWARE`, `AUTHENTICATION_BACKENDS`.
  - [ ] Move off default path: `path(os.environ["ADMIN_URL"],
        admin.site.urls)` — fail-fast if unset.
  - [ ] Caddy rate limit on the login path.
  - [ ] One superuser only, strong passphrase.
  - [ ] *(Optional, noted not decided)*: IP-allowlist `/admin/*` at Caddy
        to LAN/Tailscale range (~4 lines; reduces internet-facing
        credential surface to zero).

- [ ] **P0-3. `@require_POST` + confirmation on destructive endpoints**
      — ~1 h
  - [x] `@require_POST` on `update`, `delete`, `add`. *(done as an explicit
        `method != "POST"` check returning 403 instead of the decorator's
        405; POST-only contract holds)*
  - [ ] `@require_safe` on `index`, `detail`.
  - [ ] `delete` additionally requires a `confirm` field (defeats replayed
        stale POSTs).
  - [ ] Un-comment `detail.html:54-60` with the `confirm` input, or drop
        the route.
  - [ ] Add `robots.txt` with `Disallow: /` and `X-Robots-Tag: noindex`
        at the proxy (free; not the control — `require_POST` is).
        *(X-Robots-Tag is set in the Caddyfile; robots.txt still missing)*

- [ ] **P0-4. Unbounded `item_name` + input validation via `ModelForm`**
      — ~2 h *(note: `views.py:add` gained ad-hoc validation — missing
      fields and non-positive/non-numeric quantity are rejected — but the
      ModelForm/limit work below is not done)*
  - [ ] New file `shoppinglist/forms.py` with `AddItemForm`
        (`ModelForm` for `ShoppingItem`, fields `item_name`/`quantity`)
        and `ItemActionForm` (`ModelMultipleChoiceField` bound to
        `shopping_list.shoppingitem_set`).
  - [ ] `MAX_ITEMS_PER_LIST = 200` enforced in `AddItemForm.clean()`.
  - [ ] `AddItemForm.clean_item_name()` strips whitespace and rejects
        empty.
  - [ ] `views.py` — wire `AddItemForm` and `ItemActionForm` in place of
        raw `request.POST[...]` access.
  - [ ] `models.py:15` — add `MinValueValidator(1)`,
        `MaxValueValidator(999)` to `quantity`. **Requires migration
        `0003`.**
  - [ ] Storage is then bounded by construction: 200 items × 200 chars ×
        admin-controlled list count.

- [ ] **P0-5. Per-IP rate limiting on writes** — ~1 h
  - [ ] Install `django-ratelimit`.
  - [ ] `@ratelimit(key="ip", rate="20/m", block=True)` on add/update;
        `@ratelimit(key="ip", rate="5/m", block=True)` on delete.
  - [x] `gunicorn_conf.py` — set `workers = 1` (correct anyway on Pi +
        SQLite given write contention).
  - [ ] Configure `FileBasedCache` for django-ratelimit (default
        `LocMemCache` would multiply the real limit by N workers). **Do
        not use `DatabaseCache`** (same SQLite file = lock contention).
  - [ ] Set `RATELIMIT_VIEW` for a friendly 429 instead of a bare 403.

- [ ] **P0-6. Rotate both leaked `SECRET_KEY` values** — ~45 min
  - [ ] Compare the live `SECRET_KEY` env value on the box against both
        leaked literals (commits `2eeaf33`/`040c09d`/`bfeace7` and
        `8064984`/`v2.1.0`). **Match = active compromise, not historical.**
  - [ ] Generate a new key (`README.md:4` documents the command).
  - [ ] Store in `/etc/simple-shoppinglist.env`, `chmod 600`.
  - [ ] Systemd `EnvironmentFile=` delivers it (see P1-4); then drop
        `python-dotenv` (declared dep, never imported).
  - [ ] Restart. Only admin sessions invalidate.
  - [ ] Run `gitleaks detect` over full history once.
  - [ ] Add `gitleaks` as a pre-commit hook.
  - [ ] **Do not rewrite git history** (public clones; secret scanners
        already indexed it; rotation makes the value worthless, which is
        the actual goal).

---

## P1 — Next (~6–8 h)

- [ ] **P1-1. Python 3.12 + Django 5.2 LTS** — ~3 h
  - [ ] Preferred: Docker (`python:3.12-slim`, arm64). Decouples runtime
        from OS; rollback = tag change.
  - [ ] Alternatives if no Docker: Trixie (3.13), Bookworm (3.11).
  - [ ] `python -Wa manage.py test` to surface deprecations.
  - [ ] Upgrade uvicorn ≥ 0.30 and httptools (3 years stale; these are
        the parsers actually on the request path under
        `UvicornWorker`, not gunicorn). *(done: uvicorn 0.52.x,
        httptools 0.8.x in `requirements.txt`)*
  - [x] Upgrade gunicorn (not urgent — off the request path under
        `UvicornWorker`; but stale). *(now 26.1.0)*
  - [ ] Budget: `uvloop`/`httptools` compile from source on ARM, or just
        drop `uvloop` (no value at this traffic).

- [ ] **P1-2. One requirements file, a lockfile, audit tooling** — ~1.5 h
  - [x] Delete `latest_requirements.txt` (the conventionally-named
        `requirements.txt` must be the live one).
  - [ ] `requirements.in` — direct deps with floors:
        `Django>=5.2,<5.3`, `gunicorn>=23`,
        `uvicorn[standard]>=0.30`, `whitenoise>=6.7`,
        `django-ratelimit>=4.1`.
  - [ ] `requirements.txt` — `pip-compile --generate-hashes`; install
        with `--require-hashes`.
  - [ ] `requirements-dev.in` — pytest, pytest-django, ruff, pip-audit,
        pre-commit, gitleaks.
  - [x] Drop `django-pwa==1.1.0` (disabled at `settings.py:44` and
        `urls.py:25`, unmaintained) and delete dead `PWA_*` block at
        `settings.py:132-161`.
  - [ ] Drop `python-dotenv` (never imported). *(still in
        `requirements.txt`)*
  - [ ] Add `pip-audit` on push **and** weekly cron (so a CVE published
        against a frozen repo still reaches you).
  - [ ] Add dependabot for pip and actions.
  - [ ] `ruff check` in CI (catches `models.py:19` `NameError` in 200 ms).
  - [ ] `manage.py check --deploy --fail-level WARNING` as a CI gate
        (permanently enforces every setting from P0-1).

- [ ] **P1-3. SQLite concurrency** — ~30 min
  - [ ] `DATABASES["default"]["OPTIONS"] = {"timeout": 20,
        "init_command": "PRAGMA journal_mode=WAL;"}`.
  - [ ] Wrap multi-item `update` view in `transaction.atomic()`.

- [ ] **P1-4. Replace `logging.conf` with systemd + Django `LOGGING`** — ~1 h
  - [ ] Delete `logging.conf`; drop `--log-config` from `run.sh:1`.
  - [ ] Log to stdout/stderr under a systemd unit with:
        `EnvironmentFile=/etc/simple-shoppinglist.env`,
        `Restart=on-failure`, `MemoryMax=512M`,
        `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`.
  - [ ] Move `db.sqlite3` out of `BASE_DIR` (`settings.py:85`) to
        `/var/lib/simple-shoppinglist/` so `ProtectSystem=strict` can
        make the code tree read-only.
  - [ ] Add a `LOGGING` dict in `settings.py` routing `django.request`
        at `ERROR` to stderr (today, with `DEBUG=False` and no
        `ADMINS`, unhandled 500s go nowhere durable).
  - [ ] *(Optional upgrade: but solves P0-6 delivery — see P0-6.)*

- [ ] **P1-5. Capability URLs — decide explicitly, do not half-do** —
      All-or-nothing. Either:
      - [ ] swap integer PK for `UUIDField` AND drop the enumerating
            index (lists shareable-by-link only), **or**
      - [ ] keep enumeration and rely on the P0 controls.
      - [ ] Document the decision. (Migration + broken bookmarks if
            chosen.)

---

## P2 — Cleanup (~1–2 h)

- [ ] `models.py:7` — `len(self.shoppingitem_set.all())` → `.count()`.
      Replace `ListAdmin.list_display` (`admin.py:12`) `len` call with
      `get_queryset().annotate(_size=Count("shoppingitem"))` +
      `@admin.display(ordering="_size")` (fixes N+1, makes column
      sortable).
- [ ] `models.py:18-19` — delete `bought_all()` (references undefined
      `quantity` → `NameError`; unreferenced; its existence is evidence
      for the `ruff` CI gate).
- [ ] `views.py:40-41` and `views.py:30` — per-row `.delete()` loops
      → single bulk queries.
- [ ] `detail.html:44` — `value="{{ list.id }}"` references undefined
      `list` (context var is `shoppinglist`); disappears once rendered
      from `AddItemForm`.
- [ ] `urls.py:10-12` — normalise trailing slashes (with
      `APPEND_SLASH`, a mistyped URL redirects a POST and **silently
      discards the body**).
- [ ] `views.py:10` — add pagination; `order_by("-list_name")[:10]`
      silently truncates with no pagination; descending name order is
      probably unintended.
- [ ] `views.py:48` unused `new_item`; `views.py:2` unused
      `Http404`/`HttpResponse` after refactor.
- [x] `README.md:5-7` — documents binding gunicorn to a network
      interface with no proxy/TLS; update or someone will follow it.
      *(rewritten: documents the loopback bind + Caddy TLS setup and
      required env vars)*

---

## Test suite — write alongside P0, not after

`shoppinglist/tests.py` is an untouched 3-line stub; no regression net
exists for any change above. Write these **first** so they
demonstrably flip fail → pass. Split into
`tests/test_views.py`, `test_forms.py`, `test_models.py`,
`test_security.py`.

**Destructive-method safety (P0-3)**
- [ ] `test_delete_bought_rejects_get` — 405, item count unchanged
      *(crawler-scenario regression)*.
- [ ] `test_delete_bought_rejects_post_without_confirmation` — valid
      CSRF, no `confirm` → 400.
- [ ] `test_delete_bought_requires_csrf_token` —
      `Client(enforce_csrf_checks=True)` → 403.
- [ ] `test_update_rejects_get`, `test_add_rejects_get` — 405, not
      500.

**Input validation (P0-4)**
- [ ] `test_add_rejects_overlong_item_name` — 5,000 chars → 400 **and
      assert no row was created** (the row-count assertion is the
      whole point; naive implementation on SQLite returns 200 and
      stores it).
- [ ] `test_add_rejects_non_numeric_quantity` → 400, not 500.
- [ ] `test_add_rejects_negative_quantity`,
      `test_add_rejects_quantity_above_max`.
- [ ] `test_add_rejects_blank_and_whitespace_only_name`,
      `test_add_missing_fields_returns_400_not_500`.
- [ ] `test_add_enforces_max_items_per_list` — 201st add → 400.

**Exception handling (`views.py:25-26`)**
- [ ] `test_update_with_non_numeric_item_id` → 400
      *(the exact `ValueError` regression)*.
- [ ] `test_update_with_item_id_from_another_list` → 400 **and the
      other list's item is untouched.**
- [ ] `test_update_with_no_action_key` /
      `test_update_with_both_action_keys` → 400.
- [ ] Happy paths: `test_update_marks_selected_items_bought`,
      `test_update_deletes_selected_items`.

**Security settings (P0-1) — stay green forever**
- [ ] `test_deploy_checks_pass` —
      `call_command("check", "--deploy", "--fail-level=WARNING")`.
      Covers all four cookie/HSTS settings in one test.
- [ ] `test_secret_key_not_hardcoded` — from env, and explicitly **not
      equal to either leaked literal.** The only automated guard
      against the P0-6 reuse scenario.
- [ ] `test_debug_is_false`, `test_csrf_token_present_on_all_forms`.

**Rate limiting (P0-5)**
- [ ] `test_add_is_rate_limited`,
      `test_delete_has_stricter_rate_limit`.
- [ ] `test_rate_limit_is_per_ip` — two `REMOTE_ADDR`s get
      independent budgets. Guards against the P0-1 proxy
      misconfiguration collapsing everyone into one bucket.

**Models / templates (P2)**
- [ ] `test_list_size_uses_single_query` (`assertNumQueries(1)`),
      `test_admin_changelist_query_count` with 20 lists.
- [ ] `test_no_unescaped_output` — a list named
      `<script>alert(1)</script>` renders escaped. Clean today;
      keeps it that way (autoescaping is the *only* XSS defence and
      it's implicit).

---

## Verification

- [ ] `python manage.py test shoppinglist` — green. Confirm the P0
      cases fail against current `main` first.
- [ ] `python manage.py check --deploy` — zero issues (today: warns
      on all four cookie/HSTS settings).
- [ ] Original bugs, by hand:
  - [ ] `curl -i http://host/1/delete` → **405** (today: silently
        deletes every bought item).
  - [ ] `curl -i -X POST http://host/1/add -d "name=$(python -c
        'print("A"*5000)')&quantity=1"` → **400**, no row created
        (today: 200, 5 KB stored).
  - [ ] `curl -i -X POST http://host/1/add -d 'name=x&quantity=abc'`
        → **400** (today: 500).
  - [ ] `curl -i -X POST http://host/1/update -d 'item=abc&update=1'`
        → **400** (today: 500).
- [ ] TLS: `curl -I http://host/` → 301 https; `curl -I https://host/`
      shows HSTS; `:8080` **not reachable off-box.**
- [ ] Admin: old path 404s; 5 bad logins trigger an axes lockout.
- [ ] Rate limit: 21 rapid adds → 429 on the 21st; two source IPs get
      separate budgets.
- [ ] `pip-audit -r requirements.txt` clean; `django.__version__` →
      5.2.x; `python --version` → 3.12.x.
- [ ] Key rotation: a pre-rotation admin session cookie is rejected.
- [ ] Logs land in journald, not `/tmp`; `journalctl --disk-usage`
      bounded.

---

## Sequencing

| Window | Work | Notes |
|---|---|---|
| **1** (~4 h) | P0-1 (TLS/proxy), P0-2 (admin), P0-6 (key + admin-password rotation) | Deployment-side only. No code changes, no app rollback risk. |
| **2** (~4 h) | P0-3, P0-4, P0-5 — one branch with their tests | **Do not split.** They share `forms.py` and the views refactor. |
| **3** (~4 h) | P1-1 (runtime), P1-2 (deps), P1-4 (systemd) | Window 2's tests are what make the upgrade safe — that's why it's P1, not P0. |
| **4** (~2 h) | P2 cleanup + explicit go/no-go on P1-5 (capability URLs) | |

---

## Commit policy

Per `CLAUDE.md`, this is not a worktree, so commits will be packaged
into an executable `commit.sh` at the repo root (one commit per
logical change, Conventional-Commit messages, trailers). Run it
outside the sandbox.
