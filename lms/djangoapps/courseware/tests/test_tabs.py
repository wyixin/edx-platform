from django.test import TestCase
from mock import MagicMock
from mock import patch
from collections import namedtuple

import xmodule.tabs as tabs

from django.test.utils import override_settings
from django.core.urlresolvers import reverse

from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from courseware.tests.modulestore_config import TEST_DATA_MIXED_MODULESTORE
from .helpers import LoginEnrollmentTestCase

class TabTestCase(TestCase):

    def setUp(self):

        self.course = MagicMock()
        self.course.id = 'edX/toy/2012_Fall'

    def check_tab(
            self, tab_class, dict_tab,
            expected_link,
            expected_active_page_name,
            incorrect_active_page_name='nope',
            expected_name='same',
            invalid_dict_tab={'none': 'wrong'},
            can_display=True
    ):
        # create tab
        tab = tab_class(dict_tab)

        # takes name from given tab
        self.assertEqual(tab.name, expected_name)

        # link is as expected
        self.assertEqual(tab.link_func(self.course), expected_link)

        # active page name
        self.assertTrue(tab.active_page_name == expected_active_page_name)
        self.assertFalse(tab.active_page_name == incorrect_active_page_name)

        # can display
        self.assertEqual(
            tab.can_display(self.course, is_user_authenticated=True, is_user_staff=True),
            can_display
        )

        # validate
        self.assertIsNone(tab.validate(dict_tab))
        if invalid_dict_tab:
            self.assertRaises(tabs.InvalidTabsException, tab.validate, invalid_dict_tab)

        # return tab for any additional tests
        return tab

class ProgressTestCase(TabTestCase):

    def test_progress(self):

        self.course.hide_progress_tab = False
        self.check_tab(
            tab_class = tabs.ProgressTab,
            dict_tab={'name': 'same'},
            expected_link=reverse('progress', args=[self.course.id]),
            expected_active_page_name='progress',
            invalid_dict_tab=None,
        )

        self.course.hide_progress_tab = True
        self.check_tab(
            tab_class = tabs.ProgressTab,
            dict_tab={'name': 'same'},
            expected_link=reverse('progress', args=[self.course.id]),
            expected_active_page_name='progress',
            can_display=False,
            invalid_dict_tab=None,
        )

class WikiTestCase(TabTestCase):

    @override_settings(WIKI_ENABLED=True)
    def test_wiki_enabled(self):

        self.check_tab(
            tab_class = tabs.WikiTab,
            dict_tab={'name': 'same'},
            expected_link=reverse('course_wiki', args=[self.course.id]),
            expected_active_page_name='wiki',
            can_display=True
        )

    @override_settings(WIKI_ENABLED=False)
    def test_wiki_enabled_false(self):

        self.check_tab(
            tab_class = tabs.WikiTab,
            dict_tab={'name': 'same'},
            expected_link=reverse('course_wiki', args=[self.course.id]),
            expected_active_page_name='wiki',
            can_display=False
        )


class ExternalLinkTestCase(TabTestCase):

    def test_external_link(self):

        self.check_tab(
            tab_class = tabs.ExternalLinkTab,
            dict_tab={'name': 'same', 'link': 'blink'},
            expected_link='blink',
            expected_active_page_name=None,
            can_display=True
        )

class StaticTabTestCase(TabTestCase):

    def test_static_tab(self):

        url_slug = 'schmug'

        self.check_tab(
            tab_class = tabs.StaticTab,
            dict_tab={'name': 'same', 'url_slug': url_slug},
            expected_link=reverse('static_tab', args=[self.course.id, url_slug]),
            expected_active_page_name='static_tab_schmug',
            incorrect_active_page_name='static_tab_schlug',
            can_display=True
        )

