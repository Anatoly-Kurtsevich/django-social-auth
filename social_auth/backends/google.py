"""
Google OpenID and OAuth support

OAuth works straightforward using anonymous configurations, username
is generated by requesting email to the not documented, googleapis.com
service. Registered applications can define settings GOOGLE_CONSUMER_KEY
and GOOGLE_CONSUMER_SECRET and they will be used in the auth process.
Setting GOOGLE_OAUTH_EXTRA_SCOPE can be used to access different user
related data, like calendar, contacts, docs, etc.

OAuth2 works similar to OAuth but application must be defined on Google
APIs console https://code.google.com/apis/console/ Identity option.

OpenID also works straightforward, it doesn't need further configurations.
"""
import logging
logger = logging.getLogger(__name__)

from urllib import urlencode
from urllib2 import Request, urlopen
from urlparse import urlsplit

from django.conf import settings
from django.utils import simplejson
from django.contrib.auth import authenticate

from social_auth.backends import OpenIdAuth, ConsumerBasedOAuth, BaseOAuth2, \
                                 OAuthBackend, OpenIDBackend, SocialAuthBackend, USERNAME
from openid.yadis import etxrd



# Google OAuth base configuration
GOOGLE_OAUTH_SERVER = 'www.google.com'
GOOGLE_OAUTH_AUTHORIZATION_URL = 'https://www.google.com/accounts/OAuthAuthorizeToken'
GOOGLE_OAUTH_REQUEST_TOKEN_URL = 'https://www.google.com/accounts/OAuthGetRequestToken'
GOOGLE_OAUTH_ACCESS_TOKEN_URL = 'https://www.google.com/accounts/OAuthGetAccessToken'

# Google OAuth2 base configuration
GOOGLE_OAUTH2_SERVER = 'accounts.google.com'
GOOGLE_OATUH2_AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/auth'

# scope for user email, specify extra scopes in settings, for example:
# GOOGLE_OAUTH_EXTRA_SCOPE = ['https://www.google.com/m8/feeds/']
GOOGLE_OAUTH_SCOPE = ['https://www.googleapis.com/auth/userinfo#email']
GOOGLEAPIS_EMAIL = 'https://www.googleapis.com/userinfo/email'
GOOGLE_OPENID_URL = 'https://www.google.com/accounts/o8/id'

EXPIRES_NAME = getattr(settings, 'SOCIAL_AUTH_EXPIRATION', 'expires')
LOGIN_ERROR_URL = getattr(settings, 'LOGIN_ERROR_URL', settings.LOGIN_URL)
GOOGLE_APP_DOMAIN_KEY = getattr(settings, 'GOOGLE_APP_DOMAIN_KEY', 'domain')

# Backends
class GoogleOAuthBackend(OAuthBackend):
    """Google OAuth authentication backend"""
    name = 'google-oauth'

    def get_user_id(self, details, response):
        "Use google email as unique id"""
        return details['email']

    def get_user_details(self, response):
        """Return user details from Orkut account"""
        email = response['email']
        return {USERNAME: email.split('@', 1)[0],
                'email': email,
                'fullname': '',
                'first_name': '',
                'last_name': ''}


class GoogleOAuth2Backend(GoogleOAuthBackend):
    """Google OAuth2 authentication backend"""
    name = 'google-oauth2'
    EXTRA_DATA = [('refresh_token', 'refresh_token'),
                  ('expires_in', EXPIRES_NAME)]


class GoogleBackend(OpenIDBackend):
    """Google OpenID authentication backend"""
    name = 'google'

    def get_user_id(self, details, response):
        """Return user unique id provided by service. For google user email
        is unique enought to flag a single user. Email comes from schema:
        http://axschema.org/contact/email"""
        return details['email']

# Auth classes
class GoogleAuth(OpenIdAuth):
    """Google OpenID authentication"""
    AUTH_BACKEND = GoogleBackend

    def openid_url(self):
        """Return Google OpenID service url"""
        return GOOGLE_OPENID_URL


class BaseGoogleOAuth(ConsumerBasedOAuth):
    """Base class for Google OAuth mechanism"""
    AUTHORIZATION_URL = GOOGLE_OAUTH_AUTHORIZATION_URL
    REQUEST_TOKEN_URL = GOOGLE_OAUTH_REQUEST_TOKEN_URL
    ACCESS_TOKEN_URL = GOOGLE_OAUTH_ACCESS_TOKEN_URL
    SERVER_URL = GOOGLE_OAUTH_SERVER

    def user_data(self, access_token):
        """Loads user data from G service"""
        raise NotImplementedError('Implement in subclass')


