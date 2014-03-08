# -*- coding: utf-8 -*-
"""Test for LTI Xmodule functional logic."""

from mock import Mock, patch, PropertyMock
import mock
import textwrap
import json
from lxml import etree
import json
from webob.request import Request
from copy import copy
from collections import OrderedDict
import urllib
import oauthlib
import hashlib
import base64


from xmodule.lti_module import LTIDescriptor, LTIError

from . import LogicTest


class LTIModuleTest(LogicTest):
    """Logic tests for LTI module."""
    descriptor_class = LTIDescriptor

    def setUp(self):
        super(LTIModuleTest, self).setUp()
        self.environ = {'wsgi.url_scheme': 'http', 'REQUEST_METHOD': 'POST'}
        self.request_body_xml_template = textwrap.dedent("""
            <?xml version = "1.0" encoding = "UTF-8"?>
                <imsx_POXEnvelopeRequest xmlns = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                  <imsx_POXHeader>
                    <imsx_POXRequestHeaderInfo>
                      <imsx_version>V1.0</imsx_version>
                      <imsx_messageIdentifier>{messageIdentifier}</imsx_messageIdentifier>
                    </imsx_POXRequestHeaderInfo>
                  </imsx_POXHeader>
                  <imsx_POXBody>
                    <{action}>
                      <resultRecord>
                        <sourcedGUID>
                          <sourcedId>{sourcedId}</sourcedId>
                        </sourcedGUID>
                        <result>
                          <resultScore>
                            <language>en-us</language>
                            <textString>{grade}</textString>
                          </resultScore>
                        </result>
                      </resultRecord>
                    </{action}>
                  </imsx_POXBody>
                </imsx_POXEnvelopeRequest>
            """)
        self.system.get_real_user = Mock()
        self.system.publish = Mock()
        self.system.get_user_module_for_noauth = Mock(return_value=self.xmodule)
        self.xmodule.publish_proxy = self.system.publish

        self.user_id = self.xmodule.runtime.anonymous_student_id
        self.lti_id = self.xmodule.lti_id
        self.module_id = '//MITx/999/lti/'

        sourcedId = u':'.join(urllib.quote(i) for i in (self.lti_id, self.module_id, self.user_id))

        self.DEFAULTS = {
            'sourcedId': sourcedId,
            'action': 'replaceResultRequest',
            'grade': '0.5',
            'messageIdentifier': '528243ba5241b',
        }

    def get_request_body(self, params={}):
        data = copy(self.DEFAULTS)

        data.update(params)
        return self.request_body_xml_template.format(**data)

    def get_response_values(self, response):
        parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
        root = etree.fromstring(response.body.strip(), parser=parser)
        lti_spec_namespace = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0"
        namespaces = {'def': lti_spec_namespace}

        code_major = root.xpath("//def:imsx_codeMajor", namespaces=namespaces)[0].text
        description = root.xpath("//def:imsx_description", namespaces=namespaces)[0].text
        messageIdentifier = root.xpath("//def:imsx_messageIdentifier", namespaces=namespaces)[0].text
        imsx_POXBody = root.xpath("//def:imsx_POXBody", namespaces=namespaces)[0]

        try:
            action = imsx_POXBody.getchildren()[0].tag.replace('{'+lti_spec_namespace+'}', '')
        except Exception:
            action = None

        return {
            'code_major': code_major,
            'description': description,
            'messageIdentifier': messageIdentifier,
            'action': action
        }

    @patch('xmodule.lti_module.LTIModule.get_client_key_secret', return_value=('test_client_key', u'test_client_secret'))
    def test_authorization_header_not_present(self, get_key_secret):
        """
        Request has no Authorization header.

        This is an unknown service request, i.e., it is not a part of the original service specification.
        """
        request = Request(self.environ)
        request.body = self.get_request_body()
        response = self.xmodule.grade_handler(request, '')
        real_response = self.get_response_values(response)
        expected_response = {
            'action': None,
            'code_major': 'failure',
            'description': 'OAuth verification error: Malformed authorization header',
            'messageIdentifier': self.DEFAULTS['messageIdentifier'],
        }

        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)

    @patch('xmodule.lti_module.LTIModule.get_client_key_secret', return_value=('test_client_key', u'test_client_secret'))
    def test_authorization_header_empty(self, get_key_secret):
        """
        Request Authorization header has no value.

        This is an unknown service request, i.e., it is not a part of the original service specification.
        """
        request = Request(self.environ)
        request.authorization = "bad authorization header"
        request.body = self.get_request_body()
        response = self.xmodule.grade_handler(request, '')
        real_response = self.get_response_values(response)
        expected_response = {
            'action': None,
            'code_major': 'failure',
            'description': 'OAuth verification error: Malformed authorization header',
            'messageIdentifier': self.DEFAULTS['messageIdentifier'],
        }
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)

    def test_real_user_is_none(self):
        """
        If we have no real user, we should send back failure response.
        """
        self.xmodule.verify_oauth_body_sign = Mock()
        self.xmodule.has_score = True
        self.system.get_real_user = Mock(return_value=None)
        request = Request(self.environ)
        request.body = self.get_request_body()
        response = self.xmodule.grade_handler(request, '')
        real_response = self.get_response_values(response)
        expected_response = {
            'action': None,
            'code_major': 'failure',
            'description': 'User not found.',
            'messageIdentifier': self.DEFAULTS['messageIdentifier'],
        }
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)

    def test_grade_not_in_range(self):
        """
        Grade returned from Tool Provider is outside the range 0.0-1.0.
        """
        self.xmodule.verify_oauth_body_sign = Mock()
        request = Request(self.environ)
        request.body = self.get_request_body(params={'grade': '10'})
        response = self.xmodule.grade_handler(request, '')
        real_response = self.get_response_values(response)
        expected_response = {
            'action': None,
            'code_major': 'failure',
            'description': 'Request body XML parsing error: score value outside the permitted range of 0-1.',
            'messageIdentifier': 'unknown',
        }
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)

    def test_bad_grade_decimal(self):
        """
        Grade returned from Tool Provider doesn't use a period as the decimal point.
        """
        self.xmodule.verify_oauth_body_sign = Mock()
        request = Request(self.environ)
        request.body = self.get_request_body(params={'grade': '0,5'})
        response = self.xmodule.grade_handler(request, '')
        real_response = self.get_response_values(response)
        expected_response = {
            'action': None,
            'code_major': 'failure',
            'description': 'Request body XML parsing error: invalid literal for float(): 0,5',
            'messageIdentifier': 'unknown',
        }
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)

    def test_unsupported_action(self):
        """
        Action returned from Tool Provider isn't supported.
        `replaceResultRequest` is supported only.
        """
        self.xmodule.verify_oauth_body_sign = Mock()
        request = Request(self.environ)
        request.body = self.get_request_body({'action': 'wrongAction'})
        response = self.xmodule.grade_handler(request, '')
        real_response = self.get_response_values(response)
        expected_response = {
            'action': None,
            'code_major': 'unsupported',
            'description': 'Target does not support the requested operation.',
            'messageIdentifier': self.DEFAULTS['messageIdentifier'],
        }
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)

    def test_good_request(self):
        """
        Response from Tool Provider is correct.
        """
        self.xmodule.verify_oauth_body_sign = Mock()
        self.xmodule.has_score = True
        request = Request(self.environ)
        request.body = self.get_request_body()
        response = self.xmodule.grade_handler(request, '')
        description_expected = 'Score for {sourcedId} is now {score}'.format(
                sourcedId=self.DEFAULTS['sourcedId'],
                score=self.DEFAULTS['grade'],
            )
        real_response = self.get_response_values(response)
        expected_response = {
            'action': 'replaceResultResponse',
            'code_major': 'success',
            'description': description_expected,
            'messageIdentifier': self.DEFAULTS['messageIdentifier'],
        }

        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(expected_response, real_response)
        self.assertEqual(self.xmodule.module_score, float(self.DEFAULTS['grade']))

    def test_user_id(self):
        expected_user_id = unicode(urllib.quote(self.xmodule.runtime.anonymous_student_id))
        real_user_id = self.xmodule.get_user_id()
        self.assertEqual(real_user_id, expected_user_id)

    def test_outcome_service_url(self):
        expected_outcome_service_url = '{scheme}://{host}{path}'.format(
                scheme='http' if self.xmodule.runtime.debug else 'https',
                host=self.xmodule.runtime.hostname,
                path=self.xmodule.runtime.handler_url(self.xmodule, 'grade_handler', thirdparty=True).rstrip('/?')
            )
        real_outcome_service_url = self.xmodule.get_outcome_service_url()
        self.assertEqual(real_outcome_service_url, expected_outcome_service_url)

    def test_resource_link_id(self):
        with patch('xmodule.lti_module.LTIModule.id', new_callable=PropertyMock) as mock_id:
            mock_id.return_value = self.module_id
            expected_resource_link_id = unicode(urllib.quote(self.module_id))
            real_resource_link_id = self.xmodule.get_resource_link_id()
            self.assertEqual(real_resource_link_id, expected_resource_link_id)

    def test_lis_result_sourcedid(self):
        with patch('xmodule.lti_module.LTIModule.id', new_callable=PropertyMock) as mock_id:
            mock_id.return_value = self.module_id
            expected_sourcedId = u':'.join(urllib.quote(i) for i in (self.lti_id, self.module_id, self.user_id))
            real_lis_result_sourcedid = self.xmodule.get_lis_result_sourcedid()
            self.assertEqual(real_lis_result_sourcedid, expected_sourcedId)


    @patch('xmodule.course_module.CourseDescriptor.id_to_location')
    def test_client_key_secret(self, test):
        """
        LTI module gets client key and secret provided.
        """
        #this adds lti passports to system
        mocked_course = Mock(lti_passports = ['lti_id:test_client:test_secret'])
        modulestore = Mock()
        modulestore.get_item.return_value = mocked_course
        runtime = Mock(modulestore=modulestore)
        self.xmodule.descriptor.runtime = runtime
        self.xmodule.lti_id = "lti_id"
        key, secret = self.xmodule.get_client_key_secret()
        expected = ('test_client', 'test_secret')
        self.assertEqual(expected, (key, secret))

    @patch('xmodule.course_module.CourseDescriptor.id_to_location')
    def test_client_key_secret_not_provided(self, test):
        """
        LTI module attempts to get client key and secret provided in cms.

        There are key and secret but not for specific LTI.
        """

        #this adds lti passports to system
        mocked_course = Mock(lti_passports = ['test_id:test_client:test_secret'])
        modulestore = Mock()
        modulestore.get_item.return_value = mocked_course
        runtime = Mock(modulestore=modulestore)
        self.xmodule.descriptor.runtime = runtime
        #set another lti_id
        self.xmodule.lti_id = "another_lti_id"
        key_secret = self.xmodule.get_client_key_secret()
        expected = ('','')
        self.assertEqual(expected, key_secret)

    @patch('xmodule.course_module.CourseDescriptor.id_to_location')
    def test_bad_client_key_secret(self, test):
        """
        LTI module attempts to get client key and secret provided in cms.

        There are key and secret provided in wrong format.
        """
        #this adds lti passports to system
        mocked_course = Mock(lti_passports = ['test_id_test_client_test_secret'])
        modulestore = Mock()
        modulestore.get_item.return_value = mocked_course
        runtime = Mock(modulestore=modulestore)
        self.xmodule.descriptor.runtime = runtime
        self.xmodule.lti_id = 'lti_id'
        with self.assertRaises(LTIError):
            self.xmodule.get_client_key_secret()

    @patch('xmodule.lti_module.signature.verify_hmac_sha1', return_value=True)
    @patch('xmodule.lti_module.LTIModule.get_client_key_secret', return_value=('test_client_key', u'test_client_secret'))
    def test_successful_verify_oauth_body_sign(self, get_key_secret, mocked_verify):
        """
        Test if OAuth signing was successful.
        """
        try:
            self.xmodule.verify_oauth_body_sign(self.get_signed_grade_mock_request())
        except LTIError:
            self.fail("verify_oauth_body_sign() raised LTIError unexpectedly!")

    @patch('xmodule.lti_module.signature.verify_hmac_sha1', return_value=False)
    @patch('xmodule.lti_module.LTIModule.get_client_key_secret', return_value=('test_client_key', u'test_client_secret'))
    def test_failed_verify_oauth_body_sign(self, get_key_secret, mocked_verify):
        """
        Oauth signing verify fail.
        """
        with self.assertRaises(LTIError):
            req = self.get_signed_grade_mock_request()
            self.xmodule.verify_oauth_body_sign(req)

    def get_signed_grade_mock_request(self):
        """
        Example of signed request from LTI Provider.
        """
        mock_request = Mock()
        mock_request.headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/xml',
            'Authorization': u'OAuth oauth_nonce="135685044251684026041377608307", \
                oauth_timestamp="1234567890", oauth_version="1.0", \
                oauth_signature_method="HMAC-SHA1", \
                oauth_consumer_key="test_client_key", \
                oauth_signature="my_signature%3D", \
                oauth_body_hash="gz+PeJZuF2//n9hNUnDj2v5kN70="'
        }
        mock_request.url = u'http://testurl'
        mock_request.http_method = u'POST'
        mock_request.body = textwrap.dedent("""
            <?xml version = "1.0" encoding = "UTF-8"?>
                <imsx_POXEnvelopeRequest  xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                </imsx_POXEnvelopeRequest>
        """)
        return mock_request

    def test_lti20_rest_bad_contenttype(self):
        """
        Input with bad content type
        """
        with self.assertRaisesRegexp(LTIError, "Content-Type must be"):
            request = Mock(headers={u'Content-Type': u'Non-existent'})
            self.xmodule.verify_lti_2_0_result_rest_headers(request)

    def test_lti20_rest_failed_oauth_body_verify(self):
        """
        Input with bad oauth body hash verification
        """
        err_msg = "OAuth body verification failed"
        self.xmodule.verify_oauth_body_sign = Mock(side_effect=LTIError(err_msg))
        with self.assertRaisesRegexp(LTIError, err_msg):
            request = Mock(headers={u'Content-Type': u'application/vnd.ims.lis.v2.result+json'})
            self.xmodule.verify_lti_2_0_result_rest_headers(request)

    def test_lti20_rest_good_headers(self):
        """
        Input with good oauth body hash verification
        """
        self.xmodule.verify_oauth_body_sign = Mock(return_value=True)

        request = Mock(headers={u'Content-Type': u'application/vnd.ims.lis.v2.result+json'})
        self.xmodule.verify_lti_2_0_result_rest_headers(request)
        #  We just want the above call to complete without exceptions, and to have called verify_oauth_body_sign
        self.assertTrue(self.xmodule.verify_oauth_body_sign.called)

    BAD_DISPATCH_INPUTS = [
        None,
        u"",
        u"abcd"
        u"notuser/abcd"
        u"user/"
        u"user//"
        u"user/gbere/"
        u"user/gbere/xsdf"
        u"user/ಠ益ಠ"  # not alphanumeric
    ]

    def test_lti20_rest_bad_dispatch(self):
        """
        Test the error cases for the "dispatch" argument to the LTI 2.0 handler.  Anything that doesn't
        fit the form user/<anon_id>
        """
        for einput in self.BAD_DISPATCH_INPUTS:
            with self.assertRaisesRegexp(LTIError, "No valid user id found in endpoint URL"):
                self.xmodule.parse_lti_2_0_handler_dispatch(einput)

    GOOD_DISPATCH_INPUTS = [
        (u"user/abcd3", u"abcd3"),
        (u"user/Äbcdè2", u"Äbcdè2"),  # unicode, just to make sure
    ]

    def test_lti20_rest_good_dispatch(self):
        """
        Test the good cases for the "dispatch" argument to the LTI 2.0 handler.  Anything that does
        fit the form user/<anon_id>
        """
        for ginput, expected in self.GOOD_DISPATCH_INPUTS:
            self.assertEquals(self.xmodule.parse_lti_2_0_handler_dispatch(ginput), expected)

    BAD_JSON_INPUTS = [
        # (bad inputs, error message expected)
        ([
            u"kk",   # ValueError
            u"{{}",  # ValueError
            u"{}}",  # ValueError
            3,       # TypeError
            {},      # TypeError
        ], u"Supplied JSON string in request body could not be decoded"),
        ([
            u"3",        # valid json, not array or object
            u"[]",       # valid json, array too small
            u"[3, {}]",  # valid json, 1st element not an object
        ], u"Supplied JSON string is a list that does not contain an object as the first element"),
        ([
            u'{"@type": "NOTResult"}',  # @type key must have value 'Result'
        ], u"JSON object does not contain correct @type attribute"),
        ([
            # @context missing
            u'{"@type": "Result", "resultScore": 0.1}',
        ], u"JSON object does not contain required key"),
        ([
            u'''
            {"@type": "Result",
             "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
             "resultScore": 100}'''  # score out of range
        ], u"score value outside the permitted range of 0-1."),
        ([
            u'''
            {"@type": "Result",
             "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
             "resultScore": "1b"}''',   # score ValueError
            u'''
            {"@type": "Result",
             "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
             "resultScore": {}}''',   # score TypeError
        ], u"Could not convert resultScore to float"),
    ]

    def test_lti20_bad_json(self):
        """
        Test that bad json_str to parse_lti_2_0_result_json inputs raise appropriate LTI Error
        """
        for error_inputs, error_message in self.BAD_JSON_INPUTS:
            for einput in error_inputs:
                with self.assertRaisesRegexp(LTIError, error_message):
                    self.xmodule.parse_lti_2_0_result_json(einput)

    GOOD_JSON_INPUTS = [
        (u'''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": 0.1}''', u""),  # no comment means we expect ""
        (u'''
        [{"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "@id": "anon_id:abcdef0123456789",
         "resultScore": 0.1}]''', u""),  # OK to have array of objects -- just take the first.  @id is okay too
        (u'''
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "resultScore": 0.1,
         "comment": "ಠ益ಠ"}''', u"ಠ益ಠ"),  # unicode comment
    ]

    def test_lti20_good_json(self):
        """
        Test the parsing of good comments
        """
        for json_str, expected_comment in self.GOOD_JSON_INPUTS:
            score, comment = self.xmodule.parse_lti_2_0_result_json(json_str)
            self.assertEqual(score, 0.1)
            self.assertEqual(comment, expected_comment)

    GOOD_JSON_PUT = textwrap.dedent(u"""
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "@id": "anon_id:abcdef0123456789",
         "resultScore": 0.1,
         "comment": "ಠ益ಠ"}
    """).encode('utf-8')

    GOOD_JSON_PUT_LIKE_DELETE = textwrap.dedent(u"""
        {"@type": "Result",
         "@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
         "@id": "anon_id:abcdef0123456789",
         "comment": "ಠ益ಠ"}
    """).encode('utf-8')

    def get_signed_lti20_mock_request(self, body, method=u'PUT'):
        """
        Example of signed from LTI 2.0 Provider.  Signatures and hashes are example only and won't verify
        """
        mock_request = Mock()
        mock_request.headers = {
            'Content-Type': 'application/vnd.ims.lis.v2.result+json',
            'Authorization': u'OAuth oauth_nonce="135685044251684026041377608307", \
                oauth_timestamp="1234567890", oauth_version="1.0", \
                oauth_signature_method="HMAC-SHA1", \
                oauth_consumer_key="test_client_key", \
                oauth_signature="my_signature%3D", \
                oauth_body_hash="gz+PeJZuF2//n9hNUnDj2v5kN70="'
        }
        mock_request.url = u'http://testurl'
        mock_request.http_method = method
        mock_request.method = method
        mock_request.body = body
        return mock_request

    USER_STANDIN = "IamAStringStandingInForAUser"

    def setup_system_xmodule_mocks_for_lti20_request_test(self):
        """
        Helper fn to set up mocking for lti 2.0 request test
        """
        self.system.get_real_user = Mock(return_value=self.USER_STANDIN)
        self.xmodule.max_score = Mock(return_value=1.0)
        self.xmodule.get_client_key_secret = Mock(return_value=('test_client_key', u'test_client_secret'))
        self.xmodule.verify_oauth_body_sign = Mock()

    def test_lti20_put_like_delete_success(self):
        """
        The happy path for LTI 2.0 PUT that acts like a delete
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        SCORE = 0.55  # pylint: disable=invalid-name
        COMMENT = u"ಠ益ಠ"  # pylint: disable=invalid-name
        self.xmodule.module_score = SCORE
        self.xmodule.score_comment = COMMENT
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT_LIKE_DELETE)
        # Now call the handler
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        # Now assert there's no score
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.xmodule.module_score)
        self.assertEqual(self.xmodule.score_comment, u"")
        (_, called_grade_obj), kwargs = self.system.publish.call_args
        self.assertEqual(called_grade_obj, {'event_name': 'grade_delete'})
        self.assertEqual(kwargs, {'custom_user': self.USER_STANDIN})

    def test_lti20_delete_success(self):
        """
        The happy path for LTI 2.0 DELETE
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        SCORE = 0.55  # pylint: disable=invalid-name
        COMMENT = u"ಠ益ಠ"  # pylint: disable=invalid-name
        self.xmodule.module_score = SCORE
        self.xmodule.score_comment = COMMENT
        mock_request = self.get_signed_lti20_mock_request("", method=u'DELETE')
        # Now call the handler
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        # Now assert there's no score
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.xmodule.module_score)
        self.assertEqual(self.xmodule.score_comment, u"")
        (_, called_grade_obj), kwargs = self.system.publish.call_args
        self.assertEqual(called_grade_obj, {'event_name': 'grade_delete'})
        self.assertEqual(kwargs, {'custom_user': self.USER_STANDIN})

    def test_lti20_put_set_score_success(self):
        """
        The happy path for LTI 2.0 PUT that sets a score
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT)
        # Now call the handler
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        # Now assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.xmodule.module_score, 0.1)
        self.assertEqual(self.xmodule.score_comment, u"ಠ益ಠ")
        (_, called_grade_obj), kwargs = self.system.publish.call_args
        self.assertEqual(called_grade_obj, {'event_name': 'grade', 'value': 0.1, 'max_value': 1.0})
        self.assertEqual(kwargs, {'custom_user': self.USER_STANDIN})

    def test_lti20_get_no_score_success(self):
        """
        The happy path for LTI 2.0 GET when there's no score
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        mock_request = self.get_signed_lti20_mock_request("", method=u'GET')
        # Now call the handler
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        # Now assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
                                         "@type": "Result"})

    def test_lti20_get_with_score_success(self):
        """
        The happy path for LTI 2.0 GET when there is a score
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        SCORE = 0.55  # pylint: disable=invalid-name
        COMMENT = u"ಠ益ಠ"  # pylint: disable=invalid-name
        self.xmodule.module_score = SCORE
        self.xmodule.score_comment = COMMENT
        mock_request = self.get_signed_lti20_mock_request("", method=u'GET')
        # Now call the handler
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        # Now assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"@context": "http://purl.imsglobal.org/ctx/lis/v2/Result",
                                         "@type": "Result",
                                         "resultScore": SCORE,
                                         "comment": COMMENT})

    UNSUPPORTED_HTTP_METHODS = ["OPTIONS", "HEAD", "POST", "TRACE", "CONNECT"]

    def test_lti20_unsupported_method_error(self):
        """
        Test we get a 404 when we don't GET or PUT
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT)
        for bad_method in self.UNSUPPORTED_HTTP_METHODS:
            mock_request.method = bad_method
            response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
            self.assertEqual(response.status_code, 404)

    def test_lti20_request_handler_bad_headers(self):
        """
        Test that we get a 401 when header verification fails
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        self.xmodule.verify_lti_2_0_result_rest_headers = Mock(side_effect=LTIError())
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT)
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        self.assertEqual(response.status_code, 401)

    def test_lti20_request_handler_bad_dispatch_user(self):
        """
        Test that we get a 404 when there's no (or badly formatted) user specified in the url
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT)
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, None)
        self.assertEqual(response.status_code, 404)

    def test_lti20_request_handler_bad_json(self):
        """
        Test that we get a 404 when json verification fails
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        self.xmodule.parse_lti_2_0_result_json = Mock(side_effect=LTIError())
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT)
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        self.assertEqual(response.status_code, 404)

    def test_lti20_request_handler_bad_user(self):
        """
        Test that we get a 404 when the supplied user does not exist
        """
        self.setup_system_xmodule_mocks_for_lti20_request_test()
        self.system.get_real_user = Mock(return_value=None)
        mock_request = self.get_signed_lti20_mock_request(self.GOOD_JSON_PUT)
        response = self.xmodule.lti_2_0_result_rest_handler(mock_request, "user/abcd")
        self.assertEqual(response.status_code, 404)

    def test_good_custom_params(self):
        """
        Custom parameters are presented in right format.
        """
        self.xmodule.custom_parameters = ['test_custom_params=test_custom_param_value']
        self.xmodule.get_client_key_secret = Mock(return_value=('test_client_key', 'test_client_secret'))
        self.xmodule.oauth_params = Mock()
        self.xmodule.get_input_fields()
        self.xmodule.oauth_params.assert_called_with(
            {u'custom_test_custom_params': u'test_custom_param_value'},
            'test_client_key', 'test_client_secret'
        )

    def test_bad_custom_params(self):
        """
        Custom parameters are presented in wrong format.
        """
        bad_custom_params = ['test_custom_params: test_custom_param_value']
        self.xmodule.custom_parameters = bad_custom_params
        self.xmodule.get_client_key_secret = Mock(return_value=('test_client_key', 'test_client_secret'))
        self.xmodule.oauth_params = Mock()
        with self.assertRaises(LTIError):
            self.xmodule.get_input_fields()

    def test_max_score(self):
        self.xmodule.weight = 100.0

        self.xmodule.graded = True
        self.assertEqual(self.xmodule.max_score(), None)

        self.xmodule.has_score = True
        self.assertEqual(self.xmodule.max_score(), 100.0)

        self.xmodule.graded = False
        self.assertEqual(self.xmodule.max_score(), 100.0)

