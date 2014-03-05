"""
Implement CourseTab
"""
from abc import ABCMeta, abstractmethod

from xblock.fields import List
from xmodule.modulestore import Location

from django.conf import settings
from django.core.urlresolvers import reverse

# We only need to scrape strings for i18n in this file, since ugettext is called on them in the template:
# https://github.com/edx/edx-platform/blob/master/lms/templates/courseware/course_navigation.html#L29
_ = lambda text: text


class CourseTab(object):  # pylint: disable=incomplete-protocol
    '''
    The Course Tab class is a data abstraction for all tabs (i.e., course navigation links) within a course.
    It is an abstract class - to be inherited by various tab types.  Derived classes are expected to implement
    all abstract methods and override methods as needed.
    When a new tab class is created, its type should also be added in this class' factory method.
    '''
    __metaclass__ = ABCMeta

    def __init__(self, name, active_page_name, link_func):
        '''
        Initializes class members with values passed in by subclasses.
        '''

        # name of the tab
        self.name = name

        # used by UI layers to display which tab is active
        self.active_page_name = active_page_name

        # function that computes the link for the tab, given the course as an input parameter
        self.link_func = link_func

    @abstractmethod
    def type(self):
        '''
        Abstract method to be implemented by subclasses.  It is generally a constant value for a
        subclass, shared by all instances of the subclass.
        '''
        pass

    def can_display(self, course, is_user_authenticated, is_user_staff):  # pylint: disable=unused-argument
        '''
        Determines whether the tab should be displayed in the UI for the given course and a particular user.
        This method is to be overridden by subclasses when applicable.  The base class implementation
        always returns True.

        'course' is an xModule CourseDescriptor

        'is_user_authenticated' indicates whether the user is authenticated.  If the tab is of
         type AuthenticatedCourseTab and this value is False, then can_display will return False.

        'is_user_staff' indicates whether the user has staff access to the course.  If the tab is of
         type StaffTab and this value is False, then can_display will return False.

        Returns a boolean value to indicate whether this instance of the tab should be displayed to a
        given user for the given course.
        '''
        return True

    def get(self, key, default=None):
        '''
        Akin to the get method on Python dictionary objects, gracefully returns the value associated with the
        given key, or the default if key does not exist.
        '''
        if key == 'name':
            return self.name
        elif key == 'type':
            return self.type()
        elif key == 'active_page_name':
            return self.active_page_name
        else:
            return default

    def __getitem__(self, key):
        '''
        This method allows callers to access CourseTab members with the d[key] syntax as is done with
        Python dictionary objects.
        '''
        item = self.get(key=key, default=KeyError)
        if item is KeyError:
            raise KeyError()
        else:
            return item

    def __setitem__(self, key, value):
        '''
        This method allows callers to change CourseTab members with the d[key]=value syntax as is done with
        Python dictionary objects.  For example: course_tab['name'] = new_name

        Note: the 'type' member can be 'get', but not 'set'.
        '''
        if key == 'name':
            self.name = value
        elif key == 'active_page_name':
            self.active_page_name = value
        else:
            raise KeyError()

    # pylint: disable=incomplete-protocol
    # Note: pylint complains that we do not implement __delitem__ and __len__, although we implement __setitem__
    # and __getitem__.  However, the former two do not apply to this class so we do not implement them.  The
    # reason we implement the latter two is to enable callers to continue to use the CourseTab object with dict-type
    # accessors.

    @classmethod
    def validate(cls, tab):
        """
        Validates the given dict-type tab object to ensure it contains the expected keys.
        This method should be overridden by subclasses that require certain keys to be persisted in the tab.
        """
        pass

    @classmethod
    def factory(cls, tab):
        '''
        Factory method that creates a CourseTab object for the given dict-type tab.  The subclass that is
        instantiated is determined by the value of the 'type' key in the given dict-type tab.  The given
        dict-type tab is validated before instantiating the CourseTab object.
        '''
        sub_class_types = {
            'courseware': CoursewareTab,
            'course_info': CourseInfoTab,
            'wiki': WikiTab,
            'discussion': DiscussionTab,
            'external_discussion': ExternalDiscussionTab,
            'external_link': ExternalLinkTab,
            'textbooks': TextbookTabs,
            'pdf_textbooks': PDFTextbookTabs,
            'html_textbooks': HtmlTextbookTabs,
            'progress': ProgressTab,
            'static_tab': StaticTab,
            'peer_grading': PeerGradingTab,
            'staff_grading': StaffGradingTab,
            'open_ended': OpenEndedGradingTab,
            'notes': NotesTab,
            'syllabus': SyllabusTab,
            'instructor': InstructorTab,  # not persisted
        }

        tab_type = tab['type']
        if tab_type not in sub_class_types:
            raise InvalidTabsException(
                'Unknown tab type {0}. Known types: {1}'.format(tab_type, sub_class_types)
            )

        tab_class = sub_class_types[tab['type']]
        tab_class.validate(tab)
        return tab_class(tab=tab)

    def to_json(self):
        '''
        Serializes the necessary members of the CourseTab object.
        This method is overridden by subclasses that have more members to serialize.
        '''
        return {'type': self.type(), 'name': self.name}


