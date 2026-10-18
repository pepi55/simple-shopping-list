# Security Hardening — simple-shopping-list

_Revised 2026-10-13 against branch `agent/sec-test` @ `6964649`, which includes P0-1 (`71a47c8`,
`d754370`, `6964649`; not yet pushed). Line references are to that commit, except where P0-1 quotes
the code it replaced "at `2eea816`". `main` (`491f4f5`) still carries the pre-fix code. Test results
come from the project `venv/` built from `requirements.txt` (Python 3.9.25, Django 4.2.4,
django-axes 6.5.0, django-ratelimit 4.1.0, pymemcache 4.0.0), i.e. the versions the Pi runs, and a
local memcached._

## Context

`simple-shopping-list` is a Django 4.2 app served by gunicorn + uvicorn on a Pi and exposed to the
public internet. Injection hygiene is good: the ORM is used throughout, templates rely on default
autoescaping, and every item lookup is scoped to its parent list. **There is no SQLi, no XSS, and no
cross-list IDOR.**

The first round of fixes landed as six commits on `agent/sec-test` (`d3a84d2`..`2eea816`): TLS
settings, loopback bind, `django-axes`, env-driven admin path, POST-only writes, `ModelForm`
validation, per-IP rate limiting, and a 45-test suite. **None of it is merged or deployed.**

Running the suite caught a real defect: rate-limited requests returned 403, not 429. Following that
thread turned up a worse one. **The rate limiting could be bypassed outright by sending requests
concurrently**, because `FileBasedCache` has no atomic add or increment. P0-1 fixed both on the
branch: memcached, the ratelimit middleware, test settings, and regression tests. It was verified
end to end against a real memcached behind uvicorn: a 50-request concurrent burst now lets exactly
5 through. The suite is 49/49.

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
item table (capped at 200 items × 200 chars per list) but not the list table.

> **Residual risk, stated once:** an open write-enabled endpoint on the public internet can be
> filled with junk or wiped by anyone who finds it. The controls below bound the damage and make
> abuse slow and noisy; they cannot prevent it. If this data starts to matter, revisit auth.

---

## Where things stand

| Area | State | Evidence |
|---|---|---|
| TLS settings, `SECURE_PROXY_SSL_HEADER`, secure cookies, HSTS (60 s) | ✅ on branch; `check --deploy` clean | `settings.py:36-52` |
| gunicorn on loopback, `workers = 1`, `forwarded_allow_ips = '127.0.0.1'` | ✅ on branch | `gunicorn_conf.py:5,13,20` |
| `ALLOWED_HOSTS` from env | ✅ on branch | `settings.py:30` |
| `django-axes` (5 failures, 1 h cool-off) | ✅ on branch | `settings.py:65,79,89-94` |
| Admin path from `ADMIN_URL`, fail-fast | ✅ on branch | `simple_shoppinglist/urls.py:33` |
| `robots.txt` + `X-Robots-Tag: noindex` | ✅ on branch | `simple_shoppinglist/urls.py:25-26`, `Caddyfile:4` |
| `@require_POST` / `@require_safe`, CSRF on all three forms | ✅ on branch, tested | `views.py:20-70`, `detail.html` |
| `AddItemForm` / `ItemActionForm`, 200-item cap | ✅ on branch, tested | `forms.py` |
| `quantity` bounded 1–256 + migration `0003` | ✅ on branch; `makemigrations --check` clean | `models.py:16-19` |
| Bulk queries instead of per-row loops; `bought_all()` removed | ✅ on branch | `views.py:49-52,64` |
| `django-ratelimit` 20/m writes, 5/m bulk delete | ✅ on branch (memcached, 429 middleware); verified end to end under uvicorn | P0-1 |
| Test suite | ✅ 49/49, three runs back to back, via `settings_test.py`; no env vars needed | Test suite |
| Merged to `main` and deployed | ❌ | P0-2 |
| Admin password / `SECRET_KEY` rotation | ❌ not verifiable from the repo | P0-3 |
| Caddy config | ✅ present but broken for the wildcard, no login throttle | P0-4 |
| Python 3.12 / Django 5.2 | ❌ still Python 3.9.25, `Django==4.2.4` | P0-5 |
| Lockfile, CI, `pip-audit`, `latest_requirements.txt` removed | ❌ | P1-1 |
| systemd, `logging.conf` → journald, Django `LOGGING` | ❌ `run.sh:1` still logs to `/tmp` | P1-4 |
| SQLite WAL | ❌ | P1-5 |

