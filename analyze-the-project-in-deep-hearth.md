# Security Hardening — simple-shopping-list

## Context

`simple-shopping-list` is a Django 4.2 app at `/home/petar.dimitrov/claudespace/simple-shopping-list`,
served by gunicorn + uvicorn on a Pi and exposed to the public internet (`settings.py:31` allows
`84.82.138.101` and `.petar-dev.com`).

Injection hygiene is genuinely good: the ORM is used throughout with parameterised lookups,
templates rely consistently on default autoescaping, and the item lookup at `views.py:25` is
correctly scoped to its parent list. **There is no SQLi, no XSS, and no cross-list IDOR.** The
exposure is elsewhere — every write endpoint is anonymous and unvalidated, one destructive endpoint
fires on a bare `GET`, the runtime and framework are both EOL, and two `SECRET_KEY` values sit in
public git history.

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
confidentiality. Two structural facts shape the whole plan:

- **There is no create-list view.** `shoppinglist/urls.py:7-13` exposes only
  index/detail/update/delete/add_item; lists are created only through `/admin/`. Anonymous users
  can grow the *item* table but not the *list* table, which meaningfully shrinks the blast radius.
- **SQLite does not enforce `VARCHAR(200)`.** This turns out to be the worst hole in the app (P0-4).

> **Residual risk, stated once:** an open write-enabled endpoint on the public internet can be
> filled with junk or wiped by anyone who finds it. The controls below bound the damage and make
> abuse slow and noisy; they cannot prevent it. If this data starts to matter, revisit auth.

---

## P0 — Do first (~6–9 h)

### ☐ P0-1. Terminate TLS behind Caddy, rebind gunicorn to loopback — ~2 h

Nothing else here is trustworthy over cleartext. Today gunicorn binds `Pie3:8080` directly
(`gunicorn_conf.py:3`) with the public IP port-forwarded to it, and there is no proxy at all.

Caddy over nginx: automatic Let's Encrypt issuance *and* renewal with no certbot/cron, and a
~10-line config. Rebind `gunicorn_conf.py:3` to `127.0.0.1:8080` and repoint the router forward at
Caddy:443. **The app must not remain reachable on `:8080`** — otherwise every control below is
bypassed by hitting the origin directly.

```python
# settings.py — replaces the explicit CSRF_COOKIE_SECURE = False at line 26 (commit c81a347)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60          # raise to 31536000 after a week of clean operation
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
CSRF_TRUSTED_ORIGINS = ["https://petar-dev.com", "https://*.petar-dev.com"]
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
```

Two traps worth calling out:

- `SECURE_PROXY_SSL_HEADER` is safe **only** if Caddy unconditionally *overwrites*
  `X-Forwarded-Proto`. If a client can set it, Django believes a plaintext request was secure.
- Behind the proxy `REMOTE_ADDR` becomes `127.0.0.1`, which silently collapses per-IP rate limiting
  (P0-5) into one global bucket. Set `FORWARDED_ALLOW_IPS=127.0.0.1` — never `*`, or
  `X-Forwarded-For` becomes spoofable.

Don't set HSTS to a year on day one; a mistake on a domain hosting your other Pi services is
painful to unwind. Also move `ALLOWED_HOSTS` to an env var and drop the hardcoded IPs.

### ☐ P0-2. Harden `/admin/` — ~45 min

`simple_shoppinglist/urls.py:23`, with the comment *"There is no admin... Maybe there is an admin."*
Obscurity is not a control, and this route grants full destruction of every list.

- **Rotate the admin password now.** It has been transmitted in cleartext over the public internet
  on every login since deployment. This is more urgent than the `SECRET_KEY` rotation and is the
  step most often skipped.
- **`django-axes` is the load-bearing control here**, not the path change — `AXES_FAILURE_LIMIT = 5`,
  `AXES_COOLOFF_TIME = 1`. Needs `INSTALLED_APPS`, `AXES_MIDDLEWARE`, `AUTHENTICATION_BACKENDS`.
