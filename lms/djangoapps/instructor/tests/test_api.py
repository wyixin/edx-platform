"""
Unit tests for instructor.api methods.
"""
# pylint: disable=E1111
import unittest
import json
import requests
import datetime
from urllib import quote
from django.test import TestCase
from nose.tools import raises
from mock import Mock, patch
from django.test.utils import override_settings
from django.core.urlresolvers import reverse
from django.http import HttpRequest, HttpResponse
from django_comment_common.models import FORUM_ROLE_COMMUNITY_TA
from django.core import mail
from django.utils.timezone import utc

from django.contrib.auth.models import User
from courseware.tests.modulestore_config import TEST_DATA_MIXED_MODULESTORE
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from courseware.tests.helpers import LoginEnrollmentTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from student.tests.factories import UserFactory
from courseware.tests.factories import StaffFactory, InstructorFactory, BetaTesterFactory
from student.roles import CourseBetaTesterRole

from student.models import CourseEnrollment, CourseEnrollmentAllowed
from courseware.models import StudentModule

# modules which are mocked in test cases.
import instructor_task.api
from instructor.access import allow_access
import instructor.views.api
from instructor.views.api import _split_input_list, _msk_from_problem_urlname, common_exceptions_400
from instructor_task.api_helper import AlreadyRunningError

from .test_tools import get_extended_due


@common_exceptions_400
def view_success(request):  # pylint: disable=W0613
    "A dummy view for testing that returns a simple HTTP response"
    return HttpResponse('success')


@common_exceptions_400
def view_user_doesnotexist(request):  # pylint: disable=W0613
    "A dummy view that raises a User.DoesNotExist exception"
    raise User.DoesNotExist()


@common_exceptions_400
def view_alreadyrunningerror(request):  # pylint: disable=W0613
    "A dummy view that raises an AlreadyRunningError exception"
    raise AlreadyRunningError()


