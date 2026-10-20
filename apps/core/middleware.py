import re
from django.conf import settings
from django.shortcuts import redirect
from django.utils import translation
from django.middleware.locale import LocaleMiddleware


class DefaultLanguageLocaleMiddleware(LocaleMiddleware):
    """Locale middleware whose fallback is always settings.LANGUAGE_CODE.

    Django's LocaleMiddleware honours the browser ``Accept-Language`` header, so
    a browser configured for Chinese would receive the Chinese UI even though
    English is the configured default. Here only an explicit choice (the
    language cookie written by the switcher) overrides the default, unless
    ``settings.LANGUAGE_FROM_BROWSER`` is enabled.
    """

    def process_request(self, request):
        if getattr(settings, 'LANGUAGE_FROM_BROWSER', False):
            return super().process_request(request)

        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE')
        request.META['HTTP_ACCEPT_LANGUAGE'] = ''
        try:
            return super().process_request(request)
        finally:
            if accept_language is None:
                request.META.pop('HTTP_ACCEPT_LANGUAGE', None)
            else:
                request.META['HTTP_ACCEPT_LANGUAGE'] = accept_language


class CharsetMiddleware:
    """Middleware to ensure all responses are served with UTF-8 charset.
    This fixes issues where both Chinese and English text appear garbled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Always set Content-Type with UTF-8 charset
        if 'Content-Type' not in response.headers:
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
        else:
            content_type = response.headers['Content-Type']
            if 'charset=' not in content_type.lower():
                response.headers['Content-Type'] = f"{content_type}; charset=utf-8"
        
        # Set other encoding-related headers
        response.headers['Content-Language'] = translation.get_language() or settings.LANGUAGE_CODE
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        return response

class LoginRequiredMiddleware:
    """Middleware that requires a user to be authenticated to view any page
    except those in LOGIN_EXEMPT_URLS. Add to MIDDLEWARE after
    AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        exempt = getattr(settings, 'LOGIN_EXEMPT_URLS', [])
        self.exempt_urls = [re.compile(expr) for expr in exempt]
        self.login_url = settings.LOGIN_URL

    def __call__(self, request):
        path = request.path_info.lstrip('/')

        # Always allow authenticated users
        if getattr(request, 'user', None) and request.user.is_authenticated:
            return self.get_response(request)

        # Allow exempted urls (admin/static/media/login/register etc.)
        for pattern in self.exempt_urls:
            if pattern.match(path):
                return self.get_response(request)

        # Not authenticated and not exempt -> redirect to login
        # preserve next param
        return redirect(f"{self.login_url}?next=/{path}")