class GoogleOAuth(BaseGoogleOAuth):
    """Google OAuth authorization mechanism"""
    AUTH_BACKEND = GoogleOAuthBackend
    SETTINGS_KEY_NAME = 'GOOGLE_CONSUMER_KEY'
    SETTINGS_SECRET_NAME = 'GOOGLE_CONSUMER_SECRET'

    def user_data(self, access_token):
        """Return user data from Google API"""
        request = self.oauth_request(access_token, GOOGLEAPIS_EMAIL,
                                     {'alt': 'json'})
        url, params = request.to_url().split('?', 1)
        return googleapis_email(url, params)

    def oauth_request(self, token, url, extra_params=None):
        extra_params = extra_params or {}
        scope = GOOGLE_OAUTH_SCOPE + \
                getattr(settings, 'GOOGLE_OAUTH_EXTRA_SCOPE', [])
        extra_params.update({
            'scope': ' '.join(scope),
        })
        if not self.registered():
            xoauth_displayname = getattr(settings, 'GOOGLE_DISPLAY_NAME',
                                         'Social Auth')
            extra_params['xoauth_displayname'] = xoauth_displayname
        return super(GoogleOAuth, self).oauth_request(token, url, extra_params)

    def get_key_and_secret(self):
        """Return Google OAuth Consumer Key and Consumer Secret pair, uses
        anonymous by default, beware that this marks the application as not
        registered and a security badge is displayed on authorization page.
        http://code.google.com/apis/accounts/docs/OAuth_ref.html#SigningOAuth
        """
        try:
            return super(GoogleOAuth, self).get_key_and_secret()
        except AttributeError:
            return 'anonymous', 'anonymous'

    @classmethod
    def enabled(cls):
        """Google OAuth is always enabled because of anonymous access"""
        return True

    def registered(self):
        """Check if Google OAuth Consumer Key and Consumer Secret are set"""
        key, secret = self.get_key_and_secret()
        return key != 'anonymous' and secret != 'anonymous'


# TODO: Remove this setting name check, keep for backward compatibility
_OAUTH2_KEY_NAME = hasattr(settings, 'GOOGLE_OAUTH2_CLIENT_ID') and \
                   'GOOGLE_OAUTH2_CLIENT_ID' or \
                   'GOOGLE_OAUTH2_CLIENT_KEY'


class GoogleOAuth2(BaseOAuth2):
    """Google OAuth2 support"""
    AUTH_BACKEND = GoogleOAuth2Backend
    AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/auth'
    ACCESS_TOKEN_URL = 'https://accounts.google.com/o/oauth2/token'
    SETTINGS_KEY_NAME = _OAUTH2_KEY_NAME
    SETTINGS_SECRET_NAME = 'GOOGLE_OAUTH2_CLIENT_SECRET'

    def get_scope(self):
        return GOOGLE_OAUTH_SCOPE + \
               getattr(settings, 'GOOGLE_OAUTH_EXTRA_SCOPE', [])

    def user_data(self, access_token):
        """Return user data from Google API"""
        data = {'oauth_token': access_token, 'alt': 'json'}
        return googleapis_email(GOOGLEAPIS_EMAIL, urlencode(data))


def googleapis_email(url, params):
    """Loads user data from googleapis service, only email so far as it's
    described in http://sites.google.com/site/oauthgoog/Home/emaildisplayscope

    Parameters must be passed in queryset and Authorization header as described
    on Google OAuth documentation at:
        http://groups.google.com/group/oauth/browse_thread/thread/d15add9beb418ebc
    and:
        http://code.google.com/apis/accounts/docs/OAuth2.html#CallingAnAPI
    """
    request = Request(url + '?' + params, headers={'Authorization': params})
    try:
        return simplejson.loads(urlopen(request).read())['data']
    except (ValueError, KeyError, IOError):
        return None


