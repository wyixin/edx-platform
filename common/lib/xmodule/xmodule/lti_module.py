"""
Learning Tools Interoperability (LTI) module.


Resources
---------

Theoretical background and detailed specifications of LTI can be found on:

    http://www.imsglobal.org/LTI/v1p1p1/ltiIMGv1p1p1.html

This module is based on the version 1.1.1 of the LTI specifications by the
IMS Global authority. For authentication, it uses OAuth1.

When responding back to the LTI tool provider, we must issue a correct
response. Types of responses and their message payload is available at:

    Table A1.2 Interpretation of the 'CodeMajor/severity' matrix.
    http://www.imsglobal.org/gws/gwsv1p0/imsgws_wsdlBindv1p0.html

A resource to test the LTI protocol (PHP realization):

    http://www.imsglobal.org/developers/LTI/test/v1p1/lms.php


What is supported:
------------------

1.) Display of simple LTI in iframe or a new window.
2.) Multiple LTI components on a single page.
3.) The use of multiple LTI providers per course.
4.) Use of advanced LTI component that provides back a grade.
    a.) The LTI provider sends back a grade to a specified URL.
    b.) Currently only action "update" is supported. "Read", and "delete"
        actions initially weren't required.
"""

import logging
import oauthlib.oauth1
from oauthlib.oauth1.rfc5849 import signature
import hashlib
import base64
import urllib
import textwrap
import json
import re
import bleach
from lxml import etree
from webob import Response
import mock
from xml.sax.saxutils import escape

from xmodule.editing_module import MetadataOnlyEditingDescriptor
from xmodule.raw_module import EmptyDataRawDescriptor
from xmodule.x_module import XModule, module_attr, module_runtime_attr
from xmodule.course_module import CourseDescriptor
from pkg_resources import resource_string
from xblock.core import String, Scope, List, XBlock
from xblock.fields import Boolean, Float

log = logging.getLogger(__name__)

LTI_2_0_REST_DISPATCH_PARSER = re.compile(r"^user/(?P<anon_id>\w+)", re.UNICODE)
LTI_2_0_JSON_CONTENT_TYPE = 'application/vnd.ims.lis.v2.result+json'


class LTIError(Exception):
    pass


class LTIFields(object):
    """
    Fields to define and obtain LTI tool from provider are set here,
    except credentials, which should be set in course settings::

    `lti_id` is id to connect tool with credentials in course settings. It should not contain :: (double semicolon)
    `launch_url` is launch URL of tool.
    `custom_parameters` are additional parameters to navigate to proper book and book page.

    For example, for Vitalsource provider, `launch_url` should be
    *https://bc-staging.vitalsource.com/books/book*,
    and to get to proper book and book page, you should set custom parameters as::

        vbid=put_book_id_here
        book_location=page/put_page_number_here

    Default non-empty URL for `launch_url` is needed due to oauthlib demand (URL scheme should be presented)::

    https://github.com/idan/oauthlib/blob/master/oauthlib/oauth1/rfc5849/signature.py#L136
    """
    display_name = String(display_name="Display Name", help="Display name for this module", scope=Scope.settings, default="LTI")
    lti_id = String(help="Id of the tool", default='', scope=Scope.settings)
    launch_url = String(help="URL of the tool", default='http://www.example.com', scope=Scope.settings)
    custom_parameters = List(help="Custom parameters (vbid, book_location, etc..)", scope=Scope.settings)
    open_in_a_new_page = Boolean(help="Should LTI be opened in new page?", default=True, scope=Scope.settings)
    graded = Boolean(help="Grades will be considered in overall score.", default=False, scope=Scope.settings)
    weight = Float(
        help="Weight for student grades.",
        default=1.0,
        scope=Scope.settings,
        values={"min": 0},
    )
    has_score = Boolean(help="Does this LTI module have score?", default=False, scope=Scope.settings)
    module_score = Float(help="The score kept in the xblock KVS -- duplicate of the published score in django DB",
                         default=None,
                         scope=Scope.user_state)
    score_comment = String(help="Comment as returned from grader, LTI2.0 spec", default="", scope=Scope.user_state)
    hide_launch = Boolean(help="Do not show the launch button or iframe", default=False, scope=Scope.settings)