@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class StaticTabDateTestCase(LoginEnrollmentTestCase, ModuleStoreTestCase):
    def setUp(self):
        self.course = CourseFactory.create()
        self.page = ItemFactory.create(
            category="static_tab", parent_location=self.course.location,
            data="OOGIE BLOOGIE", display_name="new_tab"
        )
        # The following XML course is closed; we're testing that
        # static tabs still appear when the course is already closed
        self.xml_data = "static 463139"
        self.xml_url = "8e4cce2b4aaf4ba28b1220804619e41f"
        self.xml_course_id = 'edX/detached_pages/2014'

    def test_logged_in(self):
        self.setup_user()
        url = reverse('static_tab', args=[self.course.id, 'new_tab'])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("OOGIE BLOOGIE", resp.content)

    def test_anonymous_user(self):
        url = reverse('static_tab', args=[self.course.id, 'new_tab'])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("OOGIE BLOOGIE", resp.content)

    @patch.dict('django.conf.settings.FEATURES', {'DISABLE_START_DATES': False})
    def test_logged_in_xml(self):
        self.setup_user()
        url = reverse('static_tab', args=[self.xml_course_id, self.xml_url])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.xml_data, resp.content)

    @patch.dict('django.conf.settings.FEATURES', {'DISABLE_START_DATES': False})
    def test_anonymous_user_xml(self):
        url = reverse('static_tab', args=[self.xml_course_id, self.xml_url])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.xml_data, resp.content)


class TextbooksTestCase(TabTestCase):

    def setUp(self):
        super(TextbooksTestCase, self).setUp()

        self.dict_tab = MagicMock()
        A = MagicMock()
        T = MagicMock()
        A.title = 'Book1: Algebra'
        T.title = 'Book2: Topology'
        self.course.textbooks = [A, T]

    @override_settings(FEATURES={'ENABLE_TEXTBOOK': True})
    def test_textbooks1(self):

        i = 0
        tab = tabs.TextbookTabs(self.dict_tab)
        self.assertTrue(tab.can_display(self.course, is_user_authenticated=True, is_user_staff=True))
        for book in tab.books(self.course):
            expected_link = reverse('book', args=[self.course.id, i])
            self.assertEqual(book.link_func(self.course), expected_link)
            self.assertEqual(book.active_page_name, 'textbook/{0}'.format(i))
            self.assertNotEquals(book.active_page_name, 'nope')
            self.assertTrue(book.name.startswith('Book{0}:'.format(i+1)))
            i=i+1

    @override_settings(FEATURES={'ENABLE_TEXTBOOK': False})
    def test_textbooks0(self):

        tab = tabs.TextbookTabs(self.dict_tab)
        self.assertFalse(tab.can_display(self.course, is_user_authenticated=True, is_user_staff=True))


class KeyCheckerTestCase(TestCase):

    def setUp(self):

        self.valid_keys = ['a', 'b']
        self.invalid_keys = ['a', 'v', 'g']
        self.dict_value = {'a': 1, 'b': 2, 'c': 3}

    def test_key_checker(self):

        self.assertIsNone(tabs.key_checker(self.valid_keys)(self.dict_value))
        self.assertRaises(tabs.InvalidTabsException,
                          tabs.key_checker(self.invalid_keys), self.dict_value)


class NeedNameTestCase(TestCase):

    def setUp(self):

        self.valid_dict1 = {'a': 1, 'name': 2}
        self.valid_dict2 = {'name': 1}
        self.valid_dict3 = {'a': 1, 'name': 2, 'b': 3}
        self.invalid_dict = {'a': 1, 'b': 2}

    def test_need_name(self):
        self.assertIsNone(tabs.need_name(self.valid_dict1))
        self.assertIsNone(tabs.need_name(self.valid_dict2))
        self.assertIsNone(tabs.need_name(self.valid_dict3))
        self.assertRaises(tabs.InvalidTabsException, tabs.need_name, self.invalid_dict)