- Move off the default path via `path(os.environ["ADMIN_URL"], admin.site.urls)` (fail-fast if
  unset). Be clear-eyed that this is worth little on its own: `urls.py` is on public GitHub.
- Add a Caddy rate limit on the login path. One superuser only, strong passphrase.

> If you later want to close this surface entirely, IP-allowlisting `/admin/*` at Caddy to your
> LAN/Tailscale range is ~4 lines and reduces the internet-facing credential surface to zero while
> keeping admin fully usable from home. Noting it as an easy upgrade, not reopening the decision.

### ☐ P0-3. `@require_POST` + confirmation on the destructive endpoint — ~1 h

`views.py:37-43` never reads `request.POST`; it unconditionally deletes every `bought=True` item.
`urls.py:11` uses a bare `path()`, and `CsrfViewMiddleware` only enforces on *unsafe* methods, so
`GET` bypasses CSRF entirely.

The reason this is P0 is **not** malicious deletion — that is already an accepted risk under the
no-auth decision. It is that `GET /<id>/delete` looks idempotent to a machine: Googlebot, Chrome/Safari
link prefetch, Slack and WhatsApp unfurlers, and antivirus URL scanners will all fire it. Data loss
with no attacker involved. The UI is commented out at `detail.html:54-60`, so it is an
undiscoverable-but-live destructive route.

- `@require_POST` on `update`, `delete`, `add`; `@require_safe` on `index`, `detail`.
- `delete` additionally requires a `confirm` field, so even a replayed stale POST can't mass-delete.
- Un-comment `detail.html:54-60` with the `confirm` input, or drop the route.
- Free extra: `robots.txt` with `Disallow: /` and an `X-Robots-Tag: noindex` header at the proxy so
  crawlers never discover list IDs. Not the control — `require_POST` is — but it costs nothing.

### ☐ P0-4. Unbounded `item_name` — the disk-exhaustion hole — ~2 h

**Not in the original finding list; the most effective DoS vector in the app.** `views.py:48` calls
`.create(item_name=request.POST["name"], ...)` directly, bypassing validation. Django's
`max_length=200` (`models.py:14`) is a *validator*, enforced by forms and `full_clean()` — and
**SQLite does not enforce `VARCHAR` limits at the storage layer**. So an anonymous POST can write a
~2.5 MB `item_name` (the `DATA_UPLOAD_MAX_MEMORY_SIZE` ceiling) on every single request. On a Pi
with SQLite, that fills the disk fast.

One mechanism — a `ModelForm` — closes this plus the non-numeric-quantity 500, the negative/absurd
quantity hole, and the `ValueError` escape at `views.py:25-26`. New file `shoppinglist/forms.py`:

```python
MAX_ITEMS_PER_LIST = 200

class AddItemForm(forms.ModelForm):
    class Meta:
        model = ShoppingItem
        fields = ["item_name", "quantity"]

    def __init__(self, *args, shopping_list, **kwargs):
        super().__init__(*args, **kwargs)
        self.shopping_list = shopping_list

    def clean_item_name(self):
        # The length check SQLite will NOT do for you.
        name = self.cleaned_data["item_name"].strip()
        if not name:
            raise forms.ValidationError("Item name is required.")
        return name

    def clean(self):
        cleaned = super().clean()
        if self.shopping_list.shoppingitem_set.count() >= MAX_ITEMS_PER_LIST:
            raise forms.ValidationError(f"This list is full (max {MAX_ITEMS_PER_LIST} items).")
        return cleaned

class ItemActionForm(forms.Form):
    """Validates and scopes the item IDs submitted by detail.html."""
    item = forms.ModelMultipleChoiceField(queryset=ShoppingItem.objects.none())

    def __init__(self, *args, shopping_list, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = shopping_list.shoppingitem_set.all()
```

`ModelMultipleChoiceField` is the precise fix for `views.py:25-26`: its `_check_values` already
wraps the `pk__in` lookup in `try/except (ValueError, TypeError)` and re-raises as `ValidationError`.
So `item=abc`, `item=-1`, and an ID from another list all become clean 400s instead of the uncaught
`ValueError` you get today. Binding the queryset to `shopping_list.shoppingitem_set` preserves the
cross-list scoping that is already correct.