---

## P0 — Do first (~8–10 h)

### ☑ P0-1. Make the rate limiting real, on the branch, before merging — done

**Findings, all three confirmed by running code against `2eea816`.**

**(a) A concurrent burst bypassed the limit entirely.** `CACHES` used `FileBasedCache`. Its `add()`
is `has_key()` followed by `set()`, and its `incr()` is `get()` + `set()`, with no locking.
django-ratelimit relies on `cache.add()` to create a window's counter and `cache.incr()` to bump it.
When N requests arrive together, they all see "no key", they all "create" the counter at 1, and
they all pass. Firing 50 threads at `django_ratelimit.core.is_ratelimited(..., rate="5/m")`:

| Backend | Allowed through a 5/m limit |
|---|---|
| `FileBasedCache` (config at `2eea816`) | **50 / 50**, in four of four runs |
| `LocMemCache` (atomic, but per-process) | 5 / 50 |

`workers = 1` does **not** serialise this. Under ASGI, Django 4.2 wraps every request in its own
`ThreadSensitiveContext` (`django/core/handlers/asgi.py:159`), so sync views and their decorators
run on separate threads concurrently. Any client that opened parallel connections, or multiplexed
over HTTP/2 through Caddy, got an unlimited write rate. The comments in `settings.py` and
`gunicorn_conf.py`, and the old plan, all claimed `FileBasedCache` plus one worker "keeps this
correct". It didn't.

django-ratelimit knew this: its own check rejects the backend as `django_ratelimit.E003 … does not
support atomic increment`. The check never loaded, because `django_ratelimit` wasn't in
`INSTALLED_APPS` and its checks register from `AppConfig.ready()`. That's why `check --deploy` was
clean.

**(b) Blocked requests got 403, not 429.** `block=True` raises `Ratelimited`, a `PermissionDenied`
subclass. `RATELIMIT_VIEW` is only consulted by `django_ratelimit.middleware.RatelimitMiddleware`,
which wasn't installed. So `ratelimited_view` (`views.py:16-17`) was dead code, and users got the
same generic 403 page as a CSRF failure. All three `RateLimitTests` failed on exactly this.

**(c) The suite polluted the live cache and failed on repeat runs.** See Test suite.

**What changed** (`71a47c8`, `d754370`, `6964649` on `agent/sec-test`):

| File | Change |
|---|---|
| `settings.py:66-68` | `django_ratelimit` in `INSTALLED_APPS`, so E003 now fires on any non-atomic backend |
| `settings.py:82-84` | `RatelimitMiddleware` appended to `MIDDLEWARE`, which makes blocked requests return 429 |
| `settings.py:96-109` | `CACHES` → `PyMemcacheCache` at `MEMCACHED_LOCATION` (default `127.0.0.1:11211`); comment rewritten |
| `gunicorn_conf.py:9-13` | Comment corrected: one worker does not serialise requests |
| `requirements.txt:13` | `pymemcache==4.0.0` |
| `simple_shoppinglist/settings_test.py` | New: test env defaults, `LocMemCache`, E003/W001 silenced for tests only |
| `tests/test_security.py` | `RateLimitConcurrencyTests` (50-thread burst against `settings.CACHES` → exactly 5 allowed) and `ProductionRateLimitConfigTests` (the production module's backend isn't in `KNOWN_BROKEN_CACHE_BACKENDS`; app and middleware installed). The redundant `CACHES` override on `RateLimitTests` was removed |
| `README.md` | `MEMCACHED_LOCATION`, the memcached requirement, and the test command |