class TestCommonExceptions400(unittest.TestCase):
    """
    Testing the common_exceptions_400 decorator.
    """
    def setUp(self):
        self.request = Mock(spec=HttpRequest)
        self.request.META = {}

    def test_happy_path(self):
        resp = view_success(self.request)
        self.assertEqual(resp.status_code, 200)

    def test_user_doesnotexist(self):
        self.request.is_ajax.return_value = False
        resp = view_user_doesnotexist(self.request)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("User does not exist", resp.content)

    def test_user_doesnotexist_ajax(self):
        self.request.is_ajax.return_value = True
        resp = view_user_doesnotexist(self.request)
        self.assertEqual(resp.status_code, 400)
        result = json.loads(resp.content)
        self.assertIn("User does not exist", result["error"])

    def test_alreadyrunningerror(self):
        self.request.is_ajax.return_value = False
        resp = view_alreadyrunningerror(self.request)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Task is already running", resp.content)

    def test_alreadyrunningerror_ajax(self):
        self.request.is_ajax.return_value = True
        resp = view_alreadyrunningerror(self.request)
        self.assertEqual(resp.status_code, 400)
        result = json.loads(resp.content)
        self.assertIn("Task is already running", result["error"])


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPIDenyLevels(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Ensure that users cannot access endpoints they shouldn't be able to.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.user = UserFactory.create()
        CourseEnrollment.enroll(self.user, self.course.id)

        self.problem_urlname = 'robot-some-problem-urlname'
        _module = StudentModule.objects.create(
            student=self.user,
            course_id=self.course.id,
            module_state_key=_msk_from_problem_urlname(
                self.course.id,
                self.problem_urlname
            ),
            state=json.dumps({'attempts': 10}),
        )

        # Endpoints that only Staff or Instructors can access
        self.staff_level_endpoints = [
            ('students_update_enrollment', {'emails': 'foo@example.org', 'action': 'enroll'}),
            ('get_grading_config', {}),
            ('get_students_features', {}),
            ('get_distribution', {}),
            ('get_student_progress_url', {'unique_student_identifier': self.user.username}),
            ('reset_student_attempts', {'problem_to_reset': self.problem_urlname, 'unique_student_identifier': self.user.email}),
            ('update_forum_role_membership', {'email': self.user.email, 'rolename': 'Moderator', 'action': 'allow'}),
            ('list_forum_members', {'rolename': FORUM_ROLE_COMMUNITY_TA}),
            ('proxy_legacy_analytics', {'aname': 'ProblemGradeDistribution'}),
            ('send_email', {'send_to': 'staff', 'subject': 'test', 'message': 'asdf'}),
            ('list_instructor_tasks', {}),
            ('list_background_email_tasks', {}),
            ('list_report_downloads', {}),
            ('calculate_grades_csv', {}),
        ]
        # Endpoints that only Instructors can access
        self.instructor_level_endpoints = [
            ('bulk_beta_modify_access', {'emails': 'foo@example.org', 'action': 'add'}),
            ('modify_access', {'unique_student_identifier': self.user.email, 'rolename': 'beta', 'action': 'allow'}),
            ('list_course_role_members', {'rolename': 'beta'}),
            ('rescore_problem', {'problem_to_reset': self.problem_urlname, 'unique_student_identifier': self.user.email}),
        ]

    def _access_endpoint(self, endpoint, args, status_code, msg):
        """
        Asserts that accessing the given `endpoint` gets a response of `status_code`.

        endpoint: string, endpoint for instructor dash API
        args: dict, kwargs for `reverse` call
        status_code: expected HTTP status code response
        msg: message to display if assertion fails.
        """
        url = reverse(endpoint, kwargs={'course_id': self.course.id})
        if endpoint in 'send_email':
            response = self.client.post(url, args)
        else:
            response = self.client.get(url, args)
        print endpoint
        print response
        self.assertEqual(
            response.status_code,
            status_code,
            msg=msg
        )

    def test_student_level(self):
        """
        Ensure that an enrolled student can't access staff or instructor endpoints.
        """
        self.client.login(username=self.user.username, password='test')

        for endpoint, args in self.staff_level_endpoints:
            self._access_endpoint(
                endpoint,
                args,
                403,
                "Student should not be allowed to access endpoint " + endpoint
            )

        for endpoint, args in self.instructor_level_endpoints:
            self._access_endpoint(
                endpoint,
                args,
                403,
                "Student should not be allowed to access endpoint " + endpoint
            )

    def test_staff_level(self):
        """
        Ensure that a staff member can't access instructor endpoints.
        """
        staff_member = StaffFactory(course=self.course.location)
        CourseEnrollment.enroll(staff_member, self.course.id)
        self.client.login(username=staff_member.username, password='test')
        # Try to promote to forums admin - not working
        # update_forum_role(self.course.id, staff_member, FORUM_ROLE_ADMINISTRATOR, 'allow')

        for endpoint, args in self.staff_level_endpoints:
            # TODO: make these work
            if endpoint in ['update_forum_role_membership', 'proxy_legacy_analytics', 'list_forum_members']:
                continue
            self._access_endpoint(
                endpoint,
                args,
                200,
                "Staff member should be allowed to access endpoint " + endpoint
            )

        for endpoint, args in self.instructor_level_endpoints:
            self._access_endpoint(
                endpoint,
                args,
                403,
                "Staff member should not be allowed to access endpoint " + endpoint
            )

    def test_instructor_level(self):
        """
        Ensure that an instructor member can access all endpoints.
        """
        inst = InstructorFactory(course=self.course.location)
        CourseEnrollment.enroll(inst, self.course.id)
        self.client.login(username=inst.username, password='test')

        for endpoint, args in self.staff_level_endpoints:
            # TODO: make these work
            if endpoint in ['update_forum_role_membership', 'proxy_legacy_analytics']:
                continue
            self._access_endpoint(
                endpoint,
                args,
                200,
                "Instructor should be allowed to access endpoint " + endpoint
            )

        for endpoint, args in self.instructor_level_endpoints:
            # TODO: make this work
            if endpoint in ['rescore_problem']:
                continue
            self._access_endpoint(
                endpoint,
                args,
                200,
                "Instructor should be allowed to access endpoint " + endpoint
            )


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPIEnrollment(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test enrollment modification endpoint.

    This test does NOT exhaustively test state changes, that is the
    job of test_enrollment. This tests the response and action switch.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

        self.enrolled_student = UserFactory(username='EnrolledStudent', first_name='Enrolled', last_name='Student')
        CourseEnrollment.enroll(
            self.enrolled_student,
            self.course.id
        )
        self.notenrolled_student = UserFactory(username='NotEnrolledStudent', first_name='NotEnrolled', last_name='Student')

        # Create invited, but not registered, user
        cea = CourseEnrollmentAllowed(email='robot-allowed@robot.org', course_id=self.course.id)
        cea.save()
        self.allowed_email = 'robot-allowed@robot.org'

        self.notregistered_email = 'robot-not-an-email-yet@robot.org'
        self.assertEqual(User.objects.filter(email=self.notregistered_email).count(), 0)

        # uncomment to enable enable printing of large diffs
        # from failed assertions in the event of a test failure.
        # (comment because pylint C0103)
        # self.maxDiff = None

    def test_missing_params(self):
        """ Test missing all query parameters. """
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_bad_action(self):
        """ Test with an invalid action. """
        action = 'robot-not-an-action'
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.enrolled_student.email, 'action': action})
        self.assertEqual(response.status_code, 400)

    def test_enroll_without_email(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notenrolled_student.email, 'action': 'enroll', 'email_students': False})
        print "type(self.notenrolled_student.email): {}".format(type(self.notenrolled_student.email))
        self.assertEqual(response.status_code, 200)

        # test that the user is now enrolled
        user = User.objects.get(email=self.notenrolled_student.email)
        self.assertTrue(CourseEnrollment.is_enrolled(user, self.course.id))

        # test the response data
        expected = {
            "action": "enroll",
            "auto_enroll": False,
            "results": [
                {
                    "email": self.notenrolled_student.email,
                    "before": {
                        "enrollment": False,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    },
                    "after": {
                        "enrollment": True,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    }
                }
            ]
        }

        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 0)

    def test_enroll_with_email(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notenrolled_student.email, 'action': 'enroll', 'email_students': True})
        print "type(self.notenrolled_student.email): {}".format(type(self.notenrolled_student.email))
        self.assertEqual(response.status_code, 200)

        # test that the user is now enrolled
        user = User.objects.get(email=self.notenrolled_student.email)
        self.assertTrue(CourseEnrollment.is_enrolled(user, self.course.id))

        # test the response data
        expected = {
            "action": "enroll",
            "auto_enroll": False,
            "results": [
                {
                    "email": self.notenrolled_student.email,
                    "before": {
                        "enrollment": False,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    },
                    "after": {
                        "enrollment": True,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    }
                }
            ]
        }

        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been enrolled in Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear NotEnrolled Student\n\nYou have been enrolled in Robot Super Course "
            "at edx.org by a member of the course staff. "
            "The course should now appear on your edx.org dashboard.\n\n"
            "To start accessing course materials, please visit "
            "https://edx.org/courses/MITx/999/Robot_Super_Course\n\n----\n"
            "This email was automatically sent from edx.org to NotEnrolled Student"
        )

    def test_enroll_with_email_not_registered(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notregistered_email, 'action': 'enroll', 'email_students': True})
        print "type(self.notregistered_email): {}".format(type(self.notregistered_email))
        self.assertEqual(response.status_code, 200)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been invited to register for Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear student,\n\nYou have been invited to join Robot Super Course at edx.org by a member of the course staff.\n\n"
            "To finish your registration, please visit https://edx.org/register and fill out the registration form "
            "making sure to use robot-not-an-email-yet@robot.org in the E-mail field.\n"
            "Once you have registered and activated your account, "
            "visit https://edx.org/courses/MITx/999/Robot_Super_Course/about to join the course.\n\n----\n"
            "This email was automatically sent from edx.org to robot-not-an-email-yet@robot.org"
        )

    def test_enroll_with_email_not_registered_autoenroll(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notregistered_email, 'action': 'enroll', 'email_students': True, 'auto_enroll': True})
        print "type(self.notregistered_email): {}".format(type(self.notregistered_email))
        self.assertEqual(response.status_code, 200)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been invited to register for Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear student,\n\nYou have been invited to join Robot Super Course at edx.org by a member of the course staff.\n\n"
            "To finish your registration, please visit https://edx.org/register and fill out the registration form "
            "making sure to use robot-not-an-email-yet@robot.org in the E-mail field.\n"
            "Once you have registered and activated your account, you will see Robot Super Course listed on your dashboard.\n\n----\n"
            "This email was automatically sent from edx.org to robot-not-an-email-yet@robot.org"
        )

    def test_unenroll_without_email(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.enrolled_student.email, 'action': 'unenroll', 'email_students': False})
        print "type(self.enrolled_student.email): {}".format(type(self.enrolled_student.email))
        self.assertEqual(response.status_code, 200)

        # test that the user is now unenrolled
        user = User.objects.get(email=self.enrolled_student.email)
        self.assertFalse(CourseEnrollment.is_enrolled(user, self.course.id))

        # test the response data
        expected = {
            "action": "unenroll",
            "auto_enroll": False,
            "results": [
                {
                    "email": self.enrolled_student.email,
                    "before": {
                        "enrollment": True,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    },
                    "after": {
                        "enrollment": False,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    }
                }
            ]
        }

        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 0)

    def test_unenroll_with_email(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.enrolled_student.email, 'action': 'unenroll', 'email_students': True})
        print "type(self.enrolled_student.email): {}".format(type(self.enrolled_student.email))
        self.assertEqual(response.status_code, 200)

        # test that the user is now unenrolled
        user = User.objects.get(email=self.enrolled_student.email)
        self.assertFalse(CourseEnrollment.is_enrolled(user, self.course.id))

        # test the response data
        expected = {
            "action": "unenroll",
            "auto_enroll": False,
            "results": [
                {
                    "email": self.enrolled_student.email,
                    "before": {
                        "enrollment": True,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    },
                    "after": {
                        "enrollment": False,
                        "auto_enroll": False,
                        "user": True,
                        "allowed": False,
                    }
                }
            ]
        }

        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been un-enrolled from Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear Enrolled Student\n\nYou have been un-enrolled in Robot Super Course "
            "at edx.org by a member of the course staff. "
            "The course will no longer appear on your edx.org dashboard.\n\n"
            "Your other courses have not been affected.\n\n----\n"
            "This email was automatically sent from edx.org to Enrolled Student"
        )

    def test_unenroll_with_email_allowed_student(self):
        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.allowed_email, 'action': 'unenroll', 'email_students': True})
        print "type(self.allowed_email): {}".format(type(self.allowed_email))
        self.assertEqual(response.status_code, 200)

        # test the response data
        expected = {
            "action": "unenroll",
            "auto_enroll": False,
            "results": [
                {
                    "email": self.allowed_email,
                    "before": {
                        "enrollment": False,
                        "auto_enroll": False,
                        "user": False,
                        "allowed": True,
                    },
                    "after": {
                        "enrollment": False,
                        "auto_enroll": False,
                        "user": False,
                        "allowed": False,
                    }
                }
            ]
        }

        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been un-enrolled from Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear Student,\n\nYou have been un-enrolled from course Robot Super Course by a member of the course staff. "
            "Please disregard the invitation previously sent.\n\n----\n"
            "This email was automatically sent from edx.org to robot-allowed@robot.org"
        )

    @patch('instructor.enrollment.uses_shib')
    def test_enroll_with_email_not_registered_with_shib(self, mock_uses_shib):

        mock_uses_shib.return_value = True

        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notregistered_email, 'action': 'enroll', 'email_students': True})
        print "type(self.notregistered_email): {}".format(type(self.notregistered_email))
        self.assertEqual(response.status_code, 200)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been invited to register for Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear student,\n\nYou have been invited to join Robot Super Course at edx.org by a member of the course staff.\n\n"
            "To access the course visit https://edx.org/courses/MITx/999/Robot_Super_Course/about and register for the course.\n\n----\n"
            "This email was automatically sent from edx.org to robot-not-an-email-yet@robot.org"
        )

    @patch('instructor.enrollment.uses_shib')
    def test_enroll_with_email_not_registered_with_shib_autoenroll(self, mock_uses_shib):

        mock_uses_shib.return_value = True

        url = reverse('students_update_enrollment', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notregistered_email, 'action': 'enroll', 'email_students': True, 'auto_enroll': True})
        print "type(self.notregistered_email): {}".format(type(self.notregistered_email))
        self.assertEqual(response.status_code, 200)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been invited to register for Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear student,\n\nYou have been invited to join Robot Super Course at edx.org by a member of the course staff.\n\n"
            "To access the course visit https://edx.org/courses/MITx/999/Robot_Super_Course and login.\n\n----\n"
            "This email was automatically sent from edx.org to robot-not-an-email-yet@robot.org"
        )


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPIBulkBetaEnrollment(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test bulk beta modify access endpoint.

    This test does NOT exhaustively test state changes, that is the
    job of test_enrollment. This tests the response and action switch.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

        self.beta_tester = BetaTesterFactory(course=self.course.location)
        CourseEnrollment.enroll(
            self.beta_tester,
            self.course.id
        )

        self.notenrolled_student = UserFactory(username='NotEnrolledStudent', first_name='NotEnrolled', last_name='Student')

        self.notregistered_email = 'robot-not-an-email-yet@robot.org'
        self.assertEqual(User.objects.filter(email=self.notregistered_email).count(), 0)

        # uncomment to enable enable printing of large diffs
        # from failed assertions in the event of a test failure.
        # (comment because pylint C0103)
        # self.maxDiff = None

    def test_missing_params(self):
        """ Test missing all query parameters. """
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_bad_action(self):
        """ Test with an invalid action. """
        action = 'robot-not-an-action'
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.beta_tester.email, 'action': action})
        self.assertEqual(response.status_code, 400)

    def test_add_notenrolled(self):
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notenrolled_student.email, 'action': 'add', 'email_students': False})
        self.assertEqual(response.status_code, 200)

        self.assertTrue(CourseBetaTesterRole(self.course.location).has_user(self.notenrolled_student))
        # test the response data
        expected = {
            "action": "add",
            "results": [
                {
                    "email": self.notenrolled_student.email,
                    "error": False,
                    "userDoesNotExist": False
                }
            ]
        }

        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 0)

    def test_add_notenrolled_with_email(self):
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notenrolled_student.email, 'action': 'add', 'email_students': True})
        self.assertEqual(response.status_code, 200)

        self.assertTrue(CourseBetaTesterRole(self.course.location).has_user(self.notenrolled_student))
        # test the response data
        expected = {
            "action": "add",
            "results": [
                {
                    "email": self.notenrolled_student.email,
                    "error": False,
                    "userDoesNotExist": False
                }
            ]
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been invited to a beta test for Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear NotEnrolled Student\n\nYou have been invited to be a beta tester "
            "for Robot Super Course at edx.org by a member of the course staff.\n\n"
            "Visit https://edx.org/courses/MITx/999/Robot_Super_Course/about to join "
            "the course and begin the beta test.\n\n----\n"
            "This email was automatically sent from edx.org to {}".format(self.notenrolled_student.email)
        )

    def test_enroll_with_email_not_registered(self):
        # User doesn't exist
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.notregistered_email, 'action': 'add', 'email_students': True})
        self.assertEqual(response.status_code, 200)
        # test the response data
        expected = {
            "action": "add",
            "results": [
                {
                    "email": self.notregistered_email,
                    "error": True,
                    "userDoesNotExist": True
                }
            ]
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 0)

    def test_remove_without_email(self):
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.beta_tester.email, 'action': 'remove', 'email_students': False})
        self.assertEqual(response.status_code, 200)

        self.assertFalse(CourseBetaTesterRole(self.course.location).has_user(self.beta_tester))

        # test the response data
        expected = {
            "action": "remove",
            "results": [
                {
                    "email": self.beta_tester.email,
                    "error": False,
                    "userDoesNotExist": False
                }
            ]
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

        # Check the outbox
        self.assertEqual(len(mail.outbox), 0)

    def test_remove_with_email(self):
        url = reverse('bulk_beta_modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'emails': self.beta_tester.email, 'action': 'remove', 'email_students': True})
        self.assertEqual(response.status_code, 200)

        self.assertFalse(CourseBetaTesterRole(self.course.location).has_user(self.beta_tester))

        # test the response data
        expected = {
            "action": "remove",
            "results": [
                {
                    "email": self.beta_tester.email,
                    "error": False,
                    "userDoesNotExist": False
                }
            ]
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)
        # Check the outbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'You have been removed from a beta test for Robot Super Course'
        )
        self.assertEqual(
            mail.outbox[0].body,
            "Dear {full_name}\n\nYou have been removed as a beta tester for "
            "Robot Super Course at edx.org by a member of the course staff. "
            "The course will remain on your dashboard, but you will no longer "
            "be part of the beta testing group.\n\n"
            "Your other courses have not been affected.\n\n----\n"
            "This email was automatically sent from edx.org to {email_address}".format(
                full_name="{} {}".format(self.beta_tester.first_name, self.beta_tester.last_name),
                email_address=self.beta_tester.email
            )
        )


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPILevelsAccess(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test endpoints whereby instructors can change permissions
    of other users.

    This test does NOT test whether the actions had an effect on the
    database, that is the job of test_access.
    This tests the response and action switch.
    Actually, modify_access does not have a very meaningful
    response yet, so only the status code is tested.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

        self.other_instructor = UserFactory()
        allow_access(self.course, self.other_instructor, 'instructor')
        self.other_staff = UserFactory()
        allow_access(self.course, self.other_staff, 'staff')
        self.other_user = UserFactory()

    def test_modify_access_noparams(self):
        """ Test missing all query parameters. """
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_modify_access_bad_action(self):
        """ Test with an invalid action parameter. """
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_staff.email,
            'rolename': 'staff',
            'action': 'robot-not-an-action',
        })
        self.assertEqual(response.status_code, 400)

    def test_modify_access_bad_role(self):
        """ Test with an invalid action parameter. """
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_staff.email,
            'rolename': 'robot-not-a-roll',
            'action': 'revoke',
        })
        self.assertEqual(response.status_code, 400)

    def test_modify_access_allow(self):
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_instructor.email,
            'rolename': 'staff',
            'action': 'allow',
        })
        self.assertEqual(response.status_code, 200)

    def test_modify_access_allow_with_uname(self):
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_instructor.username,
            'rolename': 'staff',
            'action': 'allow',
        })
        self.assertEqual(response.status_code, 200)

    def test_modify_access_revoke(self):
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_staff.email,
            'rolename': 'staff',
            'action': 'revoke',
        })
        self.assertEqual(response.status_code, 200)

    def test_modify_access_revoke_with_username(self):
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_staff.username,
            'rolename': 'staff',
            'action': 'revoke',
        })
        self.assertEqual(response.status_code, 200)

    def test_modify_access_revoke_not_allowed(self):
        """ Test revoking access that a user does not have. """
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.other_staff.email,
            'rolename': 'instructor',
            'action': 'revoke',
        })
        self.assertEqual(response.status_code, 200)

    def test_modify_access_revoke_self(self):
        """
        Test that an instructor cannot remove instructor privelages from themself.
        """
        url = reverse('modify_access', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'unique_student_identifier': self.instructor.email,
            'rolename': 'instructor',
            'action': 'revoke',
        })
        self.assertEqual(response.status_code, 400)

    def test_list_course_role_members_noparams(self):
        """ Test missing all query parameters. """
        url = reverse('list_course_role_members', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_list_course_role_members_bad_rolename(self):
        """ Test with an invalid rolename parameter. """
        url = reverse('list_course_role_members', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'rolename': 'robot-not-a-rolename',
        })
        print response
        self.assertEqual(response.status_code, 400)

    def test_list_course_role_members_staff(self):
        url = reverse('list_course_role_members', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'rolename': 'staff',
        })
        print response
        self.assertEqual(response.status_code, 200)

        # check response content
        expected = {
            'course_id': self.course.id,
            'staff': [
                {
                    'username': self.other_staff.username,
                    'email': self.other_staff.email,
                    'first_name': self.other_staff.first_name,
                    'last_name': self.other_staff.last_name,
                }
            ]
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)

    def test_list_course_role_members_beta(self):
        url = reverse('list_course_role_members', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'rolename': 'beta',
        })
        print response
        self.assertEqual(response.status_code, 200)

        # check response content
        expected = {
            'course_id': self.course.id,
            'beta': []
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected)


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPILevelsDataDump(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test endpoints that show data without side effects.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

        self.students = [UserFactory() for _ in xrange(6)]
        for student in self.students:
            CourseEnrollment.enroll(student, self.course.id)

    def test_get_students_features(self):
        """
        Test that some minimum of information is formatted
        correctly in the response to get_students_features.
        """
        url = reverse('get_students_features', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {})
        res_json = json.loads(response.content)
        self.assertIn('students', res_json)
        for student in self.students:
            student_json = [
                x for x in res_json['students']
                if x['username'] == student.username
            ][0]
            self.assertEqual(student_json['username'], student.username)
            self.assertEqual(student_json['email'], student.email)

    def test_get_anon_ids(self):
        """
        Test the CSV output for the anonymized user ids.
        """
        url = reverse('get_anon_ids', kwargs={'course_id': self.course.id})
        with patch('instructor.views.api.unique_id_for_user') as mock_unique:
            mock_unique.return_value = '42'
            response = self.client.get(url, {})
        self.assertEqual(response['Content-Type'], 'text/csv')
        body = response.content.replace('\r', '')
        self.assertTrue(body.startswith('"User ID","Anonymized user ID"\n"2","42"\n'))
        self.assertTrue(body.endswith('"7","42"\n'))

    def test_list_report_downloads(self):
        url = reverse('list_report_downloads', kwargs={'course_id': self.course.id})
        with patch('instructor_task.models.LocalFSReportStore.links_for') as mock_links_for:
            mock_links_for.return_value = [
                ('mock_file_name_1', 'https://1.mock.url'),
                ('mock_file_name_2', 'https://2.mock.url'),
            ]
            response = self.client.get(url, {})

        expected_response = {
            "downloads": [
                {
                    "url": "https://1.mock.url",
                    "link": "<a href=\"https://1.mock.url\">mock_file_name_1</a>",
                    "name": "mock_file_name_1"
                },
                {
                    "url": "https://2.mock.url",
                    "link": "<a href=\"https://2.mock.url\">mock_file_name_2</a>",
                    "name": "mock_file_name_2"
                }
            ]
        }
        res_json = json.loads(response.content)
        self.assertEqual(res_json, expected_response)

    def test_calculate_grades_csv_success(self):
        url = reverse('calculate_grades_csv', kwargs={'course_id': self.course.id})

        with patch('instructor_task.api.submit_calculate_grades_csv') as mock_cal_grades:
            mock_cal_grades.return_value = True
            response = self.client.get(url, {})
        success_status = "Your grade report is being generated! You can view the status of the generation task in the 'Pending Instructor Tasks' section."
        self.assertIn(success_status, response.content)

    def test_calculate_grades_csv_already_running(self):
        url = reverse('calculate_grades_csv', kwargs={'course_id': self.course.id})

        with patch('instructor_task.api.submit_calculate_grades_csv') as mock_cal_grades:
            mock_cal_grades.side_effect = AlreadyRunningError()
            response = self.client.get(url, {})
        already_running_status = "A grade report generation task is already in progress. Check the 'Pending Instructor Tasks' table for the status of the task. When completed, the report will be available for download in the table below."
        self.assertIn(already_running_status, response.content)

    def test_get_students_features_csv(self):
        """
        Test that some minimum of information is formatted
        correctly in the response to get_students_features.
        """
        url = reverse('get_students_features', kwargs={'course_id': self.course.id})
        response = self.client.get(url + '/csv', {})
        self.assertEqual(response['Content-Type'], 'text/csv')

    def test_get_distribution_no_feature(self):
        """
        Test that get_distribution lists available features
        when supplied no feature parameter.
        """
        url = reverse('get_distribution', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        res_json = json.loads(response.content)
        self.assertEqual(type(res_json['available_features']), list)

        url = reverse('get_distribution', kwargs={'course_id': self.course.id})
        response = self.client.get(url + u'?feature=')
        self.assertEqual(response.status_code, 200)
        res_json = json.loads(response.content)
        self.assertEqual(type(res_json['available_features']), list)

    def test_get_distribution_unavailable_feature(self):
        """
        Test that get_distribution fails gracefully with
            an unavailable feature.
        """
        url = reverse('get_distribution', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'feature': 'robot-not-a-real-feature'})
        self.assertEqual(response.status_code, 400)

    def test_get_distribution_gender(self):
        """
        Test that get_distribution fails gracefully with
            an unavailable feature.
        """
        url = reverse('get_distribution', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'feature': 'gender'})
        self.assertEqual(response.status_code, 200)
        res_json = json.loads(response.content)
        print res_json
        self.assertEqual(res_json['feature_results']['data']['m'], 6)
        self.assertEqual(res_json['feature_results']['choices_display_names']['m'], 'Male')
        self.assertEqual(res_json['feature_results']['data']['no_data'], 0)
        self.assertEqual(res_json['feature_results']['choices_display_names']['no_data'], 'No Data')

    def test_get_student_progress_url(self):
        """ Test that progress_url is in the successful response. """
        url = reverse('get_student_progress_url', kwargs={'course_id': self.course.id})
        url += "?unique_student_identifier={}".format(
            quote(self.students[0].email.encode("utf-8"))
        )
        print url
        response = self.client.get(url)
        print response
        self.assertEqual(response.status_code, 200)
        res_json = json.loads(response.content)
        self.assertIn('progress_url', res_json)

    def test_get_student_progress_url_from_uname(self):
        """ Test that progress_url is in the successful response. """
        url = reverse('get_student_progress_url', kwargs={'course_id': self.course.id})
        url += "?unique_student_identifier={}".format(
            quote(self.students[0].username.encode("utf-8"))
        )
        print url
        response = self.client.get(url)
        print response
        self.assertEqual(response.status_code, 200)
        res_json = json.loads(response.content)
        self.assertIn('progress_url', res_json)

    def test_get_student_progress_url_noparams(self):
        """ Test that the endpoint 404's without the required query params. """
        url = reverse('get_student_progress_url', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

    def test_get_student_progress_url_nostudent(self):
        """ Test that the endpoint 400's when requesting an unknown email. """
        url = reverse('get_student_progress_url', kwargs={'course_id': self.course.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPIRegradeTask(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test endpoints whereby instructors can change student grades.
    This includes resetting attempts and starting rescore tasks.

    This test does NOT test whether the actions had an effect on the
    database, that is the job of task tests and test_enrollment.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

        self.student = UserFactory()
        CourseEnrollment.enroll(self.student, self.course.id)

        self.problem_urlname = 'robot-some-problem-urlname'
        self.module_to_reset = StudentModule.objects.create(
            student=self.student,
            course_id=self.course.id,
            module_state_key=_msk_from_problem_urlname(
                self.course.id,
                self.problem_urlname
            ),
            state=json.dumps({'attempts': 10}),
        )

    def test_reset_student_attempts_deletall(self):
        """ Make sure no one can delete all students state on a problem. """
        url = reverse('reset_student_attempts', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'all_students': True,
            'delete_module': True,
        })
        print response.content
        self.assertEqual(response.status_code, 400)

    def test_reset_student_attempts_single(self):
        """ Test reset single student attempts. """
        url = reverse('reset_student_attempts', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'unique_student_identifier': self.student.email,
        })
        print response.content
        self.assertEqual(response.status_code, 200)
        # make sure problem attempts have been reset.
        changed_module = StudentModule.objects.get(pk=self.module_to_reset.pk)
        self.assertEqual(
            json.loads(changed_module.state)['attempts'],
            0
        )

    # mock out the function which should be called to execute the action.
    @patch.object(instructor_task.api, 'submit_reset_problem_attempts_for_all_students')
    def test_reset_student_attempts_all(self, act):
        """ Test reset all student attempts. """
        url = reverse('reset_student_attempts', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'all_students': True,
        })
        print response.content
        self.assertEqual(response.status_code, 200)
        self.assertTrue(act.called)

    def test_reset_student_attempts_missingmodule(self):
        """ Test reset for non-existant problem. """
        url = reverse('reset_student_attempts', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': 'robot-not-a-real-module',
            'unique_student_identifier': self.student.email,
        })
        print response.content
        self.assertEqual(response.status_code, 400)

    def test_reset_student_attempts_delete(self):
        """ Test delete single student state. """
        url = reverse('reset_student_attempts', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'unique_student_identifier': self.student.email,
            'delete_module': True,
        })
        print response.content
        self.assertEqual(response.status_code, 200)
        # make sure the module has been deleted
        self.assertEqual(
            StudentModule.objects.filter(
                student=self.module_to_reset.student,
                course_id=self.module_to_reset.course_id,
                # module_state_key=self.module_to_reset.module_state_key,
            ).count(),
            0
        )

    def test_reset_student_attempts_nonsense(self):
        """ Test failure with both unique_student_identifier and all_students. """
        url = reverse('reset_student_attempts', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'unique_student_identifier': self.student.email,
            'all_students': True,
        })
        print response.content
        self.assertEqual(response.status_code, 400)

    @patch.object(instructor_task.api, 'submit_rescore_problem_for_student')
    def test_rescore_problem_single(self, act):
        """ Test rescoring of a single student. """
        url = reverse('rescore_problem', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'unique_student_identifier': self.student.email,
        })
        print response.content
        self.assertEqual(response.status_code, 200)
        self.assertTrue(act.called)

    @patch.object(instructor_task.api, 'submit_rescore_problem_for_student')
    def test_rescore_problem_single_from_uname(self, act):
        """ Test rescoring of a single student. """
        url = reverse('rescore_problem', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'unique_student_identifier': self.student.username,
        })
        print response.content
        self.assertEqual(response.status_code, 200)
        self.assertTrue(act.called)

    @patch.object(instructor_task.api, 'submit_rescore_problem_for_all_students')
    def test_rescore_problem_all(self, act):
        """ Test rescoring for all students. """
        url = reverse('rescore_problem', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'problem_to_reset': self.problem_urlname,
            'all_students': True,
        })
        print response.content
        self.assertEqual(response.status_code, 200)
        self.assertTrue(act.called)


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorSendEmail(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Checks that only instructors have access to email endpoints, and that
    these endpoints are only accessible with courses that actually exist,
    only with valid email messages.
    """
    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')
        test_subject = u'\u1234 test subject'
        test_message = u'\u6824 test message'
        self.full_test_message = {
            'send_to': 'staff',
            'subject': test_subject,
            'message': test_message,
        }

    def test_send_email_as_logged_in_instructor(self):
        url = reverse('send_email', kwargs={'course_id': self.course.id})
        response = self.client.post(url, self.full_test_message)
        self.assertEqual(response.status_code, 200)

    def test_send_email_but_not_logged_in(self):
        self.client.logout()
        url = reverse('send_email', kwargs={'course_id': self.course.id})
        response = self.client.post(url, self.full_test_message)
        self.assertEqual(response.status_code, 403)

    def test_send_email_but_not_staff(self):
        self.client.logout()
        student = UserFactory()
        self.client.login(username=student.username, password='test')
        url = reverse('send_email', kwargs={'course_id': self.course.id})
        response = self.client.post(url, self.full_test_message)
        self.assertEqual(response.status_code, 403)

    def test_send_email_but_course_not_exist(self):
        url = reverse('send_email', kwargs={'course_id': 'GarbageCourse/DNE/NoTerm'})
        response = self.client.post(url, self.full_test_message)
        self.assertNotEqual(response.status_code, 200)

    def test_send_email_no_sendto(self):
        url = reverse('send_email', kwargs={'course_id': self.course.id})
        response = self.client.post(url, {
            'subject': 'test subject',
            'message': 'test message',
        })
        self.assertEqual(response.status_code, 400)

    def test_send_email_no_subject(self):
        url = reverse('send_email', kwargs={'course_id': self.course.id})
        response = self.client.post(url, {
            'send_to': 'staff',
            'message': 'test message',
        })
        self.assertEqual(response.status_code, 400)

    def test_send_email_no_message(self):
        url = reverse('send_email', kwargs={'course_id': self.course.id})
        response = self.client.post(url, {
            'send_to': 'staff',
            'subject': 'test subject',
        })
        self.assertEqual(response.status_code, 400)


class MockCompletionInfo(object):
    """Mock for get_task_completion_info"""
    times_called = 0

    def mock_get_task_completion_info(self, *args):  # pylint: disable=unused-argument
        """Mock for get_task_completion_info"""
        self.times_called += 1
        if self.times_called % 2 == 0:
            return True, 'Task Completed'
        return False, 'Task Errored In Some Way'


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestInstructorAPITaskLists(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test instructor task list endpoint.
    """

    class FakeTask(object):
        """ Fake task object """
        FEATURES = [
            'task_type',
            'task_input',
            'task_id',
            'requester',
            'task_state',
            'created',
            'status',
            'task_message',
            'duration_sec'
        ]

        def __init__(self, completion):
            for feature in self.FEATURES:
                setattr(self, feature, 'expected')
            # created needs to be a datetime
            self.created = datetime.datetime(2013, 10, 25, 11, 42, 35)
            # set 'status' and 'task_message' attrs
            success, task_message = completion()
            if success:
                self.status = "Complete"
            else:
                self.status = "Incomplete"
            self.task_message = task_message
            # Set 'task_output' attr, which will be parsed to the 'duration_sec' attr.
            self.task_output = '{"duration_ms": 1035000}'
            self.duration_sec = 1035000 / 1000.0

        def make_invalid_output(self):
            """Munge task_output to be invalid json"""
            self.task_output = 'HI MY NAME IS INVALID JSON'
            # This should be given the value of 'unknown' if the task output
            # can't be properly parsed
            self.duration_sec = 'unknown'

        def to_dict(self):
            """ Convert fake task to dictionary representation. """
            attr_dict = {key: getattr(self, key) for key in self.FEATURES}
            attr_dict['created'] = attr_dict['created'].isoformat()
            return attr_dict

    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

        self.student = UserFactory()
        CourseEnrollment.enroll(self.student, self.course.id)

        self.problem_urlname = 'robot-some-problem-urlname'
        self.module = StudentModule.objects.create(
            student=self.student,
            course_id=self.course.id,
            module_state_key=_msk_from_problem_urlname(
                self.course.id,
                self.problem_urlname
            ),
            state=json.dumps({'attempts': 10}),
        )
        mock_factory = MockCompletionInfo()
        self.tasks = [self.FakeTask(mock_factory.mock_get_task_completion_info) for _ in xrange(7)]
        self.tasks[-1].make_invalid_output()

    def tearDown(self):
        """
        Undo all patches.
        """
        patch.stopall()

    @patch.object(instructor_task.api, 'get_running_instructor_tasks')
    def test_list_instructor_tasks_running(self, act):
        """ Test list of all running tasks. """
        act.return_value = self.tasks
        url = reverse('list_instructor_tasks', kwargs={'course_id': self.course.id})
        mock_factory = MockCompletionInfo()
        with patch('instructor.views.api.get_task_completion_info') as mock_completion_info:
            mock_completion_info.side_effect = mock_factory.mock_get_task_completion_info
            response = self.client.get(url, {})
        self.assertEqual(response.status_code, 200)

        # check response
        self.assertTrue(act.called)
        expected_tasks = [ftask.to_dict() for ftask in self.tasks]
        actual_tasks = json.loads(response.content)['tasks']
        for exp_task, act_task in zip(expected_tasks, actual_tasks):
            self.assertDictEqual(exp_task, act_task)
        self.assertEqual(actual_tasks, expected_tasks)

    @patch.object(instructor_task.api, 'get_instructor_task_history')
    def test_list_background_email_tasks(self, act):
        """Test list of background email tasks."""
        act.return_value = self.tasks
        url = reverse('list_background_email_tasks', kwargs={'course_id': self.course.id})
        mock_factory = MockCompletionInfo()
        with patch('instructor.views.api.get_task_completion_info') as mock_completion_info:
            mock_completion_info.side_effect = mock_factory.mock_get_task_completion_info
            response = self.client.get(url, {})
        self.assertEqual(response.status_code, 200)

        # check response
        self.assertTrue(act.called)
        expected_tasks = [ftask.to_dict() for ftask in self.tasks]
        actual_tasks = json.loads(response.content)['tasks']
        for exp_task, act_task in zip(expected_tasks, actual_tasks):
            self.assertDictEqual(exp_task, act_task)
        self.assertEqual(actual_tasks, expected_tasks)

    @patch.object(instructor_task.api, 'get_instructor_task_history')
    def test_list_instructor_tasks_problem(self, act):
        """ Test list task history for problem. """
        act.return_value = self.tasks
        url = reverse('list_instructor_tasks', kwargs={'course_id': self.course.id})
        mock_factory = MockCompletionInfo()
        with patch('instructor.views.api.get_task_completion_info') as mock_completion_info:
            mock_completion_info.side_effect = mock_factory.mock_get_task_completion_info
            response = self.client.get(url, {
                'problem_urlname': self.problem_urlname,
            })
        self.assertEqual(response.status_code, 200)

        # check response
        self.assertTrue(act.called)
        expected_tasks = [ftask.to_dict() for ftask in self.tasks]
        actual_tasks = json.loads(response.content)['tasks']
        for exp_task, act_task in zip(expected_tasks, actual_tasks):
            self.assertDictEqual(exp_task, act_task)
        self.assertEqual(actual_tasks, expected_tasks)

    @patch.object(instructor_task.api, 'get_instructor_task_history')
    def test_list_instructor_tasks_problem_student(self, act):
        """ Test list task history for problem AND student. """
        act.return_value = self.tasks
        url = reverse('list_instructor_tasks', kwargs={'course_id': self.course.id})
        mock_factory = MockCompletionInfo()
        with patch('instructor.views.api.get_task_completion_info') as mock_completion_info:
            mock_completion_info.side_effect = mock_factory.mock_get_task_completion_info
            response = self.client.get(url, {
                'problem_urlname': self.problem_urlname,
                'unique_student_identifier': self.student.email,
            })
        self.assertEqual(response.status_code, 200)

        # check response
        self.assertTrue(act.called)
        expected_tasks = [ftask.to_dict() for ftask in self.tasks]
        actual_tasks = json.loads(response.content)['tasks']
        for exp_task, act_task in zip(expected_tasks, actual_tasks):
            self.assertDictEqual(exp_task, act_task)

        self.assertEqual(actual_tasks, expected_tasks)


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
@override_settings(ANALYTICS_SERVER_URL="http://robotanalyticsserver.netbot:900/")
@override_settings(ANALYTICS_API_KEY="robot_api_key")
class TestInstructorAPIAnalyticsProxy(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test instructor analytics proxy endpoint.
    """

    class FakeProxyResponse(object):
        """ Fake successful requests response object. """
        def __init__(self):
            self.status_code = requests.status_codes.codes.OK
            self.content = '{"test_content": "robot test content"}'

    class FakeBadProxyResponse(object):
        """ Fake strange-failed requests response object. """
        def __init__(self):
            self.status_code = 'notok.'
            self.content = '{"test_content": "robot test content"}'

    def setUp(self):
        self.course = CourseFactory.create()
        self.instructor = InstructorFactory(course=self.course.location)
        self.client.login(username=self.instructor.username, password='test')

    @patch.object(instructor.views.api.requests, 'get')
    def test_analytics_proxy_url(self, act):
        """ Test legacy analytics proxy url generation. """
        act.return_value = self.FakeProxyResponse()

        url = reverse('proxy_legacy_analytics', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'aname': 'ProblemGradeDistribution'
        })
        print response.content
        self.assertEqual(response.status_code, 200)

        # check request url
        expected_url = "{url}get?aname={aname}&course_id={course_id}&apikey={api_key}".format(
            url="http://robotanalyticsserver.netbot:900/",
            aname="ProblemGradeDistribution",
            course_id=self.course.id,
            api_key="robot_api_key",
        )
        act.assert_called_once_with(expected_url)

    @patch.object(instructor.views.api.requests, 'get')
    def test_analytics_proxy(self, act):
        """
        Test legacy analytics content proxyin, actg.
        """
        act.return_value = self.FakeProxyResponse()

        url = reverse('proxy_legacy_analytics', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'aname': 'ProblemGradeDistribution'
        })
        print response.content
        self.assertEqual(response.status_code, 200)

        # check response
        self.assertTrue(act.called)
        expected_res = {'test_content': "robot test content"}
        self.assertEqual(json.loads(response.content), expected_res)

    @patch.object(instructor.views.api.requests, 'get')
    def test_analytics_proxy_reqfailed(self, act):
        """ Test proxy when server reponds with failure. """
        act.return_value = self.FakeBadProxyResponse()

        url = reverse('proxy_legacy_analytics', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'aname': 'ProblemGradeDistribution'
        })
        print response.content
        self.assertEqual(response.status_code, 500)

    @patch.object(instructor.views.api.requests, 'get')
    def test_analytics_proxy_missing_param(self, act):
        """ Test proxy when missing the aname query parameter. """
        act.return_value = self.FakeProxyResponse()

        url = reverse('proxy_legacy_analytics', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {})
        print response.content
        self.assertEqual(response.status_code, 400)
        self.assertFalse(act.called)


class TestInstructorAPIHelpers(TestCase):
    """ Test helpers for instructor.api """
    def test_split_input_list(self):
        strings = []
        lists = []
        strings.append("Lorem@ipsum.dolor, sit@amet.consectetur\nadipiscing@elit.Aenean\r convallis@at.lacus\r, ut@lacinia.Sed")
        lists.append(['Lorem@ipsum.dolor', 'sit@amet.consectetur', 'adipiscing@elit.Aenean', 'convallis@at.lacus', 'ut@lacinia.Sed'])

        for (stng, lst) in zip(strings, lists):
            self.assertEqual(_split_input_list(stng), lst)

    def test_split_input_list_unicode(self):
        self.assertEqual(_split_input_list('robot@robot.edu, robot2@robot.edu'), ['robot@robot.edu', 'robot2@robot.edu'])
        self.assertEqual(_split_input_list(u'robot@robot.edu, robot2@robot.edu'), ['robot@robot.edu', 'robot2@robot.edu'])
        self.assertEqual(_split_input_list(u'robot@robot.edu, robot2@robot.edu'), [u'robot@robot.edu', 'robot2@robot.edu'])
        scary_unistuff = unichr(40960) + u'abcd' + unichr(1972)
        self.assertEqual(_split_input_list(scary_unistuff), [scary_unistuff])

    def test_msk_from_problem_urlname(self):
        args = ('MITx/6.002x/2013_Spring', 'L2Node1')
        output = 'i4x://MITx/6.002x/problem/L2Node1'
        self.assertEqual(_msk_from_problem_urlname(*args), output)

    @raises(ValueError)
    def test_msk_from_problem_urlname_error(self):
        args = ('notagoodcourse', 'L2Node1')
        _msk_from_problem_urlname(*args)


@override_settings(MODULESTORE=TEST_DATA_MIXED_MODULESTORE)
class TestDueDateExtensions(ModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Test data dumps for reporting.
    """

    def setUp(self):
        """
        Fixtures.
        """
        due = datetime.datetime(2010, 5, 12, 2, 42, tzinfo=utc)
        course = CourseFactory.create()
        week1 = ItemFactory.create(due=due)
        week2 = ItemFactory.create(due=due)
        week3 = ItemFactory.create(due=due)
        course.children = [week1.location.url(), week2.location.url(),
                           week3.location.url()]

        homework = ItemFactory.create(
            parent_location=week1.location,
            due=due
        )
        week1.children = [homework.location.url()]

        user1 = UserFactory.create()
        StudentModule(
            state='{}',
            student_id=user1.id,
            course_id=course.id,
            module_state_key=week1.location.url()).save()
        StudentModule(
            state='{}',
            student_id=user1.id,
            course_id=course.id,
            module_state_key=week2.location.url()).save()
        StudentModule(
            state='{}',
            student_id=user1.id,
            course_id=course.id,
            module_state_key=week3.location.url()).save()
        StudentModule(
            state='{}',
            student_id=user1.id,
            course_id=course.id,
            module_state_key=homework.location.url()).save()

        user2 = UserFactory.create()
        StudentModule(
            state='{}',
            student_id=user2.id,
            course_id=course.id,
            module_state_key=week1.location.url()).save()
        StudentModule(
            state='{}',
            student_id=user2.id,
            course_id=course.id,
            module_state_key=homework.location.url()).save()

        user3 = UserFactory.create()
        StudentModule(
            state='{}',
            student_id=user3.id,
            course_id=course.id,
            module_state_key=week1.location.url()).save()
        StudentModule(
            state='{}',
            student_id=user3.id,
            course_id=course.id,
            module_state_key=homework.location.url()).save()

        self.course = course
        self.week1 = week1
        self.homework = homework
        self.week2 = week2
        self.user1 = user1
        self.user2 = user2

        self.instructor = InstructorFactory(course=course.location)
        self.client.login(username=self.instructor.username, password='test')

    def test_change_due_date(self):
        url = reverse('change_due_date', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'student': self.user1.username,
            'url': self.week1.location.url(),
            'due_datetime': '12/30/2013 00:00'
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(datetime.datetime(2013, 12, 30, 0, 0, tzinfo=utc),
                         get_extended_due(self.course, self.week1, self.user1))

    def test_reset_date(self):
        self.test_change_due_date()
        url = reverse('reset_due_date', kwargs={'course_id': self.course.id})
        response = self.client.get(url, {
            'student': self.user1.username,
            'url': self.week1.location.url(),
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(None,
                         get_extended_due(self.course, self.week1, self.user1))

    def test_show_unit_extensions(self):
        self.test_change_due_date()
        url = reverse('show_unit_extensions',
                      kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'url': self.week1.location.url()})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(json.loads(response.content), {
            u'data': [{u'Extended Due Date': u'2013-12-30 00:00',
                       u'Full Name': self.user1.profile.name,
                       u'Username': self.user1.username}],
            u'header': [u'Username', u'Full Name', u'Extended Due Date'],
            u'title': u'Users with due date extensions for %s' %
            self.week1.display_name})

    def test_show_student_extensions(self):
        self.test_change_due_date()
        url = reverse('show_student_extensions',
                      kwargs={'course_id': self.course.id})
        response = self.client.get(url, {'student': self.user1.username})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(json.loads(response.content), {
            u'data': [{u'Extended Due Date': u'2013-12-30 00:00',
                       u'Unit': self.week1.display_name}],
            u'header': [u'Unit', u'Extended Due Date'],
            u'title': u'Due date extensions for %s (%s)' % (
            self.user1.profile.name, self.user1.username)})
