# Security Hardening — simple-shopping-list

_Revised 2026-10-13 against branch `agent/sec-test` @ `2eea816`. All line references are to that
branch; `main` (`491f4f5`) still carries the pre-fix code._

## Context

`simple-shopping-list` is a Django 4.2 app served by gunicorn + uvicorn on a Pi and exposed to the
public internet. Injection hygiene is good: the ORM is used throughout, templates rely on default
autoescaping, and every item lookup is scoped to its parent list. **There is no SQLi, no XSS, and no
cross-list IDOR.**

The first round of fixes landed as six commits on `agent/sec-test` (`d3a84d2`..`2eea816`): TLS
settings, loopback bind, `django-axes`, env-driven admin path, POST-only writes, `ModelForm`
validation, per-IP rate limiting, and a 45-test suite. **None of it is merged or deployed.** The
biggest risk today is the gap between that branch and what the Pi actually runs, followed by a
runtime that has been out of support for months.

**Owner decisions constraining this plan** (settled; not revisited):

| Decision | Choice |
|---|---|
| Authentication | **Stays open.** No login, no accounts, no owner FK. |
| Exposure | Internet-facing. |
| TLS | Reverse proxy (Caddy) with Let's Encrypt. |
| `/admin/` | Keep it, hardened: TLS, moved path, brute-force lockout. |
| Runtime | Python 3.12 + Django 5.2 LTS. |
| Scope | Security + correctness bugs + test suite. |

With auth off the table, the threat model is **destruction, abuse, and availability** — not
confidentiality. Lists can still only be created through the admin, so anonymous users can grow the
item table (now capped at 200 items × 200 chars per list) but not the list table.

> **Residual risk, stated once:** an open write-enabled endpoint on the public internet can be
> filled with junk or wiped by anyone who finds it. The controls below bound the damage and make
> abuse slow and noisy; they cannot prevent it. If this data starts to matter, revisit auth.

---

## Where things stand

| Area | State | Evidence |
|---|---|---|
| TLS settings, `SECURE_PROXY_SSL_HEADER`, secure cookies, HSTS (60 s) | ✅ on branch | `settings.py:36-52` |
| gunicorn on loopback, `workers = 1`, `forwarded_allow_ips = '127.0.0.1'` | ✅ on branch | `gunicorn_conf.py:5,13,20` |
| `ALLOWED_HOSTS` from env | ✅ on branch | `settings.py:30` |
| `django-axes` (5 failures, 1 h cool-off) | ✅ on branch | `settings.py:65,76,83-88` |
| Admin path from `ADMIN_URL`, fail-fast | ✅ on branch | `simple_shoppinglist/urls.py:33` |
| `robots.txt` + `X-Robots-Tag: noindex` | ✅ on branch | `simple_shoppinglist/urls.py:25-26`, `Caddyfile:4` |
| `@require_POST` / `@require_safe`, CSRF on all three forms | ✅ on branch | `views.py:20-70`, `detail.html` |
| `AddItemForm` / `ItemActionForm`, 200-item cap | ✅ on branch | `forms.py` |
| `quantity` bounded 1–256 + migration `0003` | ✅ on branch | `models.py:16-19` |
| `django-ratelimit` 20/m writes, 5/m bulk delete, 429 view, `FileBasedCache` | ✅ on branch, with gaps (P1-3) | `views.py:12-17`, `settings.py:96-102` |
| Bulk queries instead of per-row loops; `bought_all()` removed | ✅ on branch | `views.py:49-52,64` |
| Test suite (45 tests) | ⚠️ written, **not run here** — see Test suite | `shoppinglist/tests/` |
| Merged to `main` and deployed | ❌ | P0-1 |
| Admin password / `SECRET_KEY` rotation | ❌ not verifiable from the repo | P0-2 |
| Caddy config | ⚠️ present but broken for the wildcard, no login throttle | P0-3 |
| Python 3.12 / Django 5.2 | ❌ still Python 3.9.25, `Django==4.2.4` | P0-4 |
| Lockfile, CI, `pip-audit`, `latest_requirements.txt` removed | ❌ | P1-1 |
| systemd, `logging.conf` → journald, Django `LOGGING` | ❌ `run.sh:1` still logs to `/tmp` | P1-4 |
| SQLite WAL | ❌ | P1-5 |

