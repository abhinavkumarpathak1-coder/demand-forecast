"""Smoke tests: rendering, languages, localization."""
from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import TestCase
from django.utils import translation

URLS = [
    '/', '/data/upload/', '/data/view/', '/data/adjust/',
    '/insight/', '/model/train/', '/model/results/',
    '/forecast/', '/forecast/results/', '/forecast/what-if/',
    '/user/login/', '/user/dashboard/', '/user/register/', '/user/permissions/',
]

LANGUAGES = ('en', 'zh-hans', 'fr', 'de', 'es', 'ja')

CHINESE_MENU = ['首页', '数据管理', '数据洞察', '模型训练', '需求预测', 'What-If 分析']
ENGLISH_MENU = ['Home', 'Data Management', 'Data Insight', 'Model Training',
                'Demand Forecast', 'What-If Analysis']


class PageRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.create_user(username='smoke', password='smoke-pass-123')

    def test_pages_render_in_all_languages(self):
        self.client.login(username='smoke', password='smoke-pass-123')
        for lang in LANGUAGES:
            self.client.cookies['django_language'] = lang
            for url in URLS:
                with self.subTest(lang=lang, url=url):
                    self.assertIn(self.client.get(url).status_code, (200, 302))


class LanguageSwitchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.create_user(username='smoke', password='smoke-pass-123')

    def test_default_is_english_even_with_chinese_browser(self):
        self.client.login(username='smoke', password='smoke-pass-123')
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='zh-CN,zh;q=0.9,en;q=0.8')
        self.assertEqual(response.wsgi_request.LANGUAGE_CODE, 'en')
        for item in ENGLISH_MENU:
            self.assertContains(response, item)

    def test_switch_to_english_and_back(self):
        self.client.login(username='smoke', password='smoke-pass-123')

        response = self.client.post('/i18n/setlang/', {'language': 'en', 'next': '/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.cookies['django_language'].value, 'en')
        response = self.client.get('/')
        self.assertContains(response, 'Welcome to the Demand Forecast System')
        for item in ENGLISH_MENU:
            self.assertContains(response, item)

        self.client.post('/i18n/setlang/', {'language': 'zh-hans', 'next': '/'})
        response = self.client.get('/')
        self.assertContains(response, '欢迎使用需求预测系统')
        for item in CHINESE_MENU:
            self.assertContains(response, item)
        for item in ENGLISH_MENU:
            self.assertNotContains(response, '<span class="nav-text">%s</span>' % item)

    def test_language_names_are_always_native(self):
        """The picker lists every language in its own language."""
        self.client.login(username='smoke', password='smoke-pass-123')
        for lang in LANGUAGES:
            self.client.cookies['django_language'] = lang
            response = self.client.get('/')
            for name in ('English', '中文', 'Français', 'Deutsch', 'Español', '日本語'):
                with self.subTest(lang=lang, name=name):
                    self.assertContains(response, name)

    def test_top_bar_holds_account_and_switcher(self):
        self.client.login(username='smoke', password='smoke-pass-123')
        html = self.client.get('/').content.decode()
        self.assertIn('top-bar', html)
        self.assertIn('account-chip', html)
        self.assertIn('smoke', html)
        self.assertNotIn('sidebar-footer', html)


class LocalizedDateTests(TestCase):
    def render(self, lang):
        with translation.override(lang):
            template = Template('{% load i18n_dates %}{{ d|localize_date }}|{{ m|localize_month }}')
            return template.render(Context({'d': '2025-01-15', 'm': '2025-03'}))

    def test_dates_follow_the_active_language(self):
        self.assertTrue(self.render('en').startswith('Jan. 15, 2025'))
        self.assertTrue(self.render('zh-hans').startswith('2025年1月15日'))
        self.assertTrue(self.render('ja').startswith('2025年1月15日'))
        self.assertTrue(self.render('fr').startswith('15 janvier 2025'))
        self.assertTrue(self.render('de').startswith('15. Januar 2025'))
        self.assertTrue(self.render('es').startswith('15 de enero de 2025'))

    def test_months_follow_the_active_language(self):
        self.assertIn('March 2025', self.render('en'))
        self.assertIn('2025年3月', self.render('zh-hans'))
        self.assertIn('2025年3月', self.render('ja'))
        self.assertIn('mars 2025', self.render('fr'))
        self.assertIn('März 2025', self.render('de'))
        self.assertIn('marzo 2025', self.render('es'))
