from django.conf import settings


def languages(request):
    """Expose the configured languages with their native (untranslated) names.

    ``settings.LANGUAGES`` intentionally stores the name of each language in
    that language (English / 中文 / Français ...). Django's ``{% get_available_languages %}``
    would translate those names again - with its own catalogues "English" would
    become 英语 or Anglais - so the switcher uses this variable instead.
    """
    return {'AVAILABLE_LANGUAGES_NATIVE': settings.LANGUAGES}