---

## P0 — Do first (~6–8 h)

### ☐ P0-1. Merge and deploy `agent/sec-test` — ~1.5 h

Until this ships, every original finding is still live. This file has been public on `origin/main`
since `491f4f5`, and the previous revision included working `curl` reproductions against the
running app. A roadmap of unpatched holes on a public repo shortens the window you can afford. Open
the PR, merge it, then on the Pi:

1. Run the test suite **on the Pi first**. It has never been seen green (see Test suite).
2. `pip install -r requirements.txt`. This pulls in `django-axes` and `django-ratelimit`, which the
   running code doesn't have yet.
3. Set the newly required env vars `ALLOWED_HOSTS` and `ADMIN_URL` (with a trailing slash). Without
   them the app now fails to start, and it should.
4. `python manage.py migrate`. This creates the axes tables. `0003` is validators-only and emits no
   SQL.
5. `python manage.py check --deploy --fail-level WARNING` with the real env.
6. Point the router's port forward at Caddy on 80/443 and **remove the `:8080` forward**. Then
   confirm from off-box that `:8080` refuses connections.
7. **Clean up what the old hole already let in.** The new validators only apply to new writes. Rows
   stored through the unvalidated `add` view stay, and the admin will refuse to re-save them:
   ```python
   from django.db.models.functions import Length
   ShoppingItem.objects.annotate(n=Length("item_name")).filter(n__gt=200)
   ShoppingItem.objects.exclude(quantity__range=(1, 256))
   ```
   Also check `du -h db.sqlite3` against what a shopping list should weigh.

### ☐ P0-2. Rotate the admin password and verify/rotate `SECRET_KEY` — ~45 min

This step is deployment-only, and nothing in the repo shows whether it was done.

- **Admin password first.** It crossed the public internet in cleartext on every login before TLS.
  Use one superuser with a long passphrase.
- **`SECRET_KEY`: verify before rotating.** Two literals sit in public history (`2eeaf33`..`bfeace7`,
  and `8064984`, which reverted the env lookup back to a literal before `42aa86a` undid it). Both
  are listed in `tests/test_security.py:11-14`. Compare the live env value against them. A match
  means the key is compromised right now, not just leaked in the past, and the admin sessions and
  password-reset tokens it signs should be treated as forgeable.
- Generate a new key (`README.md:6-7`) and store it in `/etc/simple-shoppinglist.env` with mode 600,
  loaded by systemd (P1-4). `python-dotenv` is still declared (`requirements.txt:13`) but never
  imported, so nothing loads a `.env` today.
- **Do not rewrite git history.** The repo is public and has been cloned and indexed. Rotation is
  what makes the values worthless. Run `gitleaks detect` over full history once; a pattern scan
  found nothing beyond the two known keys, and no `db.sqlite3`, `.env` or log file has ever been
  committed.

### ☐ P0-3. Fix the Caddyfile — ~1.5 h

**New findings.** `Caddyfile:1` serves `petar-dev.com, *.petar-dev.com`:

- **The wildcard can't get a certificate as written.** Let's Encrypt only issues wildcards via the
  DNS-01 challenge, which needs a Caddy DNS-provider module and a `tls { dns … }` block. Neither is
  present. Once that is fixed, the opposite problem appears: every subdomain without its own site
  block is routed to the shopping list, including names meant for your other Pi services.
- **It drags the apex into the app's security policy.** With the app on the apex,
  `SECURE_HSTS_INCLUDE_SUBDOMAINS` (`settings.py:44`) forces HTTPS on every `*.petar-dev.com` host.
  `SECURE_HSTS_PRELOAD` (`settings.py:49`) invites a near-irreversible preload submission for the
  whole domain. The wildcard `CSRF_TRUSTED_ORIGINS` (`settings.py:50`) is P1-2.

