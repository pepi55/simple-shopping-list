import threading
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_ratelimit.checks import KNOWN_BROKEN_CACHE_BACKENDS
from django_ratelimit.core import is_ratelimited

import simple_shoppinglist.settings as production_settings
from shoppinglist.models import List

# The two literals that sat in public git history (P0-6). This is the only
# automated guard against reintroducing either of them.
LEAKED_SECRET_KEYS = {
    "django-insecure-km5bbn6yod9a8ue3z0==e0)2f*@il2&@5tm-l3@z)vkwhu#vqy",
    "!+5a)ca2t%&hr!nvh284^e#_*&332htki#l9@k039$#1qb4)^x",
}


class DeploymentSettingsTests(TestCase):
    """P0-1: these stay green forever and catch anyone reverting a setting."""

    def test_deploy_checks_pass(self):
        call_command("check", "--deploy", "--fail-level=WARNING")

    def test_secret_key_not_hardcoded(self):
        self.assertNotIn(settings.SECRET_KEY, LEAKED_SECRET_KEYS)

    def test_debug_is_false(self):
        self.assertFalse(settings.DEBUG)

    def test_insecure_request_redirects_to_https(self):
        response = self.client.get("/", secure=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_csrf_token_present_on_all_forms(self):
        shopping_list = List.objects.create(list_name="Groceries")
        response = self.client.get(reverse("shoppinglist:detail", args=[shopping_list.id]))
        content = response.content.decode()
        self.assertEqual(content.count("csrfmiddlewaretoken"), 3)


@override_settings(SECURE_SSL_REDIRECT=False)
class OutputEscapingTests(TestCase):
    """Autoescaping is the only XSS defence here, and it's implicit -- keep it that way."""

    def test_list_name_is_escaped_in_index(self):
        List.objects.create(list_name="<script>alert(1)</script>")
        response = self.client.get(reverse("shoppinglist:index"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


@override_settings(SECURE_SSL_REDIRECT=False)
class RateLimitTests(TestCase):
    """P0-5. Cleared per test so counts don't bleed across test methods. The
    backend matters (it must be atomic); see the two classes below."""

    def setUp(self):
        cache.clear()
        self.shopping_list = List.objects.create(list_name="Groceries")

    def test_add_is_rate_limited(self):
        url = reverse("shoppinglist:add_item", args=[self.shopping_list.id])
        for i in range(20):
            response = self.client.post(url, {"item_name": f"item{i}", "quantity": 1})
            self.assertEqual(response.status_code, 302)
        response = self.client.post(url, {"item_name": "one too many", "quantity": 1})
        self.assertEqual(response.status_code, 429)

    def test_delete_has_stricter_rate_limit(self):
        url = reverse("shoppinglist:delete", args=[self.shopping_list.id])
        for i in range(5):
            response = self.client.post(url, {"confirm": "yes"})
            self.assertEqual(response.status_code, 302)
        response = self.client.post(url, {"confirm": "yes"})
        self.assertEqual(response.status_code, 429)

    def test_rate_limit_is_per_ip(self):
        url = reverse("shoppinglist:add_item", args=[self.shopping_list.id])
        for i in range(20):
            self.client.post(
                url, {"item_name": f"a{i}", "quantity": 1}, REMOTE_ADDR="10.0.0.1"
            )
        blocked = self.client.post(
            url, {"item_name": "over", "quantity": 1}, REMOTE_ADDR="10.0.0.1"
        )
        self.assertEqual(blocked.status_code, 429)

        still_ok = self.client.post(
            url, {"item_name": "still ok", "quantity": 1}, REMOTE_ADDR="10.0.0.2"
        )
        self.assertEqual(still_ok.status_code, 302)


class RateLimitConcurrencyTests(SimpleTestCase):
    """A burst of parallel requests must not get past the limit. Under ASGI
    every request runs on its own thread, so this is what an attacker with
    parallel connections sees. Runs against whatever settings.CACHES is, so
    on the Pi it can be pointed at the production cache:

        python manage.py test shoppinglist.tests.test_security.RateLimitConcurrencyTests \\
            --settings=simple_shoppinglist.settings
    """

    THREADS = 50
    RATE = 5

    def test_rate_limit_holds_under_concurrent_burst(self):
        # A fresh group per run, so leftover counts in a shared cache can't
        # skew the result; a TEST-NET address can't collide with a real client.
        group = f"test-burst-{uuid.uuid4()}"
        request = RequestFactory().post("/", REMOTE_ADDR="203.0.113.7")
        barrier = threading.Barrier(self.THREADS)
        allowed = []
        errors = []

        def hit():
            try:
                barrier.wait()
                if not is_ratelimited(
                    request, group=group, key="ip", rate=f"{self.RATE}/m",
                    method="POST", increment=True,
                ):
                    allowed.append(1)
            except Exception as exc:  # surface it instead of losing it in the thread
                errors.append(exc)

        threads = [threading.Thread(target=hit) for _ in range(self.THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(allowed), self.RATE)


class ProductionRateLimitConfigTests(SimpleTestCase):
    """The test settings swap the cache out, so check the production module
    directly: a regression to a non-atomic backend (FileBasedCache let 50 of
    50 concurrent requests through a 5/m limit) must fail here."""

    def test_production_cache_backend_supports_atomic_increment(self):
        backend = production_settings.CACHES["default"]["BACKEND"]
        self.assertNotIn(backend, KNOWN_BROKEN_CACHE_BACKENDS)

    def test_ratelimit_system_checks_are_loaded(self):
        self.assertIn("django_ratelimit", production_settings.INSTALLED_APPS)

    def test_ratelimit_middleware_is_installed(self):
        self.assertIn(
            "django_ratelimit.middleware.RatelimitMiddleware", production_settings.MIDDLEWARE
        )
