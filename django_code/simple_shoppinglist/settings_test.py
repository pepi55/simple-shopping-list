"""
Settings for running the test suite:

    python manage.py test shoppinglist --settings=simple_shoppinglist.settings_test

Supplies the env vars settings.py and urls.py require, and swaps the shared
rate-limit cache for a per-process one so test runs neither need memcached
nor spend the live service's rate-limit budget.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-only-" + "abcdefghij" * 6)  # >= 50 chars, >= 5 distinct (security.W009)
os.environ.setdefault("ALLOWED_HOSTS", "localhost")
os.environ.setdefault("ADMIN_URL", "mgmt/")  # read by urls.py, not settings.py

from .settings import *  # noqa: E402,F401,F403

# LocMemCache is atomic but per-process: right for one test process, wrong for
# production, which is why django-ratelimit flags it. Production keeps
# memcached, and test_security.ProductionRateLimitConfigTests guards that.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]