Give the app a dedicated host and bound the request body at the proxy:

```caddy
list.petar-dev.com {
    encode gzip

    # Django buffers up to DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB) and CsrfViewMiddleware parses the
    # body *before* the rate-limit decorator runs, so a blocked request still costs a full parse.
    request_body {
        max_size 256KB
    }

    header {
        X-Robots-Tag "noindex"
        Content-Security-Policy-Report-Only "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    }

    reverse_proxy 127.0.0.1:8080
}
```

Then set `ALLOWED_HOSTS=list.petar-dev.com` and mirror the cap in Django with
`DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024`.

- **`header_up X-Forwarded-Proto {scheme}` (`Caddyfile:21`) is redundant.** Caddy already sets it,
  and it discards client-supplied `X-Forwarded-*` unless `trusted_proxies` is configured. That
  discarding is what makes `SECURE_PROXY_SSL_HEADER`, uvicorn's proxy-header handling and axes' IP
  detection trustworthy. **Never add `trusted_proxies` to this block.**
- **CSP is new and starts in report-only.** Autoescaping is currently the only XSS defence. The one
  inline style in the app is `forms.py:13` (`style="width: 3em;"`); move it to `style.css` as a
  class. The admin templates also use some inline styles. Check the browser console for a week,
  then switch to the enforcing `Content-Security-Policy` header.
- **The admin login throttle is still commented out** (`Caddyfile:9-18`). It needs a Caddy built
  with `caddy-ratelimit` (`xcaddy build --with github.com/mholt/caddy-ratelimit`). Until then, axes
  is the only control, and it locks out per IP, so a distributed guesser gets 5 tries per IP per
  hour. The passphrase from P0-2 is what actually holds. IP-allowlisting the admin path to your
  LAN/Tailscale range remains the ~4-line upgrade that removes the surface entirely.

### ☐ P0-4. Python 3.12 + Django 5.2 LTS — ~3 h

**Promoted from P1.** It was deferred until a test suite existed, and the suite now exists. The
runtime is now the largest unpatched surface on the request path:

| Component | Pinned | Status on 2026-10-13 |
|---|---|---|
| Python | 3.9.25 | EOL since October 2025 — a year without security fixes |
| Django | `4.2.4` (`requirements.txt:4`) | 4.2 LTS EOL April 2026, and `.4` misses every 4.2.x security release since August 2023 |
| uvicorn + httptools | `0.23.2` / `0.6.0` | The HTTP parser that actually faces Caddy; three years stale |
| h11 | `0.14.0` | CVE-2025-43859 (chunked-encoding smuggling, fixed in 0.16). Uvicorn picks httptools when it's installed, but h11 becomes the parser the moment httptools fails to build on ARM |
| gunicorn | `21.2.0` | CVE-2024-1135 / CVE-2024-6827 are in gunicorn's own parser, which is **off the request path** under `UvicornWorker`. Upgrade anyway |
| django-axes, django-ratelimit | `6.5.0`, `4.1.0` | Bump both to releases that declare Django 5.2 support |

Django 5.2 LTS is supported to April 2028 and needs Python ≥ 3.10, so the target is forced. The
preferred route is still Docker (`python:3.12-slim`, arm64): rollback is a tag change, and future
upgrades stop being OS upgrades. Drop `uvloop`, which buys nothing at this traffic. For this
codebase the 4.2 → 5.2 risk is near zero: five function views, two models, no custom middleware.
Run `python -Wa manage.py test` to surface deprecations.

---

## P1 — Next (~5–7 h)

### ☐ P1-1. One requirements file, a lockfile, and CI — ~2 h