class AuthenticatedCourseTab(CourseTab):  # pylint: disable=incomplete-protocol
    '''
    Abstract class for tabs that can be accessed by only authenticated users.
    '''
    def can_display(self, course, is_user_authenticated, is_user_staff):
        return is_user_authenticated


class StaffTab(CourseTab):  # pylint: disable=incomplete-protocol
    '''
    Abstract class for tabs that can be accessed by only users with staff access.
    '''
    def can_display(self, course, is_user_authenticated, is_user_staff):  # pylint: disable=unused-argument
        return is_user_staff


class CoursewareTab(CourseTab):  # pylint: disable=incomplete-protocol
    """
    A tab containing the course content.
    """

    def type(self):
        return 'courseware'

    def __init__(self, tab=None):  # pylint: disable=unused-argument
        # Translators: 'Courseware' refers to the tab in the courseware that leads to the content of a course
        super(CoursewareTab, self).__init__(
            name=_('Courseware'),
            active_page_name=self.type(),
            link_func=link_reverse_func(self.type()),
        )


class CourseInfoTab(CourseTab):  # pylint: disable=incomplete-protocol
    """
    A tab containing information about the course.
    """

    def type(self):
        return 'course_info'

    def __init__(self, tab=None):
        # Translators: "Course Info" is the name of the course's information and updates page
        super(CourseInfoTab, self).__init__(
            name=tab['name'] if tab else _('Course Info'),
            active_page_name='info',
            link_func=link_reverse_func('info'),
        )

    @classmethod
    def validate(cls, tab):
        need_name(tab)


class ProgressTab(AuthenticatedCourseTab):  # pylint: disable=incomplete-protocol
    """
    A tab containing information about the authenticated user's progress.
    """

    def type(self):
        return 'progress'

    def __init__(self, tab=None):
        super(ProgressTab, self).__init__(
            name=tab['name'] if tab else _('Progress'),
            active_page_name=type,
            link_func=link_reverse_func(self.type()),
        )

    def can_display(self, course, is_user_authenticated, is_user_staff):
        return not course.hide_progress_tab


class WikiTab(CourseTab):  # pylint: disable=incomplete-protocol
    """
    A tab containing the course wiki.
    """

    def type(self):
        return 'wiki'

    def __init__(self, tab=None):
        super(WikiTab, self).__init__(
            name=tab['name'] if tab else _('Wiki'),
            active_page_name=self.type(),
            link_func=link_reverse_func('course_wiki'),
        )

    def can_display(self, course, is_user_authenticated, is_user_staff):
        return settings.WIKI_ENABLED

    @classmethod
    def validate(cls, tab):
        need_name(tab)


class DiscussionTab(CourseTab):  # pylint: disable=incomplete-protocol
    """
    A tab only for the new Berkeley discussion forums.
    """

    def type(self):
        return 'discussion'

    def __init__(self, tab=None):
        # Translators: "Discussion" is the title of the course forum page
        super(DiscussionTab, self).__init__(
            name=tab['name'] if tab else _('Discussion'),
            active_page_name=self.type(),
            link_func=link_reverse_func('django_comment_client.forum.views.forum_form_discussion'),
        )

    def can_display(self, course, is_user_authenticated, is_user_staff):
        return settings.FEATURES.get('ENABLE_DISCUSSION_SERVICE')

    @classmethod
    def validate(cls, tab):
        need_name(tab)


class LinkTab(CourseTab):  # pylint: disable=incomplete-protocol
    '''
    Abstract class for tabs that contain external links.
    '''
    link_value = ''

    def __init__(self, name, active_page_name, link_value):
        self.link_value = link_value
        super(LinkTab, self).__init__(
            name=name,
            active_page_name=active_page_name,
            link_func=link_value_func(self.link_value),
        )

    def get(self, key, default=None):
        if key == 'link':
            return self.link_value
        else:
            return super(LinkTab, self).get(key)

    def __setitem__(self, key, value):
        if key == 'link':
            self.link_value = value
        else:
            super(LinkTab, self).__setitem__(key, value)