Also add validators to `models.py:15` (**needs migration `0003`**) so the `min`/`max` at
`detail.html:42` finally has a server-side counterpart:

```python
quantity = models.IntegerField("quantity of item", default=1,
    validators=[MinValueValidator(1), MaxValueValidator(999)])
```

Storage is then bounded by construction: 200 items × 200 chars × admin-controlled list count.

### ☐ P0-5. Per-IP rate limiting on writes — ~1 h

`django-ratelimit`, not nginx `limit_req`: gunicorn has no rate limiting (and isn't in the request
path under UvicornWorker), and nginx can't express "20 adds/min *per list*" without adding nginx
solely for that. `WRITE_RATE = "20/m"` on add/update, `DESTROY_RATE = "5/m"` on delete.

> **The gotcha that decides whether this works at all:** django-ratelimit counts in the Django
> cache. With the default `LocMemCache` and N gunicorn workers, each worker keeps a private counter
> and the real limit silently becomes N × rate. Use `workers = 1` in `gunicorn_conf.py` (correct
> anyway on a Pi with SQLite, given write contention) **plus** `FileBasedCache`, so it stays right
> if workers ever increase. Do **not** use `DatabaseCache` — it writes to the same SQLite file and
> multiplies the lock contention. Set `RATELIMIT_VIEW` for a friendly 429 instead of a bare 403.

### ☐ P0-6. Rotate both leaked `SECRET_KEY` values — ~45 min

`settings.py:25` is correct today (`os.environ["SECRET_KEY"]`, fail-closed). Public history at
`github.com/pepi55/simple-shopping-list` is not:

| Commits | Leaked literal |
|---|---|
| `2eeaf33`, `040c09d`, `bfeace7` (removed at `f88a510`) | `django-insecure-km5bbn6yod9a8ue3z0==e0)2f*@il2&@5tm-l3@z)vkwhu#vqy` |
| `8064984`, a `v2.1.0` release commit (removed at `42aa86a`) | `!+5a)ca2t%&hr!nvh284^e#_*&332htki#l9@k039$#1qb4)^x` |

With no user accounts the leak doesn't enable session forgery against real users — it enables
**admin password-reset token forgery** (`PasswordResetTokenGenerator` is keyed on `SECRET_KEY`) and
signed-cookie tampering, which matters because `/admin/` is exposed.

`8064984` is the dangerous one: it *reverted* the env lookup back to a literal, and `42aa86a`
reverted it again. That round-trip is the signature of someone who had the literal in their shell.
**So step 1 is verification, not rotation:**

1. Compare the live `SECRET_KEY` env value on the box against both literals. A match means active
   compromise, not historical.
2. Generate a new key (`README.md:4` documents the command).
3. Store in `/etc/simple-shoppinglist.env`, `chmod 600`, loaded via systemd `EnvironmentFile=`
   (P1-4). Note `python-dotenv` is a declared dependency that **is never imported anywhere**, so
   `.env` is not being loaded today — the key must be exported by hand. Systemd fixes this; then
   drop `python-dotenv`.
4. Restart. Only admin sessions invalidate.

**Do not rewrite git history.** The repo is public with clones you can't reach; GitHub serves
unreferenced objects by SHA more or less forever, and secret scanners have already indexed them.
`filter-repo` would break every clone and invalidate every SHA while buying nothing — *rotation* is
what makes the value worthless, which is the actual goal. Instead: run `gitleaks detect` over full
history once to confirm nothing else is in there, and add it as a pre-commit hook.

---

## P1 — Next (~6–8 h)

### ☐ P1-1. Python 3.12 + Django 5.2 LTS — ~3 h

The runtime is not an obstacle to work around; **it is itself a finding.** The box runs Python
3.9.25, EOL since October 2025 — ten months unpatched. The target is forced, not chosen:

| | Status |
|---|---|
| Django 4.2 LTS (`requirements.txt`) | EOL April 2026 |
| Django 5.0.7 (`latest_requirements.txt`) | EOL April 2025 — already unsupported when pinned |
| Django 5.1 | EOL December 2025 |
| **Django 5.2 LTS** | **Supported to April 2028. Requires Python ≥ 3.10.** |

No supported Django runs on 3.9, so "upgrade Django, keep Python" isn't on the menu. Preferred route
for Python 3.12: **Docker (`python:3.12-slim`, arm64)** — decouples runtime from OS, rollback is a
tag change, and future upgrades stop being OS upgrades. Alternatives: OS upgrade to Trixie (3.13) or
Bookworm (3.11, fine for 5.2), or pyenv (an hour-plus of CPython compilation on a Pi 3, and you own
it forever). Budget for `uvloop`/`httptools` compiling from source on ARM — or just drop `uvloop`,
which buys nothing at this traffic.

4.2 → 5.2 risk for *this* codebase is near zero: five function views, two models, no custom
middleware, no third-party Django apps. Run `python -Wa manage.py test` to surface deprecations.

**Correction to my initial severity:** I flagged gunicorn 21.2.0 / CVE-2024-1135 as urgent. It is
not — `run.sh:1` uses `-k uvicorn.workers.UvicornWorker`, under which gunicorn is a process
supervisor only and never parses HTTP. The smuggling CVEs live in `gunicorn/http/message.py`, off
the request path. Upgrade it anyway, but the parser that actually needs patching is
**uvicorn 0.23.2 + httptools 0.6.0**, both three years stale.

### ☐ P1-2. One requirements file, a lockfile, and audit tooling — ~1.5 h

Having the conventionally-named `requirements.txt` be the *stale* one is a trap — every tool and
contributor reads that name. Delete `latest_requirements.txt`.

- `requirements.in` — direct deps with floors (`Django>=5.2,<5.3`, `gunicorn>=23`,
  `uvicorn[standard]>=0.30`, `whitenoise>=6.7`, `django-ratelimit>=4.1`).
- `requirements.txt` — generated by `pip-compile --generate-hashes`; install with
  `--require-hashes`.
- `requirements-dev.in` — pytest, pytest-django, ruff, pip-audit, pre-commit, gitleaks.
- Drop `django-pwa==1.1.0` (disabled at `settings.py:44` and `urls.py:25`, unmaintained) and delete
  the dead `PWA_*` block at `settings.py:132-161`. Drop `python-dotenv`.

There is no `.github/` at all — no CI, no dependabot, no pre-commit. Add: `pip-audit` on push **and**
a weekly cron (so a CVE published against a frozen repo still reaches you), dependabot for pip and
actions, `ruff check` (which catches `models.py:19` in 200 ms), and
`manage.py check --deploy --fail-level WARNING` as a gate. That last line is the highest-value one
in the plan — it permanently enforces every setting from P0-1 and fails the build if someone reverts
`CSRF_COOKIE_SECURE`.

### ☐ P1-3. SQLite concurrency — ~30 min

Concurrent anonymous writes on a Pi produce `database is locked` 500s. Rate limiting mitigates but
doesn't fix it:

```python
DATABASES["default"]["OPTIONS"] = {"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;"}
```

Wrap the multi-item `update` in `transaction.atomic()` so a partial failure can't half-apply a batch.

### ☐ P1-4. Replace `logging.conf` with systemd + add Django `LOGGING` — ~1 h

`logging.conf:34,38` writes to `/tmp/gunicorn.{error,access}.log` via plain `FileHandler` — no
rotation, and on a Pi where `/tmp` is often **tmpfs**, unbounded logs consume RAM until the box OOMs.
That availability risk matters more than the 0644 mode on a single-user host.