- Delete `latest_requirements.txt`. It pins `Django==5.0.7`, which went EOL in April 2025, and sits
  next to the conventionally-named `requirements.txt` that every tool actually reads.
  `requirements.txt` itself was hand-edited (axes and ratelimit appended to an old freeze), not
  resolved.
- Add `requirements.in` with floors (`Django>=5.2,<5.3`, `uvicorn[standard]`, `gunicorn>=23`,
  `whitenoise`, `django-axes`, `django-ratelimit`). Generate `requirements.txt` with
  `pip-compile --generate-hashes` and install with `--require-hashes`. Put the dev tools in
  `requirements-dev.in`.
- Drop `django-pwa` (`requirements.txt:6`) and `python-dotenv` (`requirements.txt:13`).
- There is still no `.github/`. Add a workflow that **runs the test suite**, which is the only way
  it will ever be verified. Also run `manage.py check --deploy --fail-level WARNING`,
  `manage.py makemigrations --check --dry-run` (`0003` was written by hand), `ruff check`, and
  `pip-audit` on push plus a weekly cron. Add dependabot for pip and actions, and a `gitleaks`
  pre-commit hook.

### ☐ P1-2. Scope cookies and CSRF to this host — ~45 min

**New finding.** `CSRF_TRUSTED_ORIGINS = ["https://petar-dev.com", "https://*.petar-dev.com"]`
(`settings.py:50`) makes every sibling subdomain a trusted CSRF origin. Siblings are *same-site*, so
`SameSite=Lax` doesn't stop them either. A sibling can also set a `csrftoken` cookie for
`.petar-dev.com` (cookie tossing) and complete Django's double-submit check. This needs an XSS or a
dangling-DNS takeover on any `petar-dev.com` host. The prize is CSRF against a logged-in **admin**
session: delete every list, or create a superuser.

```python
# CSRF_TRUSTED_ORIGINS removed: it is only needed when Origin != Host, and Caddy forwards the
# original Host, so same-origin form posts already pass.
CSRF_COOKIE_NAME = "__Host-csrftoken"     # browsers refuse __Host- cookies set with a Domain
SESSION_COOKIE_NAME = "__Host-sessionid"  # attribute, which defeats tossing from a sibling
SESSION_COOKIE_AGE = 8 * 3600             # the admin is the only session user; default is 2 weeks
```

Also decide on preload. Set `SECURE_HSTS_PRELOAD = False` and silence `security.W021` in
`SILENCED_SYSTEM_CHECKS` with a comment, unless you really intend to preload all of `petar-dev.com`.
Once the app lives on `list.petar-dev.com`, preload doesn't apply to it anyway. Raise
`SECURE_HSTS_SECONDS` to a year once a week of clean operation has passed.

### ☐ P1-3. Close the rate-limit gaps — ~1 h

**New findings**, in what landed in `c2060b9`:

- **The more destructive path got the looser limit.** "Remove Selected" (`detail.html:30`) posts to
  `update`, which deletes any selected items, bought or not, in one request at `WRITE_RATE` = 20/m
  (`views.py:35,49-50`). The bought-only cleanup in `delete` gets `DESTROY_RATE` = 5/m. Give both
  one shared budget: `@ratelimit(group="destroy", …)` on `delete`, and
  `django_ratelimit.core.is_ratelimited(request, group="destroy", key="ip", rate=DESTROY_RATE,
  increment=True)` inside the `is_delete` branch.
- **`FileBasedCache` culls a third of its entries once it reaches `MAX_ENTRIES` (default 300).**
  Under traffic from many addresses, that randomly resets live counters. Set
  `"OPTIONS": {"MAX_ENTRIES": 10000}` (`settings.py:96-101`).
- **Per-IP limits are only as strong as an attacker's address supply.** django-ratelimit buckets
  IPv6 per /64, and one home connection usually gets a /56 or /48. The 200-item-per-list cap is the
  real storage bound; rate limiting just makes abuse slow and noisy.
- After deploying, confirm the counters and axes see real client IPs and not `127.0.0.1`: trigger a
  lockout, then look at `axes_accessattempt.ip_address`.

