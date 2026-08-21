from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

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


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RateLimitTests(TestCase):
    """P0-5. Uses an isolated LocMemCache per test so counts don't bleed
    across test methods -- production uses FileBasedCache (settings.py),
    the choice of backend doesn't matter to django-ratelimit's counting."""

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
