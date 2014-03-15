from optparse import make_option

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import translation

from student.models import CourseEnrollment, Registration
from student.views import _do_create_account
from track.management.tracked_command import TrackedCommand


class Command(TrackedCommand):
    help = """
    This command creates and registers a user in a given course
    as "audit", "verified" or "honor".

    example:
        # Enroll a user test@example.com into the demo course
        # The username and name will default to "test"
        manage.py ... create_user -e test@example.com -p insecure -c edX/Open_DemoX/edx_demo_course -m verified
    """

    option_list = BaseCommand.option_list + (
        make_option('-m', '--mode',
                    metavar='ENROLLMENT_MODE',
                    dest='mode',
                    default='honor',
                    choices=('audit', 'verified', 'honor'),
                    help='Enrollment type for user for a specific course'),
        make_option('-u', '--username',
                    metavar='USERNAME',
                    dest='username',
                    default=None,
                    help='Username, defaults to "user" in the email'),
        make_option('-n', '--name',
                    metavar='NAME',
                    dest='name',
                    default=None,
                    help='Name, defaults to "user" in the email'),
        make_option('-p', '--password',
                    metavar='PASSWORD',
                    dest='password',
                    default=None,
                    help='Password for user'),
        make_option('-e', '--email',
                    metavar='EMAIL',
                    dest='email',
                    default=None,
                    help='Email for user'),
        make_option('-c', '--course',
                    metavar='COURSE_ID',
                    dest='course',
                    default=None,
                    help='course to enroll the user in (optional)'),
        make_option('-s', '--staff',
                    dest='staff',
                    default=False,
                    action='store_true',
                    help='give user the staff bit'),
    )

    def handle(self, *args, **options):
        username = options['username']
        name = options['name']
        if not username:
            username = options['email'].split('@')[0]
        if not name:
            name = options['email'].split('@')[0]

        post_data = {
            'username': username,
            'email': options['email'],
            'password': options['password'],
            'name': name,
            'honor_code': u'true',
            'terms_of_service': u'true',
        }
        # django.utils.translation.get_language() will be used to set the new
        # user's preferred language.  This line ensures that the result will
        # match this installation's default locale.  Otherwise, inside a
        # management command, it will always return "en-us".
        translation.activate(settings.LANGUAGE_CODE)
        create_account = _do_create_account(post_data)
        if isinstance(create_account, tuple):
            user = create_account[0]
            if options['staff']:
                user.is_staff = True
                user.save()
            reg = Registration.objects.get(user=user)
            reg.activate()
            reg.save()
        else:
            print create_account
            user = User.objects.get(email=options['email'])
        if options['course']:
            CourseEnrollment.enroll(user, options['course'], mode=options['mode'])