### ☐ P1-4. systemd instead of `logging.conf`, plus Django `LOGGING` — ~1 h

This item is unchanged and still open. `run.sh:1` passes `--log-config ./logging.conf`, which writes
unrotated `FileHandler` logs to `/tmp/gunicorn.{error,access}.log` (`logging.conf:34,39`). On a Pi,
`/tmp` is often tmpfs, so the logs eat RAM. It also silently overrides `errorlog`/`accesslog` in
`gunicorn_conf.py:6-7`.

Delete `logging.conf` and drop `--log-config`. Run under a systemd unit with:

- `EnvironmentFile=/etc/simple-shoppinglist.env`, `Restart=on-failure`, `MemoryMax=512M`
- `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict`
- `StateDirectory=simple-shoppinglist` for `db.sqlite3` (now `settings.py:131`)
- `CacheDirectory=simple-shoppinglist` for the ratelimit cache, which now also lives in `BASE_DIR`
  (`settings.py:99`)

Both must leave `BASE_DIR` for `ProtectSystem=strict` to make the code tree read-only. That also
closes a quiet risk: `FileBasedCache` stores pickles, so any write access to the code tree is code
execution.

There is still **no `LOGGING` dict**. With `DEBUG = False` and no `ADMINS`, 500s and axes lockouts go
nowhere durable. Route `django.request` at `ERROR` and `axes` at `WARNING` to stderr, which systemd
sends to journald.

### ☐ P1-5. SQLite concurrency — ~20 min, **after P0-4**

`DATABASES` (`settings.py:128-133`) has no options, so concurrent writes can still produce
`database is locked` 500s. The previous revision's `init_command` snippet **only works on
Django ≥ 5.1**; on 4.2 the sqlite3 backend rejects it. After the upgrade:

```python
"OPTIONS": {
    "timeout": 20,
    "transaction_mode": "IMMEDIATE",
    "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
},
```

The earlier `transaction.atomic()` advice is no longer needed. `update` is now a single bulk
statement (`views.py:49-52`), which is already atomic.

### ☐ P1-6. Optional — capability URLs. **Decide explicitly, don't half-do it.**

This decision is unchanged. Swapping the integer PK for a `UUIDField` makes lists shareable by link
only, but only if the index stops listing them (`index.html:20-22`). Otherwise the index hands every
capability to every visitor. It's a UX call, needs a migration, and breaks existing bookmarks.

---

## P2 — Cleanup (~1–2 h)

- **`views.py:75`**: `HttpResponseBadRequest(form.errors.as_text())` sends unescaped error text as
  `text/html`. None of today's messages echo user input, but any future `ChoiceField`'s
  `invalid_choice` message would turn this into reflected XSS. Pass `content_type="text/plain"`
  here and in the other `HttpResponseBadRequest` / 429 responses.
- **`detail.html:56`**: the cleanup "confirmation" is a hidden `confirm=yes` input, so every
  submission carries it and it confirms nothing. `@require_POST` + CSRF is the real control, which
  is fine. If you want an actual confirmation without JavaScript (and CSP-clean), make it a visible
  `required` checkbox.
- **`models.py:7-8`**: `list_size()` is `len(self.shoppingitem_set.all())`, which is N+1 across the
  admin changelist (`admin.py:12`). Annotate `Count("shoppingitem")` in `ListAdmin.get_queryset()`
  and use `@admin.display(ordering=…)`.
- **`shoppinglist/urls.py:9-12`**: trailing slashes are inconsistent. With `APPEND_SLASH`, a POST
  to a mistyped URL is redirected and silently loses its body. Normalise them.
- **`views.py:22`**: `order_by("-list_name")[:10]` silently hides every list past the tenth, in
  reverse alphabetical order.
- **Dead PWA code**: `settings.py:123,178-207`, `static/shoppinglist/js/serviceworker.js`, the empty
  `templates/shoppinglist/manifest.json`, and the commented `pwa` lines in `settings.py:66`,
  `simple_shoppinglist/urls.py:36` and `index.html:3,6`.