**Verification.** Everything below ran against a throwaway memcached 1.6 on `127.0.0.1:11311`. The
end-to-end runs used the production settings module with only `DATABASES` pointed at a temp
SQLite file.

| Check | Result |
|---|---|
| Suite, `settings_test`, ×3 back to back, no env vars | **49/49** each run; nothing written to `django_cache/` |
| `check --deploy --fail-level WARNING`, production settings | **No issues**, now including django-ratelimit's cache checks |
| `RateLimitConcurrencyTests` + `ProductionRateLimitConfigTests`, `--settings=simple_shoppinglist.settings`, ×3 | **4/4** each run |
| **uvicorn + memcached: 50 concurrent `POST /1/delete` with a valid CSRF token** (5/m) | **5 × 302, 45 × 429**. The same burst got 50/50 through at `2eea816` |
| uvicorn: 21 sequential `POST /1/add_item` (20/m) | 20 × 302, then **429** |
| uvicorn: memcached killed, 5 adds 1.2 s apart | **500 × 5**. No row written; fails closed as the README states |
| uvicorn: memcached restarted | The very next request reached the view (+0.0 s); no app restart needed |
| Test client: memcached unreachable from the start | 500 (`ConnectionRefusedError`); `GET` on the detail page still 200 |
| **Negative controls** | The concurrency test fails against `FileBasedCache` (`50 != 5`). All three production-config assertions trip on the `2eea816` `settings.py`. The 429 tests fail without the middleware (`403 != 429`) |

Two things came out of the outage runs:

- **The outage is invisible.** Neither uvicorn's log nor anything else recorded the 500s, because
  there is still no `LOGGING` config and no `ADMINS` (P1-4). That makes P1-4 more urgent. A dead
  memcached silently disables every write endpoint until someone notices by hand.
- **Recovery depends on the server, not just pymemcache.** pymemcache's `HashClient` keeps
  per-server failure state. It silently returns defaults for `retry_timeout` (1 s) after a failure,
  which django-ratelimit reads as "limited", so you see 429. After `retry_attempts` (2) it marks the
  server dead for `dead_timeout` (60 s), raising errors, so you see 500. Its `_retry_dead()` resets
  its timer even when nothing is due to return, so a dead server can stay dead for up to ~2 × 60 s.
  Under the real ASGI server none of that persisted, and recovery was immediate. Under Django's
  sync test client, which reuses one cache object, a long outage was **still** answering 500 at
  +75 s. Expect the Pi under gunicorn's `UvicornWorker` to behave like the uvicorn run. If writes
  ever stay at 500/429 after memcached is back, this is why. Restarting the app clears it.

The alternative would have been to move all rate limiting into Caddy, using the `caddy-ratelimit`
build P0-4 needs anyway. It is atomic and runs before Django parses the body. Memcached was the
smaller change and keeps the limits under test. Revisit if a Caddy build exists for other reasons.

### ☐ P0-2. Merge and deploy `agent/sec-test` — ~1.5 h

Until this ships, every original finding is still live. This file has been public on `origin/main`
since `491f4f5`, and an earlier revision included working `curl` reproductions against the running
app. A roadmap of unpatched holes on a public repo shortens the window you can afford. Push `agent/sec-test`,
open the PR, merge it, then on the Pi:

1. `apt install memcached`, then `pip install -r requirements.txt`. That adds `django-axes`,
   `django-ratelimit` and `pymemcache`, none of which the running code has yet.
2. Run `python manage.py test shoppinglist --settings=simple_shoppinglist.settings_test` and get it
   green three times in a row. Then, with the production env, run
   `RateLimitConcurrencyTests --settings=simple_shoppinglist.settings` once against the Pi's own
   memcached. P0-1 verified the mechanism; this checks the Pi's install.
3. Set the newly required env vars `ALLOWED_HOSTS` and `ADMIN_URL` (with a trailing slash). Without
   them the app now fails to start, and it should.
4. `python manage.py migrate` creates the axes tables. `0003` is validators-only and emits no SQL.
5. Run `python manage.py collectstatic`. The test run warns
   `No directory at: …/django_code/staticfiles/`, so whitenoise has nothing to serve until this has
   run.