class ValidateTabsTestCase(TestCase):

    def setUp(self):

        self.courses = [MagicMock() for i in range(0, 7)]

        # invalid tabs
        self.courses[0].tabs = [{'type': 'courseware'}, {'type': 'fax'}]
        self.courses[1].tabs = [{'type': 'shadow'}, {'type': 'course_info'}]
        self.courses[2].tabs = [{'type': 'courseware'}, {'type': 'course_info'}, {'type': 'flying'}]
        self.courses[3].tabs = [{'type': 'course_info'}, {'type': 'courseware'}]

        # valid tabs
        self.courses[4].tabs = []
        self.courses[5].tabs = [
            {'type': 'courseware'},
            {'type': 'course_info', 'name': 'alice'},
            {'type': 'wiki', 'name': 'alice'},
            {'type': 'discussion', 'name': 'alice'},
            {'type': 'external_link', 'name': 'alice', 'link': 'blink'},
            {'type': 'textbooks'},
            {'type': 'pdf_textbooks'},
            {'type': 'html_textbooks'},
            {'type': 'progress', 'name': 'alice'},
            {'type': 'static_tab', 'name': 'alice', 'url_slug': 'schlug'},
            {'type': 'peer_grading'},
            {'type': 'staff_grading'},
            {'type': 'open_ended'},
            {'type': 'notes', 'name': 'alice'},
            {'type': 'syllabus'},
        ]
        self.courses[6].tabs = [
            {'type': 'courseware'},
            {'type': 'course_info', 'name': 'alice'},
            {'type': 'external_discussion', 'name': 'alice', 'link':'blink'}
        ]

    def test_validate_tabs(self):
        tab_list = tabs.CourseTabList()
        for i in range(0, 4):
            self.assertRaises(tabs.InvalidTabsException, tab_list.from_json, self.courses[i].tabs)

        for i in range(4, 7):
            from_json_result = tab_list.from_json(self.courses[i].tabs)
            self.assertEquals(len(from_json_result), len(self.courses[i].tabs))


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class DiscussionLinkTestCase(ModuleStoreTestCase):

    def setUp(self):
        self.tabs_with_discussion = create_tab_list(
        [
            {'type': 'courseware'},
            {'type': 'course_info', 'name': 'foo'},
            {'type': 'discussion', 'name': 'foo'},
            {'type': 'textbooks'},
        ])
        self.tabs_without_discussion = create_tab_list(
        [
            {'type': 'courseware'},
            {'type': 'course_info', 'name': 'foo'},
            {'type': 'textbooks'},
        ])

    @staticmethod
    def _patch_reverse(course):
        def patched_reverse(viewname, args):
            if viewname == "django_comment_client.forum.views.forum_form_discussion" and args == [course.id]:
                return "default_discussion_link"
            else:
                return None
        return patch("xmodule.tabs.reverse", patched_reverse)

    @patch.dict("django.conf.settings.FEATURES", {"ENABLE_DISCUSSION_SERVICE": False})
    def test_explicit_discussion_link(self):
        """Test that setting discussion_link overrides everything else"""
        course = CourseFactory.create(discussion_link="other_discussion_link", tabs=self.tabs_with_discussion)
        self.assertEqual(tabs.CourseTabList.get_discussion(course).link_func(course), "other_discussion_link")

    @patch.dict("django.conf.settings.FEATURES", {"ENABLE_DISCUSSION_SERVICE": False})
    def test_discussions_disabled(self):
        """Test that other cases return None with discussions disabled"""
        for i, t in enumerate([[], self.tabs_with_discussion, self.tabs_without_discussion]):
            course = CourseFactory.create(tabs=t, number=str(i))
            discussion = tabs.CourseTabList.get_discussion(course)
            self.assertTrue(discussion is None or discussion.link_func(course) is None)

    @patch.dict("django.conf.settings.FEATURES", {"ENABLE_DISCUSSION_SERVICE": True})
    def test_no_tabs(self):
        """Test a course without tabs configured"""
        course = CourseFactory.create(tabs=[])
        with self._patch_reverse(course):
            self.assertEqual(tabs.CourseTabList.get_discussion(course).link_func(course), "default_discussion_link")

    @patch.dict("django.conf.settings.FEATURES", {"ENABLE_DISCUSSION_SERVICE": True})
    def test_tabs_with_discussion(self):
        """Test a course with a discussion tab configured"""
        course = CourseFactory.create(tabs=self.tabs_with_discussion)
        with self._patch_reverse(course):
            self.assertEqual(tabs.CourseTabList.get_discussion(course).link_func(course), "default_discussion_link")

    @patch.dict("django.conf.settings.FEATURES", {"ENABLE_DISCUSSION_SERVICE": True})
    def test_tabs_without_discussion(self):
        """Test a course with tabs configured but without a discussion tab"""
        course = CourseFactory.create(tabs=self.tabs_without_discussion)
        discussion = tabs.CourseTabList.get_discussion(course)
        self.assertTrue(discussion is None or discussion.link_func(course) is None)


def create_tab_list(dict_tabs):
#    tab_list = tabs.CourseTabList()
#    tab_list.from_json(dict_tabs)
#    return tab_list
    return dict_tabs