- **`settings.py:30`**: `.split(",")` doesn't strip whitespace, so `"a.com, b.com"` silently drops
  `b.com`. It fails closed, but confusingly. Also have `urls.py:33` assert that `ADMIN_URL` ends
  with `/`.
- **`detail.html:46,57`**: two elements share `id="submit"`.

---

## Test suite

**Status:** `shoppinglist/tests/` now has 45 tests across `test_forms.py`, `test_models.py`,
`test_security.py` and `test_views.py`. They cover every P0 regression from the previous revision.
**I could not run them.** The checked-in `venv/` contains only pip and setuptools, no Django install
exists anywhere on the dev box, and PyPI was unreachable from the sandbox. The `cpython-39.pyc` files
next to them only prove they were compiled, not that they passed. Treat the suite as unverified
until it is green on the Pi (P0-1) and in CI (P1-1).

Gaps to fill alongside P0-3 and P1:

- `test_admin_default_path_404s`, and `test_admin_lockout_after_five_failures` (axes), posting to
  `reverse("admin:login")`.
- `test_update_delete_shares_destroy_budget`: the 6th "Remove Selected" in a minute → 429 (P1-3).
- `test_oversized_body_rejected`: a body over `DATA_UPLOAD_MAX_MEMORY_SIZE` → 400 (P0-3).
- `test_bad_request_is_text_plain` (P2).
- `test_cookies_are_host_prefixed`: assert the `Set-Cookie` names from a GET to the detail page
  (P1-2).
- `test_list_size_uses_single_query` and `test_admin_changelist_query_count` (P2), carried over.

`RateLimitTests` swaps in `LocMemCache`, so the production `FileBasedCache` config (including
`MAX_ENTRIES`) is never exercised. That's acceptable, but keep it in mind.

---

## Verification (after P0)

1. `python manage.py test shoppinglist` is green **on the Pi**, then in CI.
2. `python manage.py check --deploy --fail-level WARNING` reports zero issues with the production
   env.
3. Behaviour against the deployed host:
   - `curl -i https://list.petar-dev.com/1/delete` → **405**
   - `curl -i -X POST https://list.petar-dev.com/1/add_item -d 'item_name=x&quantity=abc'` → **403**
     (no CSRF token): proof that writes now go through CSRF at all
   - Through a browser session: a 5,000-char item name → **400** and no row created; quantity `abc`
     → **400**; 21 adds in a minute → **429**
4. TLS: `curl -I http://list.petar-dev.com/` → 301 to https; the https response carries HSTS and the
   CSP header. `:8080` is **not** reachable off-box. `*.petar-dev.com` no longer reaches this app.
5. Admin: `/admin/` → 404; 5 bad logins at `ADMIN_URL` → axes lockout, recorded with the real
   client IP.
6. A `curl -X POST` with a 1 MB body → 413 from Caddy.
7. `pip-audit -r requirements.txt` is clean; `python --version` → 3.12.x;
   `django.__version__` → 5.2.x.
8. Key rotation: a pre-rotation admin session cookie is rejected.
9. Logs land in journald, not `/tmp`; `journalctl --disk-usage` is bounded.

## Sequencing

| Window | Work |
|---|---|
| **1** (~3 h) | P0-1 merge + deploy, P0-2 credentials, P0-3 Caddy. Run the suite on the Pi before switching traffic. |
| **2** (~4 h) | P0-4 runtime + P1-1 lockfile/CI together. The new lockfile is resolved for the new runtime, and CI is where the suite first runs unattended. |
| **3** (~3 h) | P1-2 cookies/CSRF, P1-3 rate-limit gaps, P1-4 systemd, P1-5 WAL, each with its test from the gap list. |
| **4** (~2 h) | P2 cleanup, enforcing CSP after the report-only week, and the go/no-go on P1-6. |