6. `python manage.py check --deploy --fail-level WARNING` with the real env must report zero issues,
   now including django-ratelimit's checks.
7. Point the router's port forward at Caddy on 80/443 and **remove the `:8080` forward**. Then
   confirm from off-box that `:8080` refuses connections.
8. **Clean up what the old hole already let in.** The new validators only apply to new writes. Rows
   stored through the unvalidated `add` view stay, and the admin will refuse to re-save them:
   ```python
   from django.db.models.functions import Length
   ShoppingItem.objects.annotate(n=Length("item_name")).filter(n__gt=200)
   ShoppingItem.objects.exclude(quantity__range=(1, 256))
   ```
   Also check `du -h db.sqlite3` against what a shopping list should weigh.

### ☐ P0-3. Rotate the admin password and verify/rotate `SECRET_KEY` — ~45 min

This step is deployment-only, and nothing in the repo shows whether it was done.

- **Admin password first.** It crossed the public internet in cleartext on every login before TLS.
  Use one superuser with a long passphrase.
- **`SECRET_KEY`: verify before rotating.** Two literals sit in public history (`2eeaf33`..`bfeace7`,
  and `8064984`, which reverted the env lookup back to a literal before `42aa86a` undid it). Both
  are listed in `tests/test_security.py:11-14`. Compare the live env value against them. A match
  means the key is compromised right now, not just leaked in the past, and the admin sessions and
  password-reset tokens it signs should be treated as forgeable.
- Generate a new key (`README.md:6-7`) and store it in `/etc/simple-shoppinglist.env` with mode 600,
  loaded by systemd (P1-4). `python-dotenv` is still declared (`requirements.txt:14`) but never
  imported, so nothing loads a `.env` today.
- **Do not rewrite git history.** The repo is public and has been cloned and indexed. Rotation is
  what makes the values worthless. Run `gitleaks detect` over full history once; a pattern scan
  found nothing beyond the two known keys, and no `db.sqlite3`, `.env` or log file has ever been
  committed.

### ☑ P0-4. Fix the Caddyfile — ~1.5 h

`Caddyfile:1` serves `petar-dev.com, *.petar-dev.com`:

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
  discarding is what makes `SECURE_PROXY_SSL_HEADER` and uvicorn's proxy-header handling
  trustworthy. Both django-ratelimit (`key="ip"`) and axes read the client IP from `REMOTE_ADDR`,
  which uvicorn rewrites from `X-Forwarded-For`. `django-ipware` is not installed, so axes uses its
  `REMOTE_ADDR` fallback (`axes/helpers.py:204-206`). **Never add `trusted_proxies` to this block.**
- **CSP is new and starts in report-only.** Autoescaping is currently the only XSS defence. The one
  inline style in the app is `forms.py:13` (`style="width: 3em;"`); move it to `style.css` as a
  class. The admin templates also use some inline styles. Check the browser console for a week,
  then switch to the enforcing `Content-Security-Policy` header.
- **The admin login throttle is still commented out** (`Caddyfile:9-18`). It needs a Caddy built
  with `caddy-ratelimit` (`xcaddy build --with github.com/mholt/caddy-ratelimit`). Until then, axes
  is the only control, and it locks out per IP, so a distributed guesser gets 5 tries per IP per
  hour. The passphrase from P0-3 is what actually holds. IP-allowlisting the admin path to your
  LAN/Tailscale range remains the ~4-line upgrade that removes the surface entirely.

### ☐ P0-5. Python 3.12 + Django 5.2 LTS — ~3 h

**Promoted from P1.** It was deferred until a test suite existed, and the suite is now green. The
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
upgrades stop being OS upgrades. In Docker, memcached becomes a sidecar container. Drop `uvloop`,
which buys nothing at this traffic. For this codebase the 4.2 → 5.2 risk is near zero: five function
views, two models, no custom middleware. Run `python -Wa manage.py test` to surface deprecations.

---

## P1 — Next (~5–7 h)

### ☐ P1-1. One requirements file, a lockfile, and CI — ~2 h