class ExternalDiscussionTab(LinkTab):  # pylint: disable=incomplete-protocol
    """
    A tab that links to an external discussion service.
    """

    def type(self):
        return 'external_discussion'

    def __init__(self, tab=None, link_value=None):
        link_value = tab['link'] if tab else link_value
        # Translators: 'Discussion' refers to the tab in the courseware that leads to the discussion forums
        super(ExternalDiscussionTab, self).__init__(
            name=_('Discussion'),
            active_page_name='discussion',
            link_value=self.link_value,
        )

    @classmethod
    def validate(cls, tab):
        key_checker(['link'])(tab)

    def to_json(self):
        return {'type': self.type(), 'name': self.name, 'link': self.link_value}


class ExternalLinkTab(LinkTab):  # pylint: disable=incomplete-protocol
    '''
    A tab containing an external link.
    '''
    def type(self):
        return 'external_link'

    def __init__(self, tab):
        super(ExternalLinkTab, self).__init__(
            name=tab['name'],
            active_page_name='',  # External links are never active.
            link_value=tab['link'],
        )

    @classmethod
    def validate(cls, tab):
        key_checker(['name', 'link'])(tab)


class StaticTab(CourseTab):  # pylint: disable=incomplete-protocol
    '''
    A custom tab.
    '''
    url_slug = ''

    def type(self):
        return 'static_tab'

    @classmethod
    def validate(cls, tab):
        key_checker(['name', 'url_slug'])(tab)

    def __init__(self, tab=None, name=None, url_slug=None):
        self.url_slug = tab['url_slug'] if tab else url_slug
        tab_name = tab['name'] if tab else name
        super(StaticTab, self).__init__(
            name=tab_name,
            active_page_name='static_tab_{0}'.format(self.url_slug),
            link_func=lambda course: reverse(self.type(), args=[course.id, self.url_slug]),
        )

    def get(self, key, default=None):
        if key == 'url_slug':
            return self.url_slug
        else:
            return super(StaticTab, self).get(key)

    def __setitem__(self, key, value):
        if key == 'url_slug':
            self.url_slug = value
        else:
            super(StaticTab, self).__setitem__(key, value)

    def get_location(self, course):
        '''
        Returns the location for this static tab for the given course.
        '''
        return Location(
            course.location.tag, course.location.org, course.location.course,
            'static_tab',
            self.url_slug
        )

    def to_json(self):
        return {'type': self.type(), 'name': self.name, 'url_slug': self.url_slug}


class SingleTextbookTab(CourseTab):  # pylint: disable=incomplete-protocol
    '''
    A tab representing a single textbook.  It is created temporarily when enumerating all textbooks within a
    Textbook collection tab.  It should not be serialized or persisted.
    '''
    def type(self):
        return 'single_textbook'

    def to_json(self):
        raise NotImplementedError('SingleTextbookTab should not be serialized.')


class TextbookTabsType(AuthenticatedCourseTab):  # pylint: disable=incomplete-protocol
    '''
    Abstract class for textbook collection tabs classes.
    '''
    def __init__(self, tab=None):  # pylint: disable=unused-argument
        super(TextbookTabsType, self).__init__('', '', '')

    @abstractmethod
    def books(self, course):
        '''
        A generator for iterating through all the SingleTextbookTab book objects associated with this
        collection of textbooks.
        '''
        pass


class TextbookTabs(TextbookTabsType):  # pylint: disable=incomplete-protocol
    '''
    A tab representing the collection of all textbook tabs.
    '''
    def type(self):
        return 'textbooks'

    def can_display(self, course, is_user_authenticated, is_user_staff):
        return settings.FEATURES.get('ENABLE_TEXTBOOK')

    def books(self, course):
        for index, textbook in enumerate(course.textbooks):
            yield SingleTextbookTab(
                name=textbook.title,
                active_page_name='textbook/{0}'.format(index),
                link_func=lambda course: reverse('book', args=[course.id, index]),
            )


class PDFTextbookTabs(TextbookTabsType):  # pylint: disable=incomplete-protocol
    '''
    A tab representing the collection of all PDF textbook tabs.
    '''
    def type(self):
        return 'pdf_textbooks'

    def books(self, course):
        for index, textbook in enumerate(course.pdf_textbooks):
            yield SingleTextbookTab(
                name=textbook['tab_title'],
                active_page_name='pdftextbook/{0}'.format(index),
                link_func=lambda course: reverse('pdf_book', args=[course.id, index]),
            )


