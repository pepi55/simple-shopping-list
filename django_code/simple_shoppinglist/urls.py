"""
URL configuration for simple_shoppinglist project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import os

from django.http import HttpRequest, HttpResponse
from django.urls import include, path
from django.contrib import admin


def robots_txt(request: HttpRequest) -> HttpResponse:
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type = "text/plain")


urlpatterns = [
        # Path lives in the env, not here -- this file is on public GitHub,
        # so this buys little on its own. django-axes (settings.py) is the
        # actual control.
        path(os.environ["ADMIN_URL"], admin.site.urls),
        path('robots.txt', robots_txt),
        path('', include("shoppinglist.urls")),
        #path('', include("pwa.urls")),

]