- Delete `latest_requirements.txt`. It pins `Django==5.0.7`, which went EOL in April 2025, and sits
  next to the conventionally-named `requirements.txt` that every tool actually reads.
  `requirements.txt` itself was hand-edited (axes and ratelimit appended to an old freeze), not
  resolved.
- Add `requirements.in` with floors (`Django>=5.2,<5.3`, `uvicorn[standard]`, `gunicorn>=23`,
  `whitenoise`, `django-axes`, `django-ratelimit`, `pymemcache`). Generate `requirements.txt` with
  `pip-compile --generate-hashes` and install with `--require-hashes`. Put the dev tools in
  `requirements-dev.in`.
- Drop `django-pwa` (`requirements.txt:6`) and `python-dotenv` (`requirements.txt:14`).
- There is still no `.github/`. The workflow should:
  - run the suite with `--settings=simple_shoppinglist.settings_test`;
  - with a `memcached` service container, run `manage.py check --deploy --fail-level WARNING` and
    `RateLimitConcurrencyTests` against the **production** settings with dummy env values. That is
    the only automated run of the real cache path;
  - run `makemigrations --check --dry-run` (clean today), `ruff check`, and `pip-audit` on push plus
    a weekly cron.
- Add dependabot for pip and actions, and a `gitleaks` pre-commit hook.

### ☐ P1-2. Scope cookies and CSRF to this host — ~45 min

`CSRF_TRUSTED_ORIGINS = ["https://petar-dev.com", "https://*.petar-dev.com"]` (`settings.py:50`)
makes every sibling subdomain a trusted CSRF origin. Siblings are *same-site*, so `SameSite=Lax`
doesn't stop them either. A sibling can also set a `csrftoken` cookie for `.petar-dev.com` (cookie
tossing) and complete Django's double-submit check. This needs an XSS or a dangling-DNS takeover on
any `petar-dev.com` host. The prize is CSRF against a logged-in **admin** session: delete every list,
or create a superuser.

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

### ☐ P1-3. Remaining rate-limit gaps — ~45 min

These are smaller than P0-1, and they're worth fixing now that the counters are atomic:

- **The more destructive path got the looser limit.** "Remove Selected" (`detail.html:30`) posts to
  `update`, which deletes any selected items, bought or not, in one request at `WRITE_RATE` = 20/m
  (`views.py:35,49-50`). The bought-only cleanup in `delete` gets `DESTROY_RATE` = 5/m. Give both
  one shared budget: `@ratelimit(group="destroy", …)` on `delete`, and
  `django_ratelimit.core.is_ratelimited(request, group="destroy", key="ip", rate=DESTROY_RATE,
  method="POST", increment=True)` inside the `is_delete` branch.
- **Per-IP limits are only as strong as an attacker's address supply.** django-ratelimit buckets
  IPv6 per /64 (`RATELIMIT_IPV6_MASK`, default 64, `django_ratelimit/core.py:53`), and one home
  connection usually gets a /56 or /48. The 200-item-per-list cap is the real storage bound; rate
  limiting just makes abuse slow and noisy.
- After deploying, confirm the counters and axes see real client IPs and not `127.0.0.1`: trigger a
  lockout, then look at `axes_accessattempt.ip_address`.

### ☐ P1-4. systemd instead of `logging.conf`, plus Django `LOGGING` — ~1 h

This item is still open. `run.sh:1` passes `--log-config ./logging.conf`, which writes unrotated
`FileHandler` logs to `/tmp/gunicorn.{error,access}.log` (`logging.conf:34,39`). On a Pi, `/tmp` is
often tmpfs, so the logs eat RAM. It also silently overrides `errorlog`/`accesslog` in
`gunicorn_conf.py:6-7`.

Delete `logging.conf` and drop `--log-config`. Run under a systemd unit with:

- `EnvironmentFile=/etc/simple-shoppinglist.env`, `Restart=on-failure`, `MemoryMax=512M`
- `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict`
- `StateDirectory=simple-shoppinglist` for `db.sqlite3` (now `settings.py:139`), so the code tree
  can be read-only