class HtmlTextbookTabs(TextbookTabsType):  # pylint: disable=incomplete-protocol
    '''
    A tab representing the collection of all Html textbook tabs.
    '''
    def type(self):
        return 'html_textbooks'

    def books(self, course):
        for index, textbook in enumerate(course.html_textbooks):
            yield SingleTextbookTab(
                name=textbook['tab_title'],
                active_page_name='htmltextbook/{0}'.format(index),
                link_func=lambda course: reverse('html_book', args=[course.id, index]),
            )


class GradingTab(object):
    '''
    Abstract class for tabs that involve Grading.
    '''
    pass


class StaffGradingTab(StaffTab, GradingTab):  # pylint: disable=incomplete-protocol
    '''
    A tab for staff grading.
    '''
    def type(self):
        return 'staff_grading'

    def __init__(self, tab=None):  # pylint: disable=unused-argument
        # Translators: "Staff grading" appears on a tab that allows
        # staff to view open-ended problems that require staff grading
        super(StaffGradingTab, self).__init__(
            name=_("Staff grading"),
            active_page_name=self.type(),
            link_func=link_reverse_func(self.type()),
        )


class PeerGradingTab(AuthenticatedCourseTab, GradingTab):  # pylint: disable=incomplete-protocol
    '''
    A tab for peer grading.
    '''
    def type(self):
        return 'peer_grading'

    def __init__(self, tab=None):  # pylint: disable=unused-argument
        # Translators: "Peer grading" appears on a tab that allows
        # students to view open-ended problems that require grading
        super(PeerGradingTab, self).__init__(
            name=_("Peer grading"),
            active_page_name=self.type(),
            link_func=link_reverse_func(self.type()),
        )


class OpenEndedGradingTab(AuthenticatedCourseTab, GradingTab):  # pylint: disable=incomplete-protocol
    '''
    A tab for open ended grading.
    '''
    def type(self):
        return 'open_ended'

    def __init__(self, tab=None):  # pylint: disable=unused-argument
        # Translators: "Open Ended Panel" appears on a tab that, when clicked, opens up a panel that
        # displays information about open-ended problems that a user has submitted or needs to grade
        super(OpenEndedGradingTab, self).__init__(
            name=_("Open Ended Panel"),
            active_page_name=self.type(),
            link_func=link_reverse_func('open_ended_notifications'),
        )


class SyllabusTab(CourseTab):  # pylint: disable=incomplete-protocol
    '''
    A tab for the course syllabus.
    '''
    def type(self):
        return 'syllabus'

    def can_display(self, course, is_user_authenticated, is_user_staff):
        return hasattr(course, 'syllabus_present') and course.syllabus_present

    def __init__(self, tab=None):  # pylint: disable=unused-argument
        super(SyllabusTab, self).__init__(
            # Translators: "Syllabus" appears on a tab that, when clicked, opens the syllabus of the course.
            name=_('Syllabus'),
            active_page_name=self.type(),
            link_func=link_reverse_func(self.type()),
        )


class NotesTab(AuthenticatedCourseTab):  # pylint: disable=incomplete-protocol
    '''
    A tab for the course notes.
    '''
    def type(self):
        return 'notes'

    def can_display(self, course, is_user_authenticated, is_user_staff):
        return settings.FEATURES.get('ENABLE_STUDENT_NOTES')

    def __init__(self, tab=None):
        super(NotesTab, self).__init__(
            name=tab['name'],
            active_page_name=self.type(),
            link_func=link_reverse_func(self.type()),
        )


class InstructorTab(StaffTab):  # pylint: disable=incomplete-protocol
    '''
    A tab for the course instructors.
    '''
    def type(self):
        return 'instructor'

    def __init__(self, tab=None):  # pylint: disable=unused-argument
        # Translators: 'Instructor' appears on the tab that leads to the instructor dashboard, which is
        # a portal where an instructor can get data and perform various actions on their course
        super(InstructorTab, self).__init__(
            name=_('Instructor'),
            active_page_name=self.type(),
            link_func=link_reverse_func('instructor_dashboard'),
        )