Don't add `RotatingFileHandler` — **delete `logging.conf` and drop `--log-config` from `run.sh:1`.**
Log to stdout/stderr under a systemd unit with `EnvironmentFile=/etc/simple-shoppinglist.env`,
`Restart=on-failure`, `MemoryMax=512M`, `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`.
That one change solves rotation/retention (journald, `SystemMaxUse=`), the `/tmp` exposure, the
tmpfs RAM risk, restart-on-crash, and secure `SECRET_KEY` delivery at once. Also resolves the live
conflict where `gunicorn_conf.py:4-5` sets `./error.log` but `--log-config` redirects to `/tmp` and
wins. Move `db.sqlite3` out of `BASE_DIR` (`settings.py:85`) to `/var/lib/simple-shoppinglist/` so
`ProtectSystem=strict` can make the code tree read-only.

Separately, there is **no `LOGGING` dict** in `settings.py`. With `DEBUG = False` and no `ADMINS`,
unhandled 500s — including every bug in this report — produce a traceback that goes nowhere durable.
Add one routing `django.request` at `ERROR` to stderr.

### ☐ P1-5. Optional — capability URLs. **Decide explicitly, don't half-do it.**

The one control that restores confidentiality *without* adding auth: swap the integer PK for an
unguessable `UUIDField` and drop the enumerating index. Lists become shareable-by-link only.

**It is all-or-nothing.** `index.html:18-26` lists every list with its link, so if the index stays,
capability URLs buy exactly zero — the index hands every capability to every visitor. Either the
index goes and you bookmark your lists, or you keep enumeration and rely on the P0 controls. A real
UX call, not a security one; also needs a migration and breaks existing bookmarks.

---

## P2 — Cleanup (~1–2 h)

- `models.py:7` — `len(self.shoppingitem_set.all())` loads every row; use `.count()`. It's in
  `ListAdmin.list_display` (`admin.py:12`), so it's an N+1 across the changelist — fix properly with
  `get_queryset()` returning `.annotate(_size=Count("shoppingitem"))` plus
  `@admin.display(ordering="_size")`, which also makes the column sortable.
- `models.py:18-19` — `bought_all()` references an undefined bare `quantity` → `NameError`.
  **Delete it** rather than "fix" it: it's unreferenced, and `quantity == 0` has no relationship to
  "bought", which is already a field. Its real significance is as evidence for the `ruff` CI item.
- `views.py:40-41` and `views.py:30` — per-row `.delete()` loops become single bulk queries.
- `detail.html:44` — `value="{{ list.id }}"` references `list`, but the context var is
  `shoppinglist`, so it renders empty. Disappears once rendered from `AddItemForm`.