- `After=memcached.service` and `Wants=memcached.service`

There is still **no `LOGGING` dict**. With `DEBUG = False` and no `ADMINS`, 500s and axes lockouts go
nowhere durable. P0-1's outage test confirmed it: five 500s from a dead memcached left no trace in
the server log. Route `django.request` at `ERROR`, plus `axes` and `django_ratelimit` at
`WARNING`, to stderr, which systemd sends to journald. Consider monitoring `memcached.service` too.

### ☐ P1-5. SQLite concurrency — ~20 min, **after P0-5**

`DATABASES` (`settings.py:136-141`) has no options, so concurrent writes can still produce
`database is locked` 500s. P0-1(a) shows requests really do run concurrently here. An
`init_command` option **only works on Django ≥ 5.1**; on 4.2 the sqlite3 backend rejects it. After
the upgrade:

```python
"OPTIONS": {
    "timeout": 20,
    "transaction_mode": "IMMEDIATE",
    "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
},
```

`update` is a single bulk statement (`views.py:49-52`), so it needs no extra `transaction.atomic()`.

### ☐ P1-6. Optional — capability URLs. **Decide explicitly, don't half-do it.**

This decision is unchanged. Swapping the integer PK for a `UUIDField` makes lists shareable by link
only, but only if the index stops listing them (`index.html:20-22`). Otherwise the index hands every
capability to every visitor. It's a UX call, needs a migration, and breaks existing bookmarks.

---

## P2 — Cleanup (~1–2 h)

- **`views.py:75`**: `HttpResponseBadRequest(form.errors.as_text())` sends unescaped error text as
  `text/html`. None of today's messages echo user input, but any future `ChoiceField`'s
  `invalid_choice` message would turn this into reflected XSS. Pass `content_type="text/plain"`
  here, in the other `HttpResponseBadRequest` calls, and in `ratelimited_view`.
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
- **Dead PWA code**: `settings.py:131,187-215`, `static/shoppinglist/js/serviceworker.js`, the empty
  `templates/shoppinglist/manifest.json`, and the commented `pwa` lines in `settings.py:69`,
  `simple_shoppinglist/urls.py:36` and `index.html:3,6`.
- **`settings.py:30`**: `.split(",")` doesn't strip whitespace, so `"a.com, b.com"` silently drops
  `b.com`. It fails closed, but confusingly. Also have `urls.py:33` assert that `ADMIN_URL` ends
  with `/`.
- **`detail.html:46,57`**: two elements share `id="submit"`.

---

## Test suite

`shoppinglist/tests/` has 49 tests across `test_forms.py`, `test_models.py`, `test_security.py` and
`test_views.py`. They cover every P0 regression from the original plan, plus P0-1's concurrency and
production-config guards. Run them from `django_code/` with no env vars and no memcached:

```
python manage.py test shoppinglist --settings=simple_shoppinglist.settings_test
```

Results from the project `venv/` (pinned versions):

| Run | Code | Result |
|---|---|---|
| 1 | `2eea816`, real env vars | **42/45.** All three `RateLimitTests` get `403 != 429` (P0-1(b)) |
| 2, 1 s later | `2eea816` | Same 3 failures |
| 3, 1 s later | `2eea816` | **11 fail.** The same 3, plus 7 `AddItemViewValidationTests` and `test_delete_bought_removes_only_bought_items_with_confirmation`, all `403` from the rate limiter |
| 1–3 | `6964649` (P0-1), `settings_test` | **49/49 OK, every run** |

At `2eea816`, every form, model, view-validation, CSRF, escaping and deploy-check test passed on
the first run, so the original P0 code fixes worked as intended. The failures were all in the
harness and the rate limiter:

- **The view tests wrote into the production cache.** Only `RateLimitTests` overrode `CACHES`.
  Everything in `test_views.py` used the real `FileBasedCache` at `django_code/django_cache/`, which
  persisted between runs and was never cleared. Each run spent 9 of `add_item`'s 20/m budget and 2
  of `delete`'s 5/m, so the third run in a window was blocked. On the Pi that directory would have
  been shared with the live service.