class GoogleAppsBackend(SocialAuthBackend):
    name = 'google-apps'
    
    def get_user_id(self, details, response):
        """ Returns claimed_id. """
        return details['uid']

    def get_user_details(self, response):
        details = {'uid': response['openid.claimed_id'],
                   'email': response.get('openid.ext1.value.email', None),
                   'first_name': response.get('openid.ext1.value.firstname', None),
                   'last_name': response.get('openid.ext1.value.lastname', None)}
        if details['email']:
            details[USERNAME] = details['email'].replace('.', '').replace('@', '')[:27]
        return details

class GoogleAppsAuth(OpenIdAuth):
    """ Google App Market Place OpenID authentication. """
    AUTH_BACKEND = GoogleAppsBackend
    XRDS_URL = 'https://www.google.com/accounts/o8/site-xrds'
    OPENID_ENDPOINT_TYPE = 'http://specs.openid.net/auth/2.0/server'
    ENDPOINT_URL = 'https://www.google.com/accounts/o8/ud'

    def openid_url(self, **kwargs):
        """ Does XRD discovery and returns OpenID URL. """
        kwargs['hd'] = self.domain_name
        url = self.XRDS_URL + '?' + urlencode(kwargs)
        response = urlopen(url)
        data = response.read()
        if response.code == 200:
            xrd = etxrd.parseXRDS(data)
            for service in etxrd.iterServices(xrd):
                if self.OPENID_ENDPOINT_TYPE in etxrd.getTypeURIs(service):
                    return etxrd.sortedURIs(service)[0]
        return LOGIN_ERROR_URL
    
    @property
    def domain_name(self):
        """ Returns domain name of the Google App. """
        domain = self.request.session.get(GOOGLE_APP_DOMAIN_KEY, None)
        if domain:
            return domain
        domain = self.data.get(GOOGLE_APP_DOMAIN_KEY, None)
        self.request.session[GOOGLE_APP_DOMAIN_KEY] = domain 
        return domain

    def auth_url(self):
        """ Returns OpenID url with extra parameters. LOGIN_ERROR_URL on case of error. """
        extra_params = self.auth_extra_arguments()
        try:
            openid_url = self.openid_url()
            if extra_params:
                query = urlsplit(openid_url).query
                openid_url += (query and '&' or '?') + urlencode(extra_params)
        except:
            logger.exception('discovery error.')
            openid_url = LOGIN_ERROR_URL
        return openid_url

    def auth_complete(self, *args, **kwargs):
        """ 
        Calls backend's authenticate method with 'response' argument, 
        initialized by request.GET parameters from Google. """
        # Verify the OpenID response via direct request to the OP
        params = kwargs['request'].GET.copy()
        params["openid.mode"] = u"check_authentication"
        response = urlopen(self.ENDPOINT_URL + '?' + urlencode(params))
        data = response.read()
        if data and 'is_valid:true' in data:
            kwargs.update({'response': params, self.AUTH_BACKEND.name: True})
            return authenticate(*args, **kwargs)
        
    @property
    def uses_redirect(self):
        """ Yes, we're redirecting to Google. """
        return True

    def auth_extra_arguments(self):
        """ Additional parameters required for Google Apps openid discovery. """
        return {
            'openid.ns': 'http://specs.openid.net/auth/2.0',
            'openid.return_to': self.request.build_absolute_uri(self.redirect),
            'openid.mode': 'checkid_setup', 
            'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.realm': self.request.build_absolute_uri('/'),
            'openid.ns.ax': 'http://openid.net/srv/ax/1.0',
            'openid.ax.mode': 'fetch_request',
            'openid.ax.required': 'firstname,lastname,language,email',
            'openid.ax.type.email': 'http://axschema.org/contact/email',
            'openid.ax.type.firstname': 'http://axschema.org/namePerson/first',
            'openid.ax.type.language': 'http://axschema.org/pref/language',
            'openid.ax.type.lastname': 'http://axschema.org/namePerson/last',
            'openid.ns.oauth': 'http://specs.openid.net/extensions/oauth/1.0',
            'openid.ext2.consumer': getattr(settings, 'GOOGLE_CONSUMER_KEY'),
            'openid.ns.pape': 'http://specs.openid.net/extensions/pape/1.0',
            'openid.ns.ui': 'http://openid.net/srv/ax/1.0',
            'openid.ns.ext2': 'http://specs.openid.net/extensions/oauth/1.0',
            }

# Backend definition
BACKENDS = {
    'google': GoogleAuth,
    'google-oauth': GoogleOAuth,
    'google-oauth2': GoogleOAuth2,
    'google-apps': GoogleAppsAuth
}
