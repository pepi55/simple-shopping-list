"""
Rate limiting middleware for admin URLs.

This middleware limits the number of requests to admin URLs to prevent
brute force attacks against the admin interface.
"""
import time
from collections import defaultdict
from django.http import HttpResponseForbidden


class AdminRateLimiter:
    """Simple rate limiter for admin URLs.

    Limits requests to 10 per minute per IP address for admin URLs.
    """
    def __init__(self):
        self.requests = defaultdict(list)

    def __call__(self, get_response):
        def middleware(request):
            # Only apply to admin URLs
            if not request.path.startswith('/admin/'):
                return get_response(request)

            # Check if request is from an allowed IP (admin IPs)
            admin_ips = ['127.0.0.1', '192.168.2.43']
            if request.META.get('REMOTE_ADDR') not in admin_ips:
                return get_response(request)

            # Check rate limit
            now = time.time()
            minute_ago = now - 60

            # Clean old entries
            self.requests[request.META.get('REMOTE_ADDR', '')] = [
                t for t in self.requests[request.META.get('REMOTE_ADDR', '')]
                if t > minute_ago
            ]

            if len(self.requests[request.META.get('REMOTE_ADDR', '')]) >= 10:
                return HttpResponseForbidden('Rate limit exceeded. Try again later.')

            self.requests[request.META.get('REMOTE_ADDR', '')].append(now)
            return get_response(request)

        return middleware

    def reset(self):
        """Reset the rate limiter state."""
        self.requests.clear()