- **The suite couldn't start without production env vars.** `settings.py:25,30` and
  `simple_shoppinglist/urls.py:33` read `os.environ[...]` at import time.

`settings_test.py` fixes both. It sets test defaults for the three env vars, then swaps in a
per-process `LocMemCache` and silences django-ratelimit's "not shared" checks for tests only.
Because the test settings swap the cache out, `ProductionRateLimitConfigTests` checks the production
`settings` module directly. `RateLimitConcurrencyTests` runs against whichever settings are active,
so the same test can target real memcached on the Pi (P0-1).

Gaps to fill:

- A CI job that runs `RateLimitConcurrencyTests` against a memcached service container with the
  production settings (P1-1). Locally it only exercises `LocMemCache`.
- `test_admin_default_path_404s`, and `test_admin_lockout_after_five_failures` (axes), posting to
  `reverse("admin:login")`.
- `test_update_delete_shares_destroy_budget`: the 6th "Remove Selected" in a minute → 429 (P1-3).
- `test_oversized_body_rejected`: a body over `DATA_UPLOAD_MAX_MEMORY_SIZE` → 400 (P0-4).
- `test_bad_request_is_text_plain` (P2).
- `test_cookies_are_host_prefixed`: assert the `Set-Cookie` names from a GET to the detail page
  (P1-2).
- `test_list_size_uses_single_query` and `test_admin_changelist_query_count` (P2).

---

## Verification (after P0)

1. `python manage.py test shoppinglist --settings=simple_shoppinglist.settings_test` is green **on
   the Pi**, three times in a row, then in CI.
2. `python manage.py check --deploy --fail-level WARNING` reports zero issues with the production
   env and `django_ratelimit` in `INSTALLED_APPS`.
3. `RateLimitConcurrencyTests` with `--settings=simple_shoppinglist.settings` on the Pi passes
   against the Pi's memcached: 50 concurrent hits on a 5/m limit → **5** allowed.
4. Behaviour against the deployed host:
   - `curl -i https://list.petar-dev.com/1/delete` → **405**
   - `curl -i -X POST https://list.petar-dev.com/1/add_item -d 'item_name=x&quantity=abc'` → **403**
     (no CSRF token): proof that writes now go through CSRF at all
   - Through a browser session: a 5,000-char item name → **400** and no row created; quantity `abc`
     → **400**; 21 adds in a minute → **429** (not 403)
5. TLS: `curl -I http://list.petar-dev.com/` → 301 to https; the https response carries HSTS and the
   CSP header. `:8080` is **not** reachable off-box. `*.petar-dev.com` no longer reaches this app.
6. Admin: `/admin/` → 404; 5 bad logins at `ADMIN_URL` → axes lockout, recorded with the real
   client IP.
7. A `curl -X POST` with a 1 MB body → 413 from Caddy.
8. `pip-audit -r requirements.txt` is clean; `python --version` → 3.12.x;
   `django.__version__` → 5.2.x.
9. Key rotation: a pre-rotation admin session cookie is rejected.
10. Logs land in journald, not `/tmp`; `journalctl --disk-usage` is bounded.

## Sequencing

| Window | Work |
|---|---|
| **1** (~3 h) | Push `agent/sec-test` (P0-1 is done and verified), P0-2 merge + deploy, P0-3 credentials. Pull P1-4's `LOGGING` forward if possible, since a memcached outage is otherwise silent. |
| **2** (~2 h) | P0-4 Caddy, including the `caddy-ratelimit` build for the admin login. |
| **3** (~4 h) | P0-5 runtime + P1-1 lockfile/CI together. The new lockfile is resolved for the new runtime, and CI is where the suite first runs unattended. |
| **4** (~3 h) | P1-2 cookies/CSRF, P1-3 rate-limit gaps, P1-4 systemd, P1-5 WAL, each with its test from the gap list. |
| **5** (~2 h) | P2 cleanup, enforcing CSP after the report-only week, and the go/no-go on P1-6. |