class CourseTabList(List):
    '''
    An XField class that encapsulates a collection of Tabs in a course.
    It is automatically created and can be retrieved through a CourseDescriptor object: course.tabs
    '''

    @staticmethod
    def initialize_default(course):
        '''
        An explicit initialize method is used to set the default values, rather than implementing an
        __init__ method.  This is because the default values are dependent on other information from
        within the course.
        '''

        course.tabs.append(CoursewareTab())
        course.tabs.append(CourseInfoTab())
        course.tabs.append(SyllabusTab())
        course.tabs.append(TextbookTabs())

        # # If they have a discussion link specified, use that even if we feature
        # # flag discussions off. Disabling that is mostly a server safety feature
        # # at this point, and we don't need to worry about external sites.
        if course.discussion_link:
            course.tabs.append(ExternalDiscussionTab(None, course.discussion_link))
        else:
            course.tabs.append(DiscussionTab())

        course.tabs.append(WikiTab())
        course.tabs.append(ProgressTab())

    @staticmethod
    def get_discussion(course):
        '''
        Returns the discussion tab for the given course.  It can be either of type DiscussionTab
        or ExternalDiscussionTab.  The returned tab object is self-aware of the 'link' that it corresponds to.
        '''
        for tab in course.tabs:
            if isinstance(tab, DiscussionTab) or isinstance(tab, ExternalDiscussionTab):
                return tab
        return None

    @staticmethod
    def get_tab_by_slug(course, url_slug):
        """
        Look for a tab with the specified 'url_slug'.  Returns the tab or None if not found.
        """
        for tab in course.tabs:
            # The validation code checks that these exist.
            if tab.get('url_slug') == url_slug:
                return tab
        return None

    @staticmethod
    def iterate_displayable(course, is_user_authenticated=True, is_user_staff=True):
        '''
        Generator method for iterating through all tabs that can be displayed for the given course and
        the given user with the provided access settings.
        '''
        for tab in course.tabs:
            if tab.can_display(course, is_user_authenticated, is_user_staff):
                if isinstance(tab, TextbookTabsType):
                    for book in tab.books(course):
                        yield book
                else:
                    yield tab
        instructor_tab = InstructorTab()
        if instructor_tab.can_display(course, is_user_authenticated, is_user_staff):
            yield instructor_tab

    @classmethod
    def _validate_tabs(cls, tabs):
        """
        Check that the tabs set for the specified course is valid.  If it
        isn't, raise InvalidTabsException with the complaint.

        Specific rules checked:
        - if no tabs specified, that's fine
        - if tabs specified, first two must have type 'courseware' and 'course_info', in that order.

        """
        if tabs is None or len(tabs) == 0:
            return

        if len(tabs) < 2:
            raise InvalidTabsException("Expected at least two tabs.  tabs: '{0  }'".format(tabs))

        if tabs[0]['type'] != 'courseware':
            raise InvalidTabsException(
                "Expected first tab to have type 'courseware'.  tabs: '{0}'".format(tabs))

        if tabs[1]['type'] != 'course_info':
            raise InvalidTabsException(
                "Expected second tab to have type 'course_info'.  tabs: '{0}'".format(tabs))

            # Possible other checks: make sure tabs that should only appear once (e.g. courseware)
            # are actually unique (otherwise, will break active tag code)

    def to_json(self, values):
        '''
        Overrides the to_json method to serialize all the CourseTab objects.
        '''
        json_data = []
        if values:
            for val in values:
                if isinstance(val, CourseTab):
                    json_data.append(val.to_json())
                elif isinstance(val, dict):
                    json_data.append(val)
                else:
                    continue
        return json_data

    def from_json(self, values):
        '''
        Overrides the from_json method to de-serialize all the CourseTab objects.
        '''
        self._validate_tabs(values)
        tabs = []
        for tab in values:
            tabs.append(CourseTab.factory(tab))
        return tabs


#### Link Functions
def link_reverse_func(reverse_name):
    """
    Returns a function that takes in a course and calls the django reverse URL lookup with the course' ID.
    """
    return lambda course: reverse(reverse_name, args=[course.id])


def link_value_func(value):
    """
    Returns a function takes in a course and returns the given value.
    """
    return lambda course: value


#### Validators
#  A validator takes a dict and raises InvalidTabsException if required fields are missing or otherwise wrong.
# (e.g. "is there a 'name' field?).  Validators can assume that the type field is valid.
def key_checker(expected_keys):
    """
    Returns a function that checks that specified keys are present in a dict.
    """

    def check(dictionary):
        '''
        Function that checks whether all keys in the expected_keys object is in the given dictionary.
        '''
        for key in expected_keys:
            if key not in dictionary:
                raise InvalidTabsException(
                    'Key {0} not present in {1}'.format(key, dictionary)
                )

    return check


def need_name(dictionary):
    '''
    Returns whether the 'name' key exists in the given dictionary.
    '''
    key_checker(['name'])(dictionary)


class InvalidTabsException(Exception):
    """
    A complaint about invalid tabs.
    """
    pass