- `urls.py:10-12` — inconsistent trailing slashes (`detail` has one; `update`/`delete`/`add_item`
  don't). Harmless today, but with `APPEND_SLASH` a mistyped URL redirects a POST and **silently
  discards the body**. Normalise.
- `views.py:10` — `order_by("-list_name")[:10]` silently truncates at 10 with no pagination;
  descending name order is probably unintended.
- `views.py:48` unused `new_item`; `views.py:2` unused `Http404`/`HttpResponse` after refactor.
- `README.md:5-7` documents binding gunicorn to a network interface with no proxy or TLS — update
  it, or someone will follow it.

---

## Test suite (write alongside P0, not after)

`shoppinglist/tests.py` is an untouched 3-line stub — there is no regression net for any change
above. Write these *first* so they demonstrably flip fail→pass. Split into
`tests/test_views.py`, `test_forms.py`, `test_models.py`, `test_security.py`.

**Destructive-method safety (P0-3)**
- `test_delete_bought_rejects_get` — 405, item count unchanged. *The crawler-scenario regression.*
- `test_delete_bought_rejects_post_without_confirmation` — valid CSRF, no `confirm` → 400.
- `test_delete_bought_requires_csrf_token` — `Client(enforce_csrf_checks=True)` → 403.
- `test_update_rejects_get`, `test_add_rejects_get` — 405, not 500.

**Input validation (P0-4)**
- `test_add_rejects_overlong_item_name` — 5,000 chars → 400 **and assert no row was created.** The
  row-count assertion is the whole point: on SQLite a naive implementation returns 200 and stores it.
- `test_add_rejects_non_numeric_quantity` → 400, not 500.
- `test_add_rejects_negative_quantity`, `test_add_rejects_quantity_above_max`.
- `test_add_rejects_blank_and_whitespace_only_name`, `test_add_missing_fields_returns_400_not_500`.
- `test_add_enforces_max_items_per_list` — 201st add → 400.

**Exception handling (`views.py:25-26`)**
- `test_update_with_non_numeric_item_id` → 400. *The exact `ValueError` regression.*
- `test_update_with_item_id_from_another_list` → 400 **and the other list's item is untouched.*
- `test_update_with_no_action_key` / `test_update_with_both_action_keys` → 400.
- Happy paths: `test_update_marks_selected_items_bought`, `test_update_deletes_selected_items`.

**Security settings (P0-1) — these stay green forever and stop regressions**
- `test_deploy_checks_pass` — `call_command("check", "--deploy", "--fail-level=WARNING")`. Covers
  all four settings in one test.
- `test_secret_key_not_hardcoded` — from env, and explicitly **not equal to either leaked literal.**
  The only automated guard against the P0-6 reuse scenario.
- `test_debug_is_false`, `test_csrf_token_present_on_all_forms`.

**Rate limiting (P0-5)**
- `test_add_is_rate_limited`, `test_delete_has_stricter_rate_limit`.
- `test_rate_limit_is_per_ip` — two `REMOTE_ADDR`s get independent budgets. Guards against the P0-1
  proxy misconfiguration collapsing everyone into one bucket.

**Models / templates (P2)**
- `test_list_size_uses_single_query` (`assertNumQueries(1)`),
  `test_admin_changelist_query_count` with 20 lists.
- `test_no_unescaped_output` — a list named `<script>alert(1)</script>` renders escaped. Clean
  today; this keeps it that way, since autoescaping is the *only* XSS defence and it's implicit.

---

## Verification

1. `python manage.py test shoppinglist` green — confirm the P0 cases fail against current `main` first.
2. `python manage.py check --deploy` → zero issues (today: warns on all four cookie/HSTS settings).
3. The original bugs, by hand:
   - `curl -i http://host/1/delete` → **405** (today: silently deletes every bought item)
   - `curl -i -X POST http://host/1/add -d "name=$(python -c 'print("A"*5000)')&quantity=1"` → **400**, no row created (today: 200, 5 KB stored)
   - `curl -i -X POST http://host/1/add -d 'name=x&quantity=abc'` → **400** (today: 500)
   - `curl -i -X POST http://host/1/update -d 'item=abc&update=1'` → **400** (today: 500)
4. TLS: `curl -I http://host/` → 301 https; `curl -I https://host/` shows HSTS. Confirm `:8080` is
   **not** reachable off-box.
5. Admin: old path 404s; 5 bad logins trigger an axes lockout.
6. Rate limit: 21 rapid adds → 429 on the 21st; verify from two source IPs that budgets are separate.
7. `pip-audit -r requirements.txt` clean; `django.__version__` → 5.2.x; `python --version` → 3.12.x.
8. Key rotation: a pre-rotation admin session cookie is rejected.
9. Logs land in journald, not `/tmp`; `journalctl --disk-usage` bounded.

## Sequencing

| Window | Work |
|---|---|
| **1** (~4 h) | P0-1 TLS/proxy, P0-2 admin, P0-6 key + admin-password rotation. Deployment-side only, no code changes, no app rollback risk. |
| **2** (~4 h) | P0-3, P0-4, P0-5 in one branch with their tests — they share `forms.py` and the views refactor. **Do not split these.** |
| **3** (~4 h) | P1-1 runtime upgrade behind the now-existing suite, P1-2 deps, P1-4 systemd. Window 2's tests are what make the upgrade safe — that's why it's P1, not P0. |
| **4** (~2 h) | P2 cleanup, and the explicit go/no-go on P1-5 capability URLs. |

## Note on commits

Per `CLAUDE.md`, this is not a worktree — so instead of committing I'll write an executable
`commit.sh` at the repo root with Conventional-Commit messages (`fix:`, `chore:`, `test:`) split per
logical change, for you to run outside the sandbox.