class LTIModule(LTIFields, XModule):
    """
    Module provides LTI integration to course.

    Except usual Xmodule structure it proceeds with OAuth signing.
    How it works::

    1. Get credentials from course settings.

    2.  There is minimal set of parameters need to be signed (presented for Vitalsource)::

            user_id
            oauth_callback
            lis_outcome_service_url
            lis_result_sourcedid
            launch_presentation_return_url
            lti_message_type
            lti_version
            roles
            *+ all custom parameters*

        These parameters should be encoded and signed by *OAuth1* together with
        `launch_url` and *POST* request type.

    3. Signing proceeds with client key/secret pair obtained from course settings.
        That pair should be obtained from LTI provider and set into course settings by course author.
        After that signature and other OAuth data are generated.

        OAuth data which is generated after signing is usual::

            oauth_callback
            oauth_nonce
            oauth_consumer_key
            oauth_signature_method
            oauth_timestamp
            oauth_version


    4. All that data is passed to form and sent to LTI provider server by browser via
        autosubmit via JavaScript.

        Form example::

            <form
                action="${launch_url}"
                name="ltiLaunchForm-${element_id}"
                class="ltiLaunchForm"
                method="post"
                target="ltiLaunchFrame-${element_id}"
                encType="application/x-www-form-urlencoded"
            >
                <input name="launch_presentation_return_url" value="" />
                <input name="lis_outcome_service_url" value="" />
                <input name="lis_result_sourcedid" value="" />
                <input name="lti_message_type" value="basic-lti-launch-request" />
                <input name="lti_version" value="LTI-1p0" />
                <input name="oauth_callback" value="about:blank" />
                <input name="oauth_consumer_key" value="${oauth_consumer_key}" />
                <input name="oauth_nonce" value="${oauth_nonce}" />
                <input name="oauth_signature_method" value="HMAC-SHA1" />
                <input name="oauth_timestamp" value="${oauth_timestamp}" />
                <input name="oauth_version" value="1.0" />
                <input name="user_id" value="${user_id}" />
                <input name="role" value="student" />
                <input name="oauth_signature" value="${oauth_signature}" />

                <input name="custom_1" value="${custom_param_1_value}" />
                <input name="custom_2" value="${custom_param_2_value}" />
                <input name="custom_..." value="${custom_param_..._value}" />

                <input type="submit" value="Press to Launch" />
            </form>

    5. LTI provider has same secret key and it signs data string via *OAuth1* and compares signatures.

        If signatures are correct, LTI provider redirects iframe source to LTI tool web page,
        and LTI tool is rendered to iframe inside course.

        Otherwise error message from LTI provider is generated.
    """

    css = {'scss': [resource_string(__name__, 'css/lti/lti.scss')]}

    def get_input_fields(self):
        # LTI provides a list of default parameters that might be passed as
        # part of the POST data. These parameters should not be prefixed.
        # Likewise, The creator of an LTI link can add custom key/value parameters
        # to a launch which are to be included with the launch of the LTI link.
        # In this case, we will automatically add `custom_` prefix before this parameters.
        # See http://www.imsglobal.org/LTI/v1p1p1/ltiIMGv1p1p1.html#_Toc316828520
        PARAMETERS = [
            "lti_message_type",
            "lti_version",
            "resource_link_id",
            "resource_link_title",
            "resource_link_description",
            "user_id",
            "user_image",
            "roles",
            "lis_person_name_given",
            "lis_person_name_family",
            "lis_person_name_full",
            "lis_person_contact_email_primary",
            "lis_person_sourcedid",
            "role_scope_mentor",
            "context_id",
            "context_type",
            "context_title",
            "context_label",
            "launch_presentation_locale",
            "launch_presentation_document_target",
            "launch_presentation_css_url",
            "launch_presentation_width",
            "launch_presentation_height",
            "launch_presentation_return_url",
            "tool_consumer_info_product_family_code",
            "tool_consumer_info_version",
            "tool_consumer_instance_guid",
            "tool_consumer_instance_name",
            "tool_consumer_instance_description",
            "tool_consumer_instance_url",
            "tool_consumer_instance_contact_email",
        ]

        client_key, client_secret = self.get_client_key_secret()

        # parsing custom parameters to dict
        custom_parameters = {}
        for custom_parameter in self.custom_parameters:
            try:
                param_name, param_value = [p.strip() for p in custom_parameter.split('=', 1)]
            except ValueError:
                raise LTIError('Could not parse custom parameter: {0!r}. \
                    Should be "x=y" string.'.format(custom_parameter))

            # LTI specs: 'custom_' should be prepended before each custom parameter, as pointed in link above.
            if param_name not in PARAMETERS:
                param_name = 'custom_' + param_name

            custom_parameters[unicode(param_name)] = unicode(param_value)

        return self.oauth_params(
            custom_parameters,
            client_key,
            client_secret,
        )

    def get_context(self):
        """
        Returns a context.
        """
        # use bleach defaults. see https://github.com/jsocol/bleach/blob/master/bleach/__init__.py
        # ALLOWED_TAGS = [
        #     'a',
        #     'abbr',
        #     'acronym',
        #     'b',
        #     'blockquote',
        #     'code',
        #     'em',
        #     'i',
        #     'li',
        #     'ol',
        #     'strong',
        #     'ul',
        # ]
        #
        # ALLOWED_ATTRIBUTES = {
        #     'a': ['href', 'title'],
        #     'abbr': ['title'],
        #     'acronym': ['title'],
        # }
        #
        # ALLOWED_STYLES = []
        # This lets all plaintext through.
        sanitized_comment = bleach.clean(self.score_comment)

        return {
            'input_fields': self.get_input_fields(),

            # These parameters do not participate in OAuth signing.
            'launch_url': self.launch_url.strip(),
            'element_id': self.location.html_id(),
            'element_class': self.category,
            'open_in_a_new_page': self.open_in_a_new_page,
            'display_name': self.display_name,
            'form_url': self.runtime.handler_url(self, 'preview_handler').rstrip('/?'),
            'hide_launch': self.hide_launch,
            'has_score': self.has_score,
            'weight': self.weight,
            'module_score': self.module_score,
            'comment': sanitized_comment,
        }

    def get_html(self):
        """
        Renders parameters to template.
        """
        return self.system.render_template('lti.html', self.get_context())

    @XBlock.handler
    def preview_handler(self, _, __):
        """
        This is called to get context with new oauth params to iframe.
        """
        template = self.system.render_template('lti_form.html', self.get_context())
        return Response(template, content_type='text/html')

    def get_user_id(self):
        user_id = self.runtime.anonymous_student_id
        assert user_id is not None
        return unicode(urllib.quote(user_id))

    def get_outcome_service_url(self, service_name="grade_handler"):
        """
        Return URL for storing grades.

        To test LTI on sandbox we must use http scheme.

        While testing locally and on Jenkins, mock_lti_server use http.referer
        to obtain scheme, so it is ok to have http(s) anyway.
        """
        scheme = 'http' if 'sandbox' in self.system.hostname or self.system.debug else 'https'
        uri = '{scheme}://{host}{path}'.format(
            scheme=scheme,
            host=self.system.hostname,
            path=self.runtime.handler_url(self, service_name, thirdparty=True).rstrip('/?')
        )
        return uri

    def get_resource_link_id(self):
        """
        This is an opaque unique identifier that the TC guarantees will be unique
        within the TC for every placement of the link.

        If the tool / activity is placed multiple times in the same context,
        each of those placements will be distinct.

        This value will also change if the item is exported from one system or
        context and imported into another system or context.

        This parameter is required.
        """
        return unicode(urllib.quote(self.id))

    def get_lis_result_sourcedid(self):
        """
        This field contains an identifier that indicates the LIS Result Identifier (if any)
        associated with this launch.  This field identifies a unique row and column within the
        TC gradebook.  This field is unique for every combination of context_id / resource_link_id / user_id.
        This value may change for a particular resource_link_id / user_id  from one launch to the next.
        The TP should only retain the most recent value for this field for a particular resource_link_id / user_id.
        This field is generally optional, but is required for grading.

        context_id is - is an opaque identifier that uniquely identifies the context that contains
        the link being launched.
        lti_id should be context_id by meaning.
        """
        return "{id}:{resource_link}:{user_id}".format(
            id=urllib.quote(self.lti_id),
            resource_link=urllib.quote(self.get_resource_link_id()),
            user_id=urllib.quote(self.get_user_id())
        )

    def get_course(self):
        """
        Return course by course id.
        """
        course_location = CourseDescriptor.id_to_location(self.course_id)
        course = self.descriptor.runtime.modulestore.get_item(course_location)
        return course

    @property
    def role(self):
        """
        Get system user role and convert it to LTI role.
        """
        roles = {
            'student': u'Student',
            'staff': u'Administrator',
            'instructor': u'Instructor',
        }
        return roles.get(self.system.get_user_role(), u'Student')

    def oauth_params(self, custom_parameters, client_key, client_secret):
        """
        Signs request and returns signature and OAuth parameters.

        `custom_paramters` is dict of parsed `custom_parameter` field
        `client_key` and `client_secret` are LTI tool credentials.

        Also *anonymous student id* is passed to template and therefore to LTI provider.
        """

        client = oauthlib.oauth1.Client(
            client_key=unicode(client_key),
            client_secret=unicode(client_secret)
        )

        # Must have parameters for correct signing from LTI:
        body = {
            u'user_id': self.get_user_id(),
            u'oauth_callback': u'about:blank',
            u'launch_presentation_return_url': '',
            u'lti_message_type': u'basic-lti-launch-request',
            u'lti_version': 'LTI-1p0',
            u'roles': self.role,

            # Parameters required for grading:
            u'resource_link_id': self.get_resource_link_id(),
            u'lis_result_sourcedid': self.get_lis_result_sourcedid(),

        }

        if self.has_score:
            body.update({
                u'lis_outcome_service_url': self.get_outcome_service_url()
            })

        # Appending custom parameter for signing.
        body.update(custom_parameters)

        headers = {
            # This is needed for body encoding:
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        try:
            __, headers, __ = client.sign(
                unicode(self.launch_url.strip()),
                http_method=u'POST',
                body=body,
                headers=headers)
        except ValueError:  # Scheme not in url.
            # https://github.com/idan/oauthlib/blob/master/oauthlib/oauth1/rfc5849/signature.py#L136
            # Stubbing headers for now:
            headers = {
                u'Content-Type': u'application/x-www-form-urlencoded',
                u'Authorization': u'OAuth oauth_nonce="80966668944732164491378916897", \
oauth_timestamp="1378916897", oauth_version="1.0", oauth_signature_method="HMAC-SHA1", \
oauth_consumer_key="", oauth_signature="frVp4JuvT1mVXlxktiAUjQ7%2F1cw%3D"'}

        params = headers['Authorization']
        # Parse headers to pass to template as part of context:
        params = dict([param.strip().replace('"', '').split('=') for param in params.split(',')])

        params[u'oauth_nonce'] = params[u'OAuth oauth_nonce']
        del params[u'OAuth oauth_nonce']

        # oauthlib encodes signature with
        # 'Content-Type': 'application/x-www-form-urlencoded'
        # so '='' becomes '%3D'.
        # We send form via browser, so browser will encode it again,
        # So we need to decode signature back:
        params[u'oauth_signature'] = urllib.unquote(params[u'oauth_signature']).decode('utf8')

        # Add LTI parameters to OAuth parameters for sending in form.
        params.update(body)
        return params

    def max_score(self):
        return self.weight if self.has_score else None

    @XBlock.handler
    def grade_handler(self, request, dispatch):
        """
        This is called by courseware.module_render, to handle an AJAX call.

        Used only for grading. Returns XML response.

        Example of request body from LTI provider::

        <?xml version = "1.0" encoding = "UTF-8"?>
            <imsx_POXEnvelopeRequest xmlns = "some_link (may be not required)">
              <imsx_POXHeader>
                <imsx_POXRequestHeaderInfo>
                  <imsx_version>V1.0</imsx_version>
                  <imsx_messageIdentifier>528243ba5241b</imsx_messageIdentifier>
                </imsx_POXRequestHeaderInfo>
              </imsx_POXHeader>
              <imsx_POXBody>
                <replaceResultRequest>
                  <resultRecord>
                    <sourcedGUID>
                      <sourcedId>feb-123-456-2929::28883</sourcedId>
                    </sourcedGUID>
                    <result>
                      <resultScore>
                        <language>en-us</language>
                        <textString>0.4</textString>
                      </resultScore>
                    </result>
                  </resultRecord>
                </replaceResultRequest>
              </imsx_POXBody>
            </imsx_POXEnvelopeRequest>

        Example of correct/incorrect answer XML body:: see response_xml_template.
        """
        response_xml_template = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <imsx_POXEnvelopeResponse xmlns = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                <imsx_POXHeader>
                    <imsx_POXResponseHeaderInfo>
                        <imsx_version>V1.0</imsx_version>
                        <imsx_messageIdentifier>{imsx_messageIdentifier}</imsx_messageIdentifier>
                        <imsx_statusInfo>
                            <imsx_codeMajor>{imsx_codeMajor}</imsx_codeMajor>
                            <imsx_severity>status</imsx_severity>
                            <imsx_description>{imsx_description}</imsx_description>
                            <imsx_messageRefIdentifier>
                            </imsx_messageRefIdentifier>
                        </imsx_statusInfo>
                    </imsx_POXResponseHeaderInfo>
                </imsx_POXHeader>
                <imsx_POXBody>{response}</imsx_POXBody>
            </imsx_POXEnvelopeResponse>
        """)
        # Returns when `action` is unsupported.
        # Supported actions:
        #   - replaceResultRequest.
        unsupported_values = {
            'imsx_codeMajor': 'unsupported',
            'imsx_description': 'Target does not support the requested operation.',
            'imsx_messageIdentifier': 'unknown',
            'response': ''
        }
        # Returns if:
        #   - score is out of range;
        #   - can't parse response from TP;
        #   - can't verify OAuth signing or OAuth signing is incorrect.
        failure_values = {
            'imsx_codeMajor': 'failure',
            'imsx_description': 'The request has failed.',
            'imsx_messageIdentifier': 'unknown',
            'response': ''
        }

        try:
            imsx_messageIdentifier, sourcedId, score, action = self.parse_grade_xml_body(request.body)
        except Exception as e:
            error_message = "Request body XML parsing error: " + escape(e.message)
            log.debug("[LTI]: " + error_message)
            failure_values['imsx_description'] = error_message
            return Response(response_xml_template.format(**failure_values), content_type="application/xml")

        # Verify OAuth signing.
        try:
            self.verify_oauth_body_sign(request)
        except (ValueError, LTIError) as e:
            failure_values['imsx_messageIdentifier'] = escape(imsx_messageIdentifier)
            error_message = "OAuth verification error: " + escape(e.message)
            failure_values['imsx_description'] = error_message
            log.debug("[LTI]: " + error_message)
            return Response(response_xml_template.format(**failure_values), content_type="application/xml")

        real_user = self.system.get_real_user(urllib.unquote(sourcedId.split(':')[-1]))
        if not real_user:  # that means we can't save to database, as we do not have real user id.
            failure_values['imsx_messageIdentifier'] = escape(imsx_messageIdentifier)
            failure_values['imsx_description'] = "User not found."
            return Response(response_xml_template.format(**failure_values), content_type="application/xml")

        if action == 'replaceResultRequest':
            user_instance = self.system.get_user_module_for_noauth(real_user)

            LTIModule.set_user_module_score(real_user, user_instance, score, self.max_score())

            values = {
                'imsx_codeMajor': 'success',
                'imsx_description': 'Score for {sourced_id} is now {score}'.format(sourced_id=sourcedId, score=score),
                'imsx_messageIdentifier': escape(imsx_messageIdentifier),
                'response': '<replaceResultResponse/>'
            }
            log.debug("[LTI]: Grade is saved.")
            return Response(response_xml_template.format(**values), content_type="application/xml")

        unsupported_values['imsx_messageIdentifier'] = escape(imsx_messageIdentifier)
        log.debug("[LTI]: Incorrect action.")
        return Response(response_xml_template.format(**unsupported_values), content_type='application/xml')

    #  LTI 2.0 Result Service Support -- but for now only for PUTting the grade back into an LTI xmodule
    @XBlock.handler
    def lti_2_0_result_rest_handler(self, request, dispatch):
        """
        This will in the future be the handler for the LTI 2.0 Result service REST endpoints.  Right now
        I'm (@jbau) just implementing the PUT interface first.  All other methods get 404'ed.  It really should
        be a 405, but LTI does not specify that as an acceptable return code.  See
        http://www.imsglobal.org/lti/ltiv2p0/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html

        An example JSON object:
        {
         "@context" : "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "@type" : "Result",
         "resultScore" : 0.83,
         "comment" : "This is exceptional work."
        }
        For PUTs, the content type must be "application/vnd.ims.lis.v2.result+json".
        Note the "@id" key is optional on PUT and we don't do anything with it.  Instead, we use the "dispatch"
        parameter to parse out the user from the end of the URL.  An example endpoint url is
        http://localhost:8000/courses/org/num/run/xblock/i4x:;_;_org;_num;_lti;_GUID/handler_noauth/lti_2_0_result_rest_handler/user/<anon_id>
        so dispatch is of the form "user/<anon_id>"
        Failures result in 401, 404, or 500s without any body.  Successes result in 200.  Again see
        http://www.imsglobal.org/lti/ltiv2p0/uml/purl.imsglobal.org/vocab/lis/v2/outcomes/Result/service.html
        (Note: this prevents good debug messages for the client.  So I'd advocate the creating
        another endpoint that doesn't conform to spec, but is nicer)
        """

        ######## DEBUG SECTION #######
        sha1 = hashlib.sha1()
        sha1.update(request.body)
        oauth_body_hash = unicode(base64.b64encode(sha1.digest()))
        log.debug("[LTI] oauth_body_hash = {}".format(oauth_body_hash))
        client_key, client_secret = self.get_client_key_secret()
        from oauthlib.oauth1 import Client
        client = Client(client_key, client_secret)
        params = client.get_oauth_params()
        params.append((u'oauth_body_hash', oauth_body_hash))
        mock_request = mock.Mock(
            uri=unicode(urllib.unquote(request.url)),
            headers=request.headers,
            body=u"",
            decoded_body=u"",
            oauth_params=params,
            http_method=unicode(request.method),
        )
        sig = client.get_oauth_signature(mock_request)
        mock_request.oauth_params.append((u'oauth_signature', sig))

        uri, headers, body = client._render(mock_request)
        print("\n\n#### COPY AND PASTE AUTHORIZATION HEADER ####\n{}\n#############################################\n\n"
              .format(headers['Authorization']))
        ####### DEBUG SECTION END ########
        try:
            anon_id = self.parse_lti_2_0_handler_dispatch(dispatch)
        except LTIError:
            return Response(status=404)  # 404 because a part of the URL (denoting the anon user id) is invalid
        try:
            self.verify_lti_2_0_result_rest_headers(request, verify_content_type=True)
        except LTIError:
            return Response(status=401)  # Unauthorized in this case.  401 is right

        real_user = self.system.get_real_user(anon_id)
        if not real_user:  # that means we can't save to database, as we do not have real user id.
            msg = "[LTI]: Real user not found against anon_id: {}".format(anon_id)
            log.debug(msg)
            return Response(status=404)  # have to do 404 due to spec, but 400 is better, with error msg in body
        if request.method == "PUT":
            return self._lti_2_0_result_put_handler(request, real_user)
        elif request.method == "GET":
            return self._lti_2_0_result_get_handler(request, real_user)
        elif request.method == "DELETE":
            return self._lti_2_0_result_del_handler(request, real_user)
        else:
            return Response(status=404)  # have to do 404 due to spec, but 405 is better, with error msg in body

    def parse_lti_2_0_handler_dispatch(self, dispatch):
        """
        parses the dispatch argument (the trailing parts of the URL) of the LTI2.0 REST handler.
        must be of the form "user/<anon_id>".  Returns anon_id if match found, otherwise raises LTIError
        """
        if dispatch:
            match_obj = LTI_2_0_REST_DISPATCH_PARSER.match(dispatch)
            if match_obj:
                return match_obj.group('anon_id')
        # fall-through handles all error cases
        msg = "No valid user id found in endpoint URL"
        log.debug("[LTI]: {}".format(msg))
        raise LTIError(msg)

    def _lti_2_0_result_get_handler(self, request, real_user):  # pylint: disable=unused-argument
        """
        GET handler for lti_2_0_result.  Assumes all authorization has been checked.
        """
        base_json_obj = {"@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
                         "@type": "Result"}
        user_instance = self.system.get_user_module_for_noauth(real_user)
        if user_instance.module_score is None:  # In this case, no score has been ever set
            return Response(json.dumps(base_json_obj), content_type=LTI_2_0_JSON_CONTENT_TYPE)

        # Fall through to returning grade and comment
        base_json_obj['resultScore'] = round(user_instance.module_score, 2)
        base_json_obj['comment'] = user_instance.score_comment
        return Response(json.dumps(base_json_obj), content_type=LTI_2_0_JSON_CONTENT_TYPE)

    def _lti_2_0_result_del_handler(self, request, real_user):  # pylint: disable=unused-argument
        """
        DELETE handler for lti_2_0_result.  Assumes all authorization has been checked.
        """
        user_instance = self.system.get_user_module_for_noauth(real_user)
        LTIModule.clear_user_module_score(real_user, user_instance)
        return Response(status=200)

    def _lti_2_0_result_put_handler(self, request, real_user):
        """
        PUT handler for lti_2_0_result.  Assumes all authorization has been checked.
        """
        try:
            (score, comment) = self.parse_lti_2_0_result_json(request.body)
        except LTIError:
            return Response(status=404)  # have to do 404 due to spec, but 400 is better, with error msg in body

        user_instance = self.system.get_user_module_for_noauth(real_user)
        # According to http://www.imsglobal.org/lti/ltiv2p0/ltiIMGv2p0.html#_Toc361225514
        # PUTting a JSON object with no "resultScore" field is equivalent to a DELETE.
        if score is None:
            LTIModule.clear_user_module_score(real_user, user_instance)
            return Response(status=200)

        # Fall-through record the score and the comment in the module
        LTIModule.set_user_module_score(real_user, user_instance, score, self.max_score(), comment)
        return Response(status=200)

    @classmethod
    def clear_user_module_score(cls, user, user_module):
        """
        Clears the module user state, including grades and comments.
        This is a classmethod with user and module as params because we often invoke this from
        a module bound to a noauth user.
        Note that user_module SHOULD be bound to user
        """
        user_module.publish_proxy(user_module, {'event_name': 'grade_delete'}, custom_user=user)
        del user_module.module_score
        del user_module.score_comment

    @classmethod
    def set_user_module_score(cls, user, user_module, score, max_score, comment=""):
        """
        Sets the module user state, including grades and comments.
        This is a classmethod with user and module as params because we often invoke this from
        a module bound to a noauth user.
        Note that user_module SHOULD be bound to user
        """
        scaled_score = score * max_score
        user_module.module_score = scaled_score
        user_module.score_comment = comment

        # have to publish for the progress page...
        user_module.publish_proxy(
            user_module,
            {
                'event_name': 'grade',
                'value': scaled_score,
                'max_value': max_score,
            },
            custom_user=user
        )

    def verify_lti_2_0_result_rest_headers(self, request, verify_content_type=True):
        """
        Helper method to validate LTI 2.0 REST result service HTTP headers.  returns if correct, else raises LTIError
        """
        content_type = request.headers.get('Content-Type')
        if verify_content_type and content_type != LTI_2_0_JSON_CONTENT_TYPE:
            log.debug("[LTI]: v2.0 result service -- bad Content-Type: {}".format(content_type))
            raise LTIError(
                "For LTI 2.0 result service, Content-Type must be {}.  Got {}".format(LTI_2_0_JSON_CONTENT_TYPE,
                                                                                      content_type))
        try:
            self.verify_oauth_body_sign(request, content_type=LTI_2_0_JSON_CONTENT_TYPE)
        except (ValueError, LTIError) as err:
            log.debug("[LTI]: v2.0 result service -- OAuth body verification failed:  {}".format(err.message))
            raise LTIError(err.message)

    def parse_lti_2_0_result_json(self, json_str):
        """
        Helper method for verifying LTI 2.0 JSON object.
        The json_str must be loadable.  It can either be an dict (object) or an array whose first element is an dict,
        in which case that first dict is considered.
        The dict must have the "@type" key with value equal to "Result",
        "resultScore" key with value equal to a number [0, 1],
        The "@context" key must be present, but we don't do anything with it.  And the "comment" key may be
        present, in which case it must be a string.

        Returns (score, [optional]comment) if all checks out
        """
        try:
            json_obj = json.loads(json_str)
        except (ValueError, TypeError):
            msg = "Supplied JSON string in request body could not be decoded: {}".format(json_str)
            log.debug("[LTI] {}".format(msg))
            raise LTIError(msg)

        # the standard supports a list of objects, who knows why. It must contain at least 1 element, and the
        # first element must be a dict
        if type(json_obj) != dict:
            if type(json_obj) == list and len(json_obj) >= 1 and type(json_obj[0]) == dict:
                json_obj = json_obj[0]
            else:
                msg = ("Supplied JSON string is a list that does not contain an object as the first element. {}"
                       .format(json_str))
                log.debug("[LTI] {}".format(msg))
                raise LTIError(msg)

        # '@type' must be "Result"
        result_type = json_obj.get("@type")
        if result_type != "Result":
            msg = "JSON object does not contain correct @type attribute (should be 'Result', is {})".format(result_type)
            log.debug("[LTI] {}".format(msg))
            raise LTIError(msg)

        # '@context' must be present as a key
        REQUIRED_KEYS = ["@context"]  # pylint: disable=invalid-name
        for key in REQUIRED_KEYS:
            if key not in json_obj:
                msg = "JSON object does not contain required key {}".format(key)
                log.debug("[LTI] {}".format(msg))
                raise LTIError(msg)

        # 'resultScore' is not present.  If this was a PUT this means it's actually a DELETE according
        # to the LTI spec.  We will indicate this by returning None as score, "" as comment.
        # The actual delete will be handled by the caller
        if "resultScore" not in json_obj:
            return None, json_obj.get('comment', "")

        # if present, 'resultScore' must be a number between 0 and 1 inclusive
        try:
            score = float(json_obj.get('resultScore', "unconvertable"))  # Check if float is present and the right type
            if not 0 <= score <= 1:
                msg = 'score value outside the permitted range of 0-1.'
                log.debug("[LTI] {}".format(msg))
                raise LTIError(msg)
        except (TypeError, ValueError) as err:
            msg = "Could not convert resultScore to float: {}".format(err.message)
            log.debug("[LTI] {}".format(msg))
            raise LTIError(msg)

        return score, json_obj.get('comment', "")

    @classmethod
    def parse_grade_xml_body(cls, body):
        """
        Parses XML from request.body and returns parsed data

        XML body should contain nsmap with namespace, that is specified in LTI specs.

        Returns tuple: imsx_messageIdentifier, sourcedId, score, action

        Raises Exception if can't parse.
        """
        lti_spec_namespace = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0"
        namespaces = {'def': lti_spec_namespace}

        data = body.strip().encode('utf-8')
        parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
        root = etree.fromstring(data, parser=parser)

        imsx_messageIdentifier = root.xpath("//def:imsx_messageIdentifier", namespaces=namespaces)[0].text
        sourcedId = root.xpath("//def:sourcedId", namespaces=namespaces)[0].text
        score = root.xpath("//def:textString", namespaces=namespaces)[0].text
        action = root.xpath("//def:imsx_POXBody", namespaces=namespaces)[0].getchildren()[0].tag.replace('{'+lti_spec_namespace+'}', '')
        # Raise exception if score is not float or not in range 0.0-1.0 regarding spec.
        score = float(score)
        if not 0 <= score <= 1:
            raise LTIError('score value outside the permitted range of 0-1.')

        return imsx_messageIdentifier, sourcedId, score, action

    def verify_oauth_body_sign(self, request, content_type='application/x-www-form-urlencoded'):
        """
        Verify grade request from LTI provider using OAuth body signing.

        Uses http://oauth.googlecode.com/svn/spec/ext/body_hash/1.0/oauth-bodyhash.html::

            This specification extends the OAuth signature to include integrity checks on HTTP request bodies
            with content types other than application/x-www-form-urlencoded.

        Arguments:
            request: DjangoWebobRequest.

        Raises:
            LTIError if request is incorrect.
        """

        client_key, client_secret = self.get_client_key_secret()
        headers = {
            'Authorization': unicode(request.headers.get('Authorization')),
            'Content-Type': content_type,
        }

        sha1 = hashlib.sha1()
        sha1.update(request.body)
        oauth_body_hash = base64.b64encode(sha1.digest())
        oauth_params = signature.collect_parameters(headers=headers, exclude_oauth_signature=False)
        oauth_headers = dict(oauth_params)
        oauth_signature = oauth_headers.pop('oauth_signature')
        mock_request = mock.Mock(
            uri=unicode(urllib.unquote(request.url)),
            http_method=unicode(request.method),
            params=oauth_headers.items(),
            signature=oauth_signature
        )

        if oauth_body_hash != oauth_headers.get('oauth_body_hash'):
            raise LTIError("OAuth body hash verification is failed.")

        if not signature.verify_hmac_sha1(mock_request, client_secret):
            raise LTIError("OAuth signature verification is failed.")

    def get_client_key_secret(self):
        """
        Obtains client_key and client_secret credentials from current course.
        """
        course = self.get_course()
        for lti_passport in course.lti_passports:
            try:
                lti_id, key, secret = [i.strip() for i in lti_passport.split(':')]
            except ValueError:
                raise LTIError('Could not parse LTI passport: {0!r}. \
                    Should be "id:key:secret" string.'.format(lti_passport))
            if lti_id == self.lti_id.strip():
                return key, secret
        return '', ''

class LTIDescriptor(LTIFields, MetadataOnlyEditingDescriptor, EmptyDataRawDescriptor):
    """
    Descriptor for LTI Xmodule.
    """
    module_class = LTIModule
    grade_handler = module_attr('grade_handler')
    preview_handler = module_attr('preview_handler')
    lti_2_0_result_rest_handler = module_attr('lti_2_0_result_rest_handler')
    clear_user_module_score = module_attr('clear_user_module_score')
    get_outcome_service_url = module_attr('get_outcome_service_url')
    publish_proxy = module_runtime_attr('publish')
