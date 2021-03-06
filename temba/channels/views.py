# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import base64
import hashlib
import hmac
import json
import phonenumbers
import plivo
import pycountry
import pytz
import six
import time
import requests

from datetime import datetime, timedelta
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Count, Sum
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django_countries.data import COUNTRIES
from phonenumbers.phonenumberutil import region_code_for_number
from smartmin.views import SmartCRUDL, SmartReadView
from smartmin.views import SmartUpdateView, SmartDeleteView, SmartTemplateView, SmartListView, SmartFormView, SmartModelActionView
from temba.contacts.models import ContactURN, URN, TEL_SCHEME, TWITTER_SCHEME, TELEGRAM_SCHEME, FACEBOOK_SCHEME, VIBER_SCHEME
from temba.msgs.models import Broadcast, Msg, SystemLabel, QUEUED, PENDING, WIRED, OUTGOING
from temba.msgs.views import InboxView
from temba.orgs.models import Org, ACCOUNT_SID, ACCOUNT_TOKEN
from temba.orgs.views import OrgPermsMixin, OrgObjPermsMixin, ModalMixin
from temba.utils import analytics, non_atomic_when_eager, on_transaction_commit
from temba.utils.middleware import disable_middleware
from temba.utils.timezones import timezone_to_country_code
from twilio import TwilioRestException
from twython import Twython
from uuid import uuid4
from .models import Channel, ChannelEvent, SyncEvent, Alert, ChannelLog, ChannelCount

RELAYER_TYPE_ICONS = {Channel.TYPE_ANDROID: "icon-channel-android",
                      Channel.TYPE_CHIKKA: "icon-channel-external",
                      Channel.TYPE_EXTERNAL: "icon-channel-external",
                      Channel.TYPE_KANNEL: "icon-channel-kannel",
                      Channel.TYPE_LINE: "icon-line",
                      Channel.TYPE_NEXMO: "icon-channel-nexmo",
                      Channel.TYPE_VERBOICE: "icon-channel-external",
                      Channel.TYPE_TWILIO: "icon-channel-twilio",
                      Channel.TYPE_TWIML: "icon-channel-twilio",
                      Channel.TYPE_TWILIO_MESSAGING_SERVICE: "icon-channel-twilio",
                      Channel.TYPE_PLIVO: "icon-channel-plivo",
                      Channel.TYPE_CLICKATELL: "icon-channel-clickatell",
                      Channel.TYPE_TWITTER: "icon-twitter",
                      Channel.TYPE_TELEGRAM: "icon-telegram",
                      Channel.TYPE_FACEBOOK: "icon-facebook-official",
                      Channel.TYPE_VIBER: "icon-viber"}

SESSION_TWITTER_TOKEN = 'twitter_oauth_token'
SESSION_TWITTER_SECRET = 'twitter_oauth_token_secret'


COUNTRIES_NAMES = {key: value for key, value in COUNTRIES.iteritems()}
COUNTRIES_NAMES['GB'] = _("United Kingdom")
COUNTRIES_NAMES['US'] = _("United States")


COUNTRY_CALLING_CODES = {
    "AF": (93, ),  # Afghanistan
    "AX": (35818, ),  # Åland Islands
    "AL": (355, ),  # Albania
    "DZ": (213,),  # Algeria
    "AS": (1684,),  # American Samoa
    "AD": (376,),  # Andorra
    "AO": (244,),  # Angola
    "AI": (1264,),  # Anguilla
    "AQ": (),  # Antarctica
    "AG": (1268,),  # Antigua and Barbuda
    "AR": (54,),  # Argentina
    "AM": (374,),  # Armenia
    "AW": (297,),  # Aruba
    "AU": (61,),  # Australia
    "AT": (43,),  # Austria
    "AZ": (994,),  # Azerbaijan
    "BS": (1242,),  # Bahamas
    "BH": (973,),  # Bahrain
    "BD": (880,),  # Bangladesh
    "BB": (1246,),  # Barbados
    "BY": (375,),  # Belarus
    "BE": (32,),  # Belgium
    "BZ": (501,),  # Belize
    "BJ": (229,),  # Benin
    "BM": (1441,),  # Bermuda
    "BT": (975,),  # Bhutan
    "BO": (591,),  # Bolivia (Plurinational State of)
    "BQ": (5997,),  # Bonaire, Sint Eustatius and Saba
    "BA": (387,),  # Bosnia and Herzegovina
    "BW": (267,),  # Botswana
    "BV": (),  # Bouvet Island
    "BR": (55,),  # Brazil
    "IO": (246,),  # British Indian Ocean Territory
    "BN": (673,),  # Brunei Darussalam
    "BG": (359,),  # Bulgaria
    "BF": (226,),  # Burkina Faso
    "BI": (257,),  # Burundi
    "CV": (238,),  # Cabo Verde
    "KH": (855,),  # Cambodia
    "CM": (237,),  # Cameroon
    "CA": (1,),  # Canada
    "KY": (1345,),  # Cayman Islands
    "CF": (236,),  # Central African Republic
    "TD": (235,),  # Chad
    "CL": (56,),  # Chile
    "CN": (86,),  # China
    "CX": (6189164,),  # Christmas Island
    "CC": (6189162,),  # Cocos (Keeling) Islands
    "CO": (57,),  # Colombia
    "KM": (269,),  # Comoros
    "CD": (243,),  # Congo (the Democratic Republic of the)
    "CG": (242,),  # Congo
    "CK": (682,),  # Cook Islands
    "CR": (506,),  # Costa Rica
    "CI": (225,),  # Côte d'Ivoire
    "HR": (385,),  # Croatia
    "CU": (53,),  # Cuba
    "CW": (5999,),  # Curaçao
    "CY": (357,),  # Cyprus
    "CZ": (420,),  # Czech Republic
    "DK": (45,),  # Denmark
    "DJ": (253,),  # Djibouti
    "DM": (1767,),  # Dominica
    "DO": (1809, 1829, 1849),  # Dominican Republic
    "EC": (539,),  # Ecuador
    "EG": (20,),  # Egypt
    "SV": (503,),  # El Salvador
    "GQ": (240,),  # Equatorial Guinea
    "ER": (291,),  # Eritrea
    "EE": (372,),  # Estonia
    "ET": (251,),  # Ethiopia
    "FK": (500,),  # Falkland Islands  [Malvinas]
    "FO": (298,),  # Faroe Islands
    "FJ": (679,),  # Fiji
    "FI": (358,),  # Finland
    "FR": (33,),  # France
    "GF": (594,),  # French Guiana
    "PF": (689,),  # French Polynesia
    "TF": (),  # French Southern Territories
    "GA": (241,),  # Gabon
    "GM": (220,),  # Gambia
    "GE": (995,),  # Georgia
    "DE": (49,),  # Germany
    "GH": (233,),  # Ghana
    "GI": (350,),  # Gibraltar
    "GR": (30,),  # Greece
    "GL": (299,),  # Greenland
    "GD": (1473,),  # Grenada
    "GP": (590,),  # Guadeloupe
    "GU": (1671,),  # Guam
    "GT": (502,),  # Guatemala
    "GG": (441481, 447781, 447839, 447911),  # Guernsey
    "GN": (224,),  # Guinea
    "GW": (245,),  # Guinea-Bissau
    "GY": (592,),  # Guyana
    "HT": (509,),  # Haiti
    "HM": (),  # Heard Island and McDonald Islands
    "VA": (379, 3906698),  # Holy See
    "HN": (504,),  # Honduras
    "HK": (852,),  # Hong Kong
    "HU": (36,),  # Hungary
    "IS": (354,),  # Iceland
    "IN": (91,),  # India
    "ID": (62,),  # Indonesia
    "IR": (98,),  # Iran (Islamic Republic of)
    "IQ": (964,),  # Iraq
    "IE": (353,),  # Ireland
    "IM": (441624, 447524, 447624, 447924),  # Isle of Man
    "IL": (972,),  # Israel
    "IT": (39,),  # Italy
    "JM": (1876,),  # Jamaica
    "JP": (81,),  # Japan
    "JE": (441534,),  # Jersey
    "JO": (962,),  # Jordan
    "KZ": (76, 77),  # Kazakhstan
    "KE": (254,),  # Kenya
    "KI": (686,),  # Kiribati
    "KP": (850,),  # Korea (the Democratic People's Republic of)
    "KR": (82,),  # Korea (the Republic of)
    "KW": (965,),  # Kuwait
    "KG": (996,),  # Kyrgyzstan
    "LA": (856,),  # Lao People's Democratic Republic
    "LV": (371,),  # Latvia
    "LB": (961,),  # Lebanon
    "LS": (266,),  # Lesotho
    "LR": (231,),  # Liberia
    "LY": (218,),  # Libya
    "LI": (423,),  # Liechtenstein
    "LT": (370,),  # Lithuania
    "LU": (352,),  # Luxembourg
    "MO": (853,),  # Macao
    "MK": (389,),  # Macedonia (the former Yugoslav Republic of)
    "MG": (261,),  # Madagascar
    "MW": (265,),  # Malawi
    "MY": (60,),  # Malaysia
    "MV": (960,),  # Maldives
    "ML": (223,),   # Mali
    "MT": (356,),   # Malta
    "MH": (692,),   # Marshall Islands
    "MQ": (596,),   # Martinique
    "MR": (222,),   # Mauritania
    "MU": (230,),   # Mauritius
    "YT": (262269, 262639),   # Mayotte
    "MX": (52,),   # Mexico
    "FM": (691,),   # Micronesia (Federated States of)
    "MD": (373,),   # Moldova (the Republic of)
    "MC": (377,),   # Monaco
    "MN": (976,),   # Mongolia
    "ME": (382,),   # Montenegro
    "MS": (1664,),   # Montserrat
    "MA": (212,),   # Morocco
    "MZ": (258,),   # Mozambique
    "MM": (95,),   # Myanmar
    "NA": (264,),   # Namibia
    "NR": (674,),   # Nauru
    "NP": (977,),   # Nepal
    "NL": (31,),   # Netherlands
    "NC": (687,),   # New Caledonia
    "NZ": (64,),   # New Zealand
    "NI": (505,),   # Nicaragua
    "NE": (227,),   # Niger
    "NG": (243,),   # Nigeria
    "NU": (683,),   # Niue
    "NF": (6723,),   # Norfolk Island
    "MP": (1670,),   # Northern Mariana Islands
    "NO": (47,),   # Norway
    "OM": (968,),   # Oman
    "PK": (92,),   # Pakistan
    "PW": (680,),   # Palau
    "PS": (970,),   # Palestine, State of
    "PA": (507,),   # Panama
    "PG": (675,),   # Papua New Guinea
    "PY": (595,),   # Paraguay
    "PE": (51,),   # Peru
    "PH": (63,),  # _("Philippines
    "PN": (64,),   # Pitcairn
    "PL": (48,),   # Poland
    "PT": (351,),   # Portugal
    "PR": (1787, 1939),   # Puerto Rico
    "QA": (974,),   # Qatar
    "RE": (262,),   # Réunion
    "RO": (40,),   # Romania
    "RU": (7,),   # Russian Federation
    "RW": (250,),   # Rwanda
    "BL": (590,),  # _("Saint Barthélemy
    "SH": (290,),   # Saint Helena, Ascension and Tristan da Cunha
    "KN": (1869,),   # Saint Kitts and Nevis
    "LC": (1758,),   # Saint Lucia
    "MF": (590,),   # Saint Martin (French part)
    "PM": (508,),   # Saint Pierre and Miquelon
    "VC": (1784,),   # Saint Vincent and the Grenadines
    "WS": (685,),   # Samoa
    "SM": (378,),   # San Marino
    "ST": (239,),   # Sao Tome and Principe
    "SA": (966,),   # Saudi Arabia
    "SN": (221,),   # Senegal
    "RS": (381,),   # Serbia
    "SC": (248,),   # Seychelles
    "SL": (232,),   # Sierra Leone
    "SG": (65,),   # Singapore
    "SX": (1721,),   # Sint Maarten (Dutch part)
    "SK": (421,),   # Slovakia
    "SI": (386,),  # Slovenia
    "SB": (677,),   # Solomon Islands
    "SO": (252,),   # Somalia
    "ZA": (27,),   # South Africa
    "GS": (500,),   # South Georgia and the South Sandwich Islands
    "SS": (211,),   # South Sudan
    "ES": (34,),   # Spain
    "LK": (94,),   # Sri Lanka
    "SD": (249,),   # Sudan
    "SR": (597,),   # Suriname
    "SJ": (4779,),   # Svalbard and Jan Mayen
    "SZ": (268,),   # Swaziland
    "SE": (46,),   # Sweden
    "CH": (41,),   # Switzerland
    "SY": (963,),   # Syrian Arab Republic
    "TW": (886,),   # Taiwan (Province of China)
    "TJ": (992,),   # Tajikistan
    "TZ": (255,),   # Tanzania, United Republic of
    "TH": (66,),   # Thailand
    "TL": (),   # Timor-Leste
    "TG": (228,),   # Togo
    "TK": (690,),   # Tokelau
    "TO": (676,),   # Tonga
    "TT": (1868,),   # Trinidad and Tobago
    "TN": (216,),   # Tunisia
    "TR": (90,),   # Turkey
    "TM": (993,),   # Turkmenistan
    "TC": (1649,),   # Turks and Caicos Islands
    "TV": (668,),   # Tuvalu
    "UG": (256,),   # Uganda
    "UA": (380,),   # Ukraine
    "AE": (971,),   # United Arab Emirates
    "GB": (44,),   # United Kingdom of Great Britain and Northern Ireland
    "UM": (),   # United States Minor Outlying Islands
    "US": (1,),   # United States of America
    "UY": (598,),   # Uruguay
    "UZ": (998,),   # Uzbekistan
    "VU": (678,),   # Vanuatu
    "VE": (58,),   # Venezuela (Bolivarian Republic of)
    "VN": (84,),   # Viet Nam
    "VG": (),   # Virgin Islands (British)
    "VI": (),   # Virgin Islands (U.S.)
    "WF": (681,),   # Wallis and Futuna
    "EH": (),   # Western Sahara
    "YE": (967,),   # Yemen
    "ZM": (260,),   # Zambia
    "ZW": (263,),   # Zimbabwe
}

TWILIO_SEARCH_COUNTRIES_CONFIG = ('BE',  # Belgium
                                  'CA',  # Canada
                                  'FI',  # Finland
                                  'NO',  # Norway
                                  'PL',  # Poland
                                  'ES',  # Spain
                                  'SE',  # Sweden
                                  'GB',  # United Kingdom
                                  'US'   # United States
                                  )

TWILIO_SEARCH_COUNTRIES = tuple([(elt, COUNTRIES_NAMES[elt]) for elt in TWILIO_SEARCH_COUNTRIES_CONFIG])

TWILIO_SUPPORTED_COUNTRIES_CONFIG = ('AU',  # Australia
                                     'AT',  # Austria
                                     'BE',  # Belgium
                                     'CA',  # Canada
                                     'CL',  # Chile  # Beta
                                     'CZ',  # Czech Republic  # Beta
                                     'DK',  # Denmark  # Beta
                                     'EE',  # Estonia
                                     'FI',  # Finland
                                     'FR',  # France  # Beta
                                     'DE',  # Germany
                                     'HK',  # Hong Kong
                                     'HU',  # Hungary  # Beta
                                     'IE',  # Ireland,
                                     'IL',  # Israel  # Beta
                                     'LT',  # Lithuania
                                     'MX',  # Mexico  # Beta
                                     'NO',  # Norway
                                     'PL',  # Poland
                                     'ES',  # Spain
                                     'SE',  # Sweden
                                     'CH',  # Switzerland
                                     'GB',  # United Kingdom
                                     'US',  # United States
                                     )

TWILIO_SUPPORTED_COUNTRIES = tuple([(elt, COUNTRIES_NAMES[elt]) for elt in TWILIO_SUPPORTED_COUNTRIES_CONFIG])

TWILIO_SUPPORTED_COUNTRY_CODES = list(set([code
                                           for elt in TWILIO_SUPPORTED_COUNTRIES_CONFIG
                                           for code in list(COUNTRY_CALLING_CODES[elt])]))

NEXMO_SUPPORTED_COUNTRIES_CONFIG = ('DZ',  # Algeria
                                    'AR',  # Argentina
                                    'AU',  # Australia
                                    'AT',  # Austria
                                    'BH',  # Bahrain
                                    'BE',  # Belgium
                                    'BJ',  # Benin
                                    'BO',  # Bolivia
                                    'BR',  # Brazil
                                    'BG',  # Bulgaria
                                    'KH',  # Cambodia
                                    'CA',  # Canada
                                    'KY',  # Cayman Islands
                                    'CL',  # Chile
                                    'CN',  # China
                                    'CO',  # Colombia
                                    'CR',  # Costa Rica
                                    'HR',  # Croatia
                                    'CY',  # Cyprus
                                    'CZ',  # Czech Republic
                                    'DK',  # Denmark
                                    'DO',  # Dominican Republic
                                    'SV',  # El Salvador
                                    'EE',  # Estonia
                                    'FI',  # Finland
                                    'FR',  # France
                                    'GE',  # Georgia
                                    'DE',  # Germany
                                    'GH',  # Ghana
                                    'GR',  # Greece
                                    'GD',  # Grenanda
                                    'GT',  # Guatemala
                                    'HN',  # Honduras
                                    'HK',  # Hong Kong
                                    'HU',  # Hungary
                                    'IS',  # Iceland
                                    'IN',  # India
                                    'ID',  # Indonesia
                                    'IE',  # Ireland
                                    'IL',  # Israel
                                    'IT',  # Italy
                                    'JM',  # Jamaica
                                    'JP',  # Japan
                                    'KE',  # Kenya
                                    'LV',  # Latvia
                                    'LI',  # Liechtenstein
                                    'LT',  # Lithuania
                                    'LU',  # Luxembourg
                                    'MO',  # Macau
                                    'MY',  # Malaysia
                                    'MT',  # Malta
                                    'MX',  # Mexico
                                    'MD',  # Moldova
                                    'NL',  # Netherlands
                                    'NZ',  # New Zealand
                                    'NG',  # Nigeria
                                    'NO',  # Norway
                                    'PK',  # Pakistan
                                    'PA',  # Panama
                                    'PE',  # Peru
                                    'PH',  # Philippines
                                    'PL',  # Poland
                                    'PT',  # Portugal
                                    'PR',  # Puerto Rico
                                    'RO',  # Romania
                                    'RU',  # Russia
                                    'RW',  # Rwanda
                                    'SA',  # Saudi Arabia
                                    'SG',  # Singapore
                                    'SK',  # Slovakia
                                    'SI',  # Slovenia
                                    'ZA',  # South Africa
                                    'KR',  # South Korea
                                    'ES',  # Spain
                                    'SE',  # Sweden
                                    'CH',  # Switzerland
                                    'TW',  # Taiwan
                                    'TJ',  # Tajikistan
                                    'TH',  # Thailand
                                    'TT',  # Trinidad and Tobago
                                    'TR',  # Turkey
                                    'GB',  # United Kingdom
                                    'US',  # United States
                                    'UY',  # Uruguay
                                    'VE',  # Venezuala
                                    'ZM',  # Zambia
                                    )

NEXMO_SUPPORTED_COUNTRIES = tuple([(elt, COUNTRIES_NAMES[elt]) for elt in NEXMO_SUPPORTED_COUNTRIES_CONFIG])

NEXMO_SUPPORTED_COUNTRY_CODES = list(set([code
                                          for elt in NEXMO_SUPPORTED_COUNTRIES_CONFIG
                                          for code in list(COUNTRY_CALLING_CODES[elt])]))

PLIVO_SUPPORTED_COUNTRIES_CONFIG = ('AU',  # Australia
                                    'BE',  # Belgium
                                    'CA',  # Canada
                                    'CZ',  # Czech Republic
                                    'EE',  # Estonia
                                    'FI',  # Finland
                                    'DE',  # Germany
                                    'HK',  # Hong Kong
                                    'HU',  # Hungary
                                    'IL',  # Israel
                                    'LT',  # Lithuania
                                    'MX',  # Mexico
                                    'NO',  # Norway
                                    'PK',  # Pakistan
                                    'PL',  # Poland
                                    'ZA',  # South Africa
                                    'SE',  # Sweden
                                    'CH',  # Switzerland
                                    'GB',  # United Kingdom
                                    'US',  # United States
                                    )

PLIVO_SUPPORTED_COUNTRIES = tuple([(elt, COUNTRIES_NAMES[elt]) for elt in PLIVO_SUPPORTED_COUNTRIES_CONFIG])

PLIVO_SUPPORTED_COUNTRY_CODES = list(set([code
                                          for elt in PLIVO_SUPPORTED_COUNTRIES_CONFIG
                                          for code in list(COUNTRY_CALLING_CODES[elt])]))

# django_countries now uses a dict of countries, let's turn it in our tuple
# list of codes and countries sorted by country name
ALL_COUNTRIES = sorted(((code, name) for code, name in COUNTRIES_NAMES.items()), key=lambda x: x[1])


def get_channel_icon(channel_type):
    return RELAYER_TYPE_ICONS.get(channel_type, "icon-channel-external")


def get_channel_read_url(channel):
    # viber channels without service id's need to go to their claim page instead of read
    if channel.channel_type == Channel.TYPE_VIBER and channel.address == Channel.VIBER_NO_SERVICE_ID:
        return reverse('channels.channel_claim_viber', args=[channel.id])
    else:
        return reverse('channels.channel_read', args=[channel.uuid])


def channel_status_processor(request):
    status = dict()
    user = request.user

    if user.is_superuser or user.is_anonymous():
        return status

    # from the logged in user get the channel
    org = user.get_org()

    allowed = False
    if org:
        allowed = user.has_org_perm(org, 'channels.channel_claim')

    if allowed:
        # only care about channels that are older than an hour
        cutoff = timezone.now() - timedelta(hours=1)
        send_channel = org.get_send_channel(scheme=TEL_SCHEME)
        call_channel = org.get_call_channel()

        # twitter is a suitable sender
        if not send_channel:
            send_channel = org.get_send_channel(scheme=TWITTER_SCHEME)

        # as is telegram
        if not send_channel:
            send_channel = org.get_send_channel(scheme=TELEGRAM_SCHEME)

        # and facebook
        if not send_channel:
            send_channel = org.get_send_channel(scheme=FACEBOOK_SCHEME)

        # and viber
        if not send_channel:
            send_channel = org.get_send_channel(scheme=VIBER_SCHEME)

        status['send_channel'] = send_channel
        status['call_channel'] = call_channel
        status['has_outgoing_channel'] = send_channel or call_channel
        status['is_ussd_channel'] = send_channel.is_ussd() if send_channel else False

        channels = org.channels.filter(is_active=True)
        for channel in channels:

            if channel.created_on > cutoff:
                continue

            if not channel.is_new():
                # delayed out going messages
                if channel.get_delayed_outgoing_messages():
                    status['unsent_msgs'] = True

                # see if it hasn't synced in a while
                if not channel.get_recent_syncs():
                    status['delayed_syncevents'] = True

                # don't have to keep looking if they've both failed
                if 'delayed_syncevents' in status and 'unsent_msgs' in status:
                    break

    return status


def get_commands(channel, commands, sync_event=None):

    # we want to find all queued messages

    pending_msgs = []
    retry_msgs = []
    if sync_event:
        pending_msgs = sync_event.get_pending_messages()
        retry_msgs = sync_event.get_retry_messages()

    # messages without broadcast
    msgs = list(Msg.objects.filter(status__in=(PENDING, QUEUED, WIRED), channel=channel, direction=OUTGOING,
                                   broadcast=None).select_related('contact_urn').order_by('text', 'pk'))

    # all outgoing messages for our channel that are queued up
    broadcasts = Broadcast.objects.filter(status__in=[QUEUED, PENDING], schedule=None,
                                          msgs__channel=channel).distinct().order_by('created_on', 'pk')

    outgoing_messages = 0
    for broadcast in broadcasts:
        # Send command looks like this:
        # {
        #    "cmd":"send",
        #    "to":[{number:"250788382384", "id":26],
        #    "msg":"Is water point A19 still functioning?"
        # }
        msgs += list(broadcast.get_messages().filter(status__in=[PENDING, QUEUED]).exclude(topup=None))

        outgoing_messages += len(msgs)

    msgs = Msg.objects.filter(pk__in=[m.id for m in msgs]).exclude(contact__is_test=True).exclude(topup=None)

    if sync_event:
        msgs = msgs.exclude(pk__in=pending_msgs).exclude(pk__in=retry_msgs)

    if msgs:
        commands += Msg.get_sync_commands(channel=channel, msgs=msgs)

    # TODO: add in other commands for the channel
    # We need a queueable model similar to messages for sending arbitrary commands to the client

    return commands


@disable_middleware
def sync(request, channel_id):
    start = time.time()

    if request.method != 'POST':
        return HttpResponse(status=500, content='POST Required')

    commands = []
    channel = Channel.objects.filter(pk=channel_id, is_active=True)
    if not channel:
        return JsonResponse(dict(cmds=[dict(cmd='rel', relayer_id=channel_id)]))

    channel = channel[0]

    request_time = request.GET.get('ts', '')
    request_signature = request.GET.get('signature', '')

    if not channel.secret or not channel.org:
        return JsonResponse(dict(cmds=[channel.build_registration_command()]))

    # print "\n\nSECRET: '%s'" % channel.secret
    # print "TS: %s" % request_time
    # print "BODY: '%s'\n\n" % request.body

    # check that the request isn't too old (15 mins)
    now = time.time()
    if abs(now - int(request_time)) > 60 * 15:
        return JsonResponse({"error_id": 3, "error": "Old Request", "cmds": []}, status=401)

    # sign the request
    signature = hmac.new(key=str(channel.secret + request_time), msg=bytes(request.body), digestmod=hashlib.sha256).digest()

    # base64 and url sanitize
    signature = base64.urlsafe_b64encode(signature).strip()

    if request_signature != signature:
        return JsonResponse({"error_id": 1, "error": "Invalid signature: \'%(request)s\'"
                                                     % {'request': request_signature}, "cmds": []}, status=401)

    # update our last seen on our channel
    channel.last_seen = timezone.now()
    channel.save()

    sync_event = None

    # Take the update from the client
    if request.body:

        client_updates = json.loads(request.body)

        print("==GOT SYNC")
        print(json.dumps(client_updates, indent=2))

        if 'cmds' in client_updates:
            cmds = client_updates['cmds']

            for cmd in cmds:
                handled = False
                extra = None

                if 'cmd' in cmd:
                    keyword = cmd['cmd']

                    # catchall for commands that deal with a single message
                    if 'msg_id' in cmd:
                        msg = Msg.objects.filter(pk=cmd['msg_id'], org=channel.org).first()
                        if msg:
                            if msg.direction == OUTGOING:
                                handled = msg.update(cmd)
                            else:
                                handled = True

                    # creating a new message
                    elif keyword == 'mo_sms':
                        date = datetime.fromtimestamp(int(cmd['ts']) / 1000).replace(tzinfo=pytz.utc)

                        # it is possible to receive spam SMS messages from no number on some carriers
                        tel = cmd['phone'] if cmd['phone'] else 'empty'

                        if 'msg' in cmd:
                            msg = Msg.create_incoming(channel, URN.from_tel(tel), cmd['msg'], date=date)
                            if msg:
                                extra = dict(msg_id=msg.id)
                        handled = True

                    # phone event
                    elif keyword == 'call':
                        date = datetime.fromtimestamp(int(cmd['ts']) / 1000).replace(tzinfo=pytz.utc)

                        duration = 0
                        if cmd['type'] != 'miss':
                            duration = cmd['dur']

                        # Android sometimes will pass us a call from an 'unknown number', which is null
                        # ignore these events on our side as they have no purpose and break a lot of our
                        # assumptions
                        if cmd['phone']:
                            urn = URN.from_parts(TEL_SCHEME, cmd['phone'])
                            try:
                                ChannelEvent.create(channel, urn, cmd['type'], date, duration)
                            except ValueError:
                                # in some cases Android passes us invalid URNs, in those cases just ignore them
                                pass
                        handled = True

                    elif keyword == 'gcm':
                        # update our gcm and uuid
                        channel.gcm_id = cmd['gcm_id']
                        channel.uuid = cmd.get('uuid', None)
                        channel.save()

                        # no acking the gcm
                        handled = False

                    elif keyword == 'reset':
                        # release this channel
                        channel.release(False)
                        channel.save()

                        # ack that things got handled
                        handled = True

                    elif keyword == 'status':
                        sync_event = SyncEvent.create(channel, cmd, cmds)
                        Alert.check_power_alert(sync_event)

                        # tell the channel to update its org if this channel got moved
                        if channel.org and 'org_id' in cmd and channel.org.pk != cmd['org_id']:
                            commands.append(dict(cmd='claim', org_id=channel.org.pk))

                        # we don't ack status messages since they are always included
                        handled = False

                # is this something we can ack?
                if 'p_id' in cmd and handled:
                    ack = dict(p_id=cmd['p_id'], cmd="ack")
                    if extra:
                        ack['extra'] = extra

                    commands.append(ack)

    outgoing_cmds = get_commands(channel, commands, sync_event)
    result = dict(cmds=outgoing_cmds)

    if sync_event:
        sync_event.outgoing_command_count = len([_ for _ in outgoing_cmds if _['cmd'] != 'ack'])
        sync_event.save()

    print("==RESPONDING WITH:")
    print(json.dumps(result, indent=2))

    # keep track of how long a sync takes
    analytics.gauge('temba.relayer_sync', time.time() - start)

    return JsonResponse(result)


@disable_middleware
def register(request):
    """
    Endpoint for Android devices registering with this server
    """
    if request.method != 'POST':
        return HttpResponse(status=500, content=_('POST Required'))

    client_payload = json.loads(request.body)
    cmds = client_payload['cmds']

    # look up a channel with that id
    channel = Channel.get_or_create_android(cmds[0], cmds[1])
    cmd = channel.build_registration_command()

    return JsonResponse(dict(cmds=[cmd]))


class ClaimAndroidForm(forms.Form):
    claim_code = forms.CharField(max_length=12, help_text=_("The claim code from your Android phone"))
    phone_number = forms.CharField(max_length=15, help_text=_("The phone number of the phone"))

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop('org')
        super(ClaimAndroidForm, self).__init__(*args, **kwargs)

    def clean_claim_code(self):
        claim_code = self.cleaned_data['claim_code']
        claim_code = claim_code.replace(' ', '').upper()

        # is there a channel with that claim?
        channel = Channel.objects.filter(claim_code=claim_code, is_active=True).first()

        if not channel:
            raise forms.ValidationError(_("Invalid claim code, please check and try again."))
        else:
            self.cleaned_data['channel'] = channel

        return claim_code

    def clean_phone_number(self):
        number = self.cleaned_data['phone_number']

        if 'channel' in self.cleaned_data:
            channel = self.cleaned_data['channel']

            # ensure number is valid for the channel's country
            try:
                normalized = phonenumbers.parse(number, channel.country.code)
                if not phonenumbers.is_possible_number(normalized):
                    raise forms.ValidationError(_("Invalid phone number, try again."))
            except Exception:  # pragma: no cover
                raise forms.ValidationError(_("Invalid phone number, try again."))

            number = phonenumbers.format_number(normalized, phonenumbers.PhoneNumberFormat.E164)

            # ensure no other active channel has this number
            if self.org.channels.filter(address=number, is_active=True).exclude(pk=channel.pk).exists():
                raise forms.ValidationError(_("Another channel has this number. Please remove that channel first."))

        return number


class UpdateChannelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.object = kwargs['object']
        del kwargs['object']

        super(UpdateChannelForm, self).__init__(*args, **kwargs)
        self.add_config_fields()

    def add_config_fields(self):
        pass

    class Meta:
        model = Channel
        fields = 'name', 'address', 'country', 'alert_email'
        config_fields = []
        readonly = ('address', 'country',)
        labels = {'address': _('Address')}
        helps = {'address': _('The number or address of this channel')}


class UpdateNexmoForm(UpdateChannelForm):
    class Meta(UpdateChannelForm.Meta):
        readonly = ('country',)


class UpdateAndroidForm(UpdateChannelForm):
    class Meta(UpdateChannelForm.Meta):
        readonly = []
        helps = {'address': _('Phone number of this device')}


class UpdateTwitterForm(UpdateChannelForm):
    class Meta(UpdateChannelForm.Meta):
        fields = 'name', 'address', 'alert_email'
        readonly = ('address',)
        labels = {'address': _('Handle')}
        helps = {'address': _('Twitter handle of this channel')}


class ChannelCRUDL(SmartCRUDL):
    model = Channel
    actions = ('list', 'claim', 'update', 'read', 'delete', 'search_numbers', 'claim_twilio',
               'claim_android', 'claim_africas_talking', 'claim_chikka', 'configuration', 'claim_external',
               'search_nexmo', 'claim_nexmo', 'bulk_sender_options', 'create_bulk_sender', 'claim_infobip',
               'claim_hub9', 'claim_vumi', 'claim_vumi_ussd', 'create_caller', 'claim_kannel', 'claim_twitter', 'claim_shaqodoon',
               'claim_verboice', 'claim_clickatell', 'claim_plivo', 'search_plivo', 'claim_high_connection', 'claim_blackmyna',
               'claim_smscentral', 'claim_start', 'claim_telegram', 'claim_m3tech', 'claim_yo', 'claim_viber', 'create_viber',
               'claim_twilio_messaging_service', 'claim_zenvia', 'claim_jasmin', 'claim_mblox', 'claim_facebook', 'claim_globe',
               'claim_twiml_api', 'claim_line', 'claim_viber_public', 'claim_dart_media', 'claim_junebug', 'facebook_whitelist')
    permissions = True

    class AnonMixin(OrgPermsMixin):
        """
        Mixin that makes sure that anonymous orgs cannot add channels (have no permission if anon)
        """
        def has_permission(self, request, *args, **kwargs):
            org = self.derive_org()

            # can this user break anonymity? then we are fine
            if self.get_user().has_perm('contacts.contact_break_anon'):
                return True

            # otherwise if this org is anon, no go
            if not org or org.is_anon:
                return False
            else:
                return super(ChannelCRUDL.AnonMixin, self).has_permission(request, *args, **kwargs)

    class Read(OrgObjPermsMixin, SmartReadView):
        slug_url_kwarg = 'uuid'
        exclude = ('id', 'is_active', 'created_by', 'modified_by', 'modified_on', 'gcm_id')

        def get_queryset(self):
            return Channel.objects.filter(is_active=True)

        def get_gear_links(self):
            links = []

            if self.has_org_perm("channels.channel_update"):
                links.append(dict(title=_('Edit'),
                                  style='btn-primary',
                                  href=reverse('channels.channel_update', args=[self.get_object().id])))

                sender = self.get_object().get_sender()
                if sender and sender.is_delegate_sender():
                    links.append(dict(title=_('Disable Bulk Sending'),
                                      style='btn-primary',
                                      href="#",
                                      js_class='remove-sender'))
                elif self.get_object().channel_type == Channel.TYPE_ANDROID:
                    links.append(dict(title=_('Enable Bulk Sending'),
                                      style='btn-primary',
                                      href="%s?channel=%d" % (reverse("channels.channel_bulk_sender_options"), self.get_object().pk)))

                caller = self.get_object().get_caller()
                if caller and caller.is_delegate_caller():
                    links.append(dict(title=_('Disable Voice Calling'),
                                      style='btn-primary',
                                      href="#",
                                      js_class='remove-caller'))

            if self.has_org_perm("channels.channel_delete"):
                links.append(dict(title=_('Remove'),
                                  js_class='remove-channel',
                                  href="#"))

            if self.object.channel_type == Channel.TYPE_FACEBOOK and self.has_org_perm('channels.channel_facebook_whitelist'):
                links.append(dict(title=_("Whitelist Domain"), js_class='facebook-whitelist', href='#'))

            return links

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.Read, self).get_context_data(**kwargs)
            channel = self.object

            sync_events = SyncEvent.objects.filter(channel=channel.id).order_by('-created_on')
            context['last_sync'] = sync_events.first()

            if 'HTTP_X_FORMAX' in self.request.META:  # no additional data needed if request is only for formax
                return context

            if not channel.is_active:  # pragma: needs cover
                raise Http404("No active channel with that id")

            context['msg_count'] = channel.get_msg_count()
            context['ivr_count'] = channel.get_ivr_count()

            # power source stats data
            source_stats = [[event['power_source'], event['count']]
                            for event in sync_events.order_by('power_source')
                                                    .values('power_source')
                                                    .annotate(count=Count('power_source'))]
            context['source_stats'] = source_stats

            # network connected to stats
            network_stats = [[event['network_type'], event['count']]
                             for event in sync_events.order_by('network_type')
                                                     .values('network_type')
                                                     .annotate(count=Count('network_type'))]
            context['network_stats'] = network_stats

            total_network = 0
            network_share = []

            for net in network_stats:
                total_network += net[1]

            total_share = 0
            for net_stat in network_stats:
                share = int(round((100 * net_stat[1]) / float(total_network)))
                net_name = net_stat[0]

                if net_name != "NONE" and net_name != "UNKNOWN" and share > 0:
                    network_share.append([net_name, share])
                    total_share += share

            other_share = 100 - total_share
            if other_share > 0:
                network_share.append(["OTHER", other_share])

            context['network_share'] = sorted(network_share, key=lambda _: _[1], reverse=True)

            # add to context the latest sync events to display in a table
            context['latest_sync_events'] = sync_events[:10]

            # delayed sync event
            if not channel.is_new():
                if sync_events:
                    latest_sync_event = sync_events[0]
                    interval = timezone.now() - latest_sync_event.created_on
                    seconds = interval.seconds + interval.days * 24 * 3600
                    if seconds > 3600:
                        context['delayed_sync_event'] = latest_sync_event

                # unsent messages
                unsent_msgs = channel.get_delayed_outgoing_messages()

                if unsent_msgs:
                    context['unsent_msgs_count'] = unsent_msgs.count()

            end_date = (timezone.now() + timedelta(days=1)).date()
            start_date = end_date - timedelta(days=30)

            context['start_date'] = start_date
            context['end_date'] = end_date

            message_stats = []

            # build up the channels we care about for outgoing messages
            channels = [channel]
            for sender in Channel.objects.filter(parent=channel):
                channels.append(sender)

            msg_in = []
            msg_out = []
            ivr_in = []
            ivr_out = []

            message_stats.append(dict(name=_('Incoming Text'), data=msg_in))
            message_stats.append(dict(name=_('Outgoing Text'), data=msg_out))

            if context['ivr_count']:
                message_stats.append(dict(name=_('Incoming IVR'), data=ivr_in))
                message_stats.append(dict(name=_('Outgoing IVR'), data=ivr_out))

            # get all our counts for that period
            daily_counts = list(ChannelCount.objects.filter(channel__in=channels, day__gte=start_date)
                                                    .filter(count_type__in=[ChannelCount.INCOMING_MSG_TYPE,
                                                                            ChannelCount.OUTGOING_MSG_TYPE,
                                                                            ChannelCount.INCOMING_IVR_TYPE,
                                                                            ChannelCount.OUTGOING_IVR_TYPE])
                                                    .values('day', 'count_type')
                                                    .order_by('day', 'count_type')
                                                    .annotate(count_sum=Sum('count')))

            current = start_date
            while current <= end_date:
                # for every date we care about
                while daily_counts and daily_counts[0]['day'] == current:
                    daily_count = daily_counts.pop(0)
                    if daily_count['count_type'] == ChannelCount.INCOMING_MSG_TYPE:
                        msg_in.append(dict(date=daily_count['day'], count=daily_count['count_sum']))
                    elif daily_count['count_type'] == ChannelCount.OUTGOING_MSG_TYPE:
                        msg_out.append(dict(date=daily_count['day'], count=daily_count['count_sum']))
                    elif daily_count['count_type'] == ChannelCount.INCOMING_IVR_TYPE:
                        ivr_in.append(dict(date=daily_count['day'], count=daily_count['count_sum']))
                    elif daily_count['count_type'] == ChannelCount.OUTGOING_IVR_TYPE:
                        ivr_out.append(dict(date=daily_count['day'], count=daily_count['count_sum']))

                current = current + timedelta(days=1)

            context['message_stats'] = message_stats
            context['has_messages'] = len(msg_in) or len(msg_out) or len(ivr_in) or len(ivr_out)

            message_stats_table = []

            # we'll show totals for every month since this channel was started
            month_start = channel.created_on.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # get our totals grouped by month
            monthly_totals = list(ChannelCount.objects.filter(channel=channel, day__gte=month_start)
                                                      .filter(count_type__in=[ChannelCount.INCOMING_MSG_TYPE,
                                                                              ChannelCount.OUTGOING_MSG_TYPE,
                                                                              ChannelCount.INCOMING_IVR_TYPE,
                                                                              ChannelCount.OUTGOING_IVR_TYPE])
                                                      .extra({'month': "date_trunc('month', day)"})
                                                      .values('month', 'count_type')
                                                      .order_by('month', 'count_type')
                                                      .annotate(count_sum=Sum('count')))

            # calculate our summary table for last 12 months
            now = timezone.now()
            while month_start < now:
                msg_in = 0
                msg_out = 0
                ivr_in = 0
                ivr_out = 0

                while monthly_totals and monthly_totals[0]['month'] == month_start:
                    monthly_total = monthly_totals.pop(0)
                    if monthly_total['count_type'] == ChannelCount.INCOMING_MSG_TYPE:
                        msg_in = monthly_total['count_sum']
                    elif monthly_total['count_type'] == ChannelCount.OUTGOING_MSG_TYPE:
                        msg_out = monthly_total['count_sum']
                    elif monthly_total['count_type'] == ChannelCount.INCOMING_IVR_TYPE:
                        ivr_in = monthly_total['count_sum']
                    elif monthly_total['count_type'] == ChannelCount.OUTGOING_IVR_TYPE:
                        ivr_out = monthly_total['count_sum']

                message_stats_table.append(dict(month_start=month_start,
                                                incoming_messages_count=msg_in,
                                                outgoing_messages_count=msg_out,
                                                incoming_ivr_count=ivr_in,
                                                outgoing_ivr_count=ivr_out))

                month_start = (month_start + timedelta(days=32)).replace(day=1)

            # reverse our table so most recent is first
            message_stats_table.reverse()
            context['message_stats_table'] = message_stats_table

            return context

    class FacebookWhitelist(ModalMixin, OrgObjPermsMixin, SmartModelActionView):
        class DomainForm(forms.Form):
            whitelisted_domain = forms.URLField(required=True, initial='https://',
                                                help_text="The domain to whitelist for Messenger extensions  ex: https://yourdomain.com")

        slug_url_kwarg = 'uuid'
        success_url = 'uuid@channels.channel_read'
        form_class = DomainForm

        def get_queryset(self):
            return Channel.objects.filter(is_active=True, org=self.request.user.get_org())

        def execute_action(self):
            # curl -X POST -H "Content-Type: application/json" -d '{
            #  "setting_type" : "domain_whitelisting",
            #  "whitelisted_domains" : ["https://petersfancyapparel.com"],
            #  "domain_action_type": "add"
            # }' "https://graph.facebook.com/v2.6/me/thread_settings?access_token=PAGE_ACCESS_TOKEN"
            access_token = self.object.config_json()[Channel.CONFIG_AUTH_TOKEN]
            response = requests.post('https://graph.facebook.com/v2.6/me/thread_settings?access_token=' + access_token,
                                     json=dict(setting_type='domain_whitelisting',
                                               whitelisted_domains=[self.form.cleaned_data['whitelisted_domain']],
                                               domain_action_type='add'))

            if response.status_code != 200:
                response_json = response.json()
                default_error = dict(message=_("An error occured contacting the Facebook API"))
                raise ValidationError(response_json.get('error', default_error)['message'])

    class Delete(ModalMixin, OrgObjPermsMixin, SmartDeleteView):
        cancel_url = 'id@channels.channel_read'
        title = _("Remove Android")
        success_message = ''
        fields = ('id',)

        def get_success_url(self):
            return reverse('orgs.org_home')

        def post(self, request, *args, **kwargs):
            channel = self.get_object()

            try:
                channel.release(trigger_sync=self.request.META['SERVER_NAME'] != "testserver")

                if channel.channel_type == Channel.TYPE_TWILIO and not channel.is_delegate_sender():
                    messages.info(request, _("We have disconnected your Twilio number. If you do not need this number you can delete it from the Twilio website."))
                else:
                    messages.info(request, _("Your phone number has been removed."))

                return HttpResponseRedirect(self.get_success_url())

            except TwilioRestException as e:
                if e.code == 20003:
                    messages.error(request, _("We can no longer authenticate with your Twilio Account. To delete this channel please update your Twilio connection settings."))
                else:
                    messages.error(request, _("Twilio reported an error removing your channel (Twilio error %s). Please try again later." % e.code))
                return HttpResponseRedirect(reverse("orgs.org_home"))

            except Exception as e:  # pragma: no cover
                import traceback
                traceback.print_exc(e)
                messages.error(request, _("We encountered an error removing your channel, please try again later."))
                return HttpResponseRedirect(reverse("channels.channel_read", args=[channel.uuid]))

    class Update(OrgObjPermsMixin, SmartUpdateView):
        success_message = ''
        submit_button_name = _("Save Changes")

        def derive_title(self):
            return _("%s Channel") % self.object.get_channel_type_display()

        def derive_readonly(self):
            return self.form.Meta.readonly if hasattr(self, 'form') else []

        def lookup_field_label(self, context, field, default=None):
            if field in self.form.Meta.labels:
                return self.form.Meta.labels[field]
            return super(ChannelCRUDL.Update, self).lookup_field_label(context, field, default=default)

        def lookup_field_help(self, field, default=None):
            if field in self.form.Meta.helps:
                return self.form.Meta.helps[field]
            return super(ChannelCRUDL.Update, self).lookup_field_help(field, default=default)

        def get_success_url(self):
            return reverse('channels.channel_read', args=[self.object.uuid])

        def get_form_class(self):
            channel_type = self.object.channel_type
            scheme = self.object.scheme

            if channel_type == Channel.TYPE_ANDROID:
                return UpdateAndroidForm
            elif channel_type == Channel.TYPE_NEXMO:
                return UpdateNexmoForm
            elif scheme == TWITTER_SCHEME:
                return UpdateTwitterForm
            else:
                return UpdateChannelForm

        def get_form_kwargs(self):
            kwargs = super(ChannelCRUDL.Update, self).get_form_kwargs()
            kwargs['object'] = self.object
            return kwargs

        def pre_save(self, obj):
            if obj.config:
                config = json.loads(obj.config)
                for field in self.form.Meta.config_fields:  # pragma: needs cover
                    config[field] = bool(self.form.cleaned_data[field])
                obj.config = json.dumps(config)
            return obj

        def post_save(self, obj):
            # update our delegate channels with the new number
            if not obj.parent and obj.scheme == TEL_SCHEME:
                e164_phone_number = None
                try:
                    parsed = phonenumbers.parse(obj.address, None)
                    e164_phone_number = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164).strip('+')
                except Exception:
                    pass
                for channel in obj.get_delegate_channels():  # pragma: needs cover
                    channel.address = obj.address
                    channel.bod = e164_phone_number
                    channel.save(update_fields=('address', 'bod'))

            if obj.channel_type == Channel.TYPE_TWITTER:
                # notify Mage so that it refreshes this channel
                from .tasks import MageStreamAction, notify_mage_task
                on_transaction_commit(lambda: notify_mage_task.delay(obj.uuid, MageStreamAction.refresh.name))

            return obj

    class Claim(OrgPermsMixin, SmartTemplateView):

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.Claim, self).get_context_data(**kwargs)

            twilio_countries = [six.text_type(c[1]) for c in TWILIO_SEARCH_COUNTRIES]

            twilio_countries_str = ', '.join(twilio_countries[:-1])
            twilio_countries_str += ' ' + six.text_type(_('or')) + ' ' + twilio_countries[-1]

            context['twilio_countries'] = twilio_countries_str

            org = self.request.user.get_org()
            context['recommended_channel'] = org.get_recommended_channel()
            context['org_timezone'] = six.text_type(org.timezone)

            return context

    class BulkSenderOptions(OrgPermsMixin, SmartTemplateView):
        pass

    class CreateBulkSender(OrgPermsMixin, SmartFormView):

        class BulkSenderForm(forms.Form):
            connection = forms.CharField(max_length=2, widget=forms.HiddenInput, required=False)

            def __init__(self, *args, **kwargs):
                self.org = kwargs['org']
                del kwargs['org']
                super(ChannelCRUDL.CreateBulkSender.BulkSenderForm, self).__init__(*args, **kwargs)

            def clean_connection(self):
                connection = self.cleaned_data['connection']
                if connection == Channel.TYPE_NEXMO and not self.org.is_connected_to_nexmo():
                    raise forms.ValidationError(_("A connection to a Nexmo account is required"))
                return connection

        form_class = BulkSenderForm
        fields = ('connection', )

        def get_form_kwargs(self, *args, **kwargs):
            form_kwargs = super(ChannelCRUDL.CreateBulkSender, self).get_form_kwargs(*args, **kwargs)
            form_kwargs['org'] = Org.objects.get(pk=self.request.user.get_org().pk)
            return form_kwargs

        def form_valid(self, form):

            # make sure they own the channel
            channel = self.request.GET.get('channel', None)
            if channel:
                channel = self.request.user.get_org().channels.filter(pk=channel).first()
            if not channel:  # pragma: needs cover
                raise forms.ValidationError("Can't add sender for that number")

            user = self.request.user

            Channel.add_send_channel(user, channel)
            return super(ChannelCRUDL.CreateBulkSender, self).form_valid(form)

        def form_invalid(self, form):
            return super(ChannelCRUDL.CreateBulkSender, self).form_invalid(form)

        def get_success_url(self):
            return reverse('orgs.org_home')

    class CreateCaller(OrgPermsMixin, SmartFormView):
        class CallerForm(forms.Form):
            connection = forms.CharField(max_length=2, widget=forms.HiddenInput, required=False)
            channel = forms.IntegerField(widget=forms.HiddenInput, required=False)

            def __init__(self, *args, **kwargs):
                self.org = kwargs['org']
                del kwargs['org']
                super(ChannelCRUDL.CreateCaller.CallerForm, self).__init__(*args, **kwargs)

            def clean_connection(self):
                connection = self.cleaned_data['connection']
                if connection == Channel.TYPE_TWILIO and not self.org.is_connected_to_twilio():
                    raise forms.ValidationError(_("A connection to a Twilio account is required"))
                return connection

            def clean_channel(self):
                channel = self.cleaned_data['channel']
                channel = self.org.channels.filter(pk=channel).first()
                if not channel:
                    raise forms.ValidationError(_("Sorry, a caller cannot be added for that number"))
                return channel

        form_class = CallerForm
        fields = ('connection', 'channel')

        def get_form_kwargs(self, *args, **kwargs):
            form_kwargs = super(ChannelCRUDL.CreateCaller, self).get_form_kwargs(*args, **kwargs)
            form_kwargs['org'] = Org.objects.get(pk=self.request.user.get_org().pk)
            return form_kwargs

        def form_valid(self, form):
            user = self.request.user
            org = user.get_org()

            channel = form.cleaned_data['channel']
            Channel.add_call_channel(org, user, channel)
            return super(ChannelCRUDL.CreateCaller, self).form_valid(form)

        def form_invalid(self, form):
            return super(ChannelCRUDL.CreateCaller, self).form_invalid(form)

        def get_success_url(self):
            return reverse('orgs.org_home')

    class ClaimZenvia(OrgPermsMixin, SmartFormView):
        class ZVClaimForm(forms.Form):
            shortcode = forms.CharField(max_length=6, min_length=1,
                                        help_text=_("The Zenvia short code"))
            account = forms.CharField(max_length=32,
                                      help_text=_("Your account name on Zenvia"))
            code = forms.CharField(max_length=64,
                                   help_text=_("Your api code on Zenvia for authentication"))

        title = _("Connect Zenvia Account")
        fields = ('shortcode', 'account', 'code')
        form_class = ZVClaimForm
        success_url = "id@channels.channel_configuration"

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_zenvia_channel(org,
                                                     self.request.user,
                                                     phone=data['shortcode'],
                                                     account=data['account'],
                                                     code=data['code'])

            return super(ChannelCRUDL.ClaimZenvia, self).form_valid(form)

    class CreateViber(OrgPermsMixin, SmartFormView):
        class ViberCreateForm(forms.Form):
            name = forms.CharField(max_length=32, min_length=1,
                                   help_text=_("The name of your Viber bot"))

        title = _("Connect Viber Bot")
        fields = ('name',)
        form_class = ViberCreateForm
        success_url = "id@channels.channel_claim_viber"

        def form_valid(self, form):
            org = self.request.user.get_org()
            data = form.cleaned_data
            self.object = Channel.add_viber_channel(org,
                                                    self.request.user,
                                                    data['name'])

            return super(ChannelCRUDL.CreateViber, self).form_valid(form)

    class ClaimViber(OrgPermsMixin, SmartUpdateView):
        class ViberClaimForm(forms.ModelForm):
            service_id = forms.IntegerField(help_text=_("The service id provided by Viber"))

            class Meta:
                model = Channel
                fields = ('service_id',)

        title = _("Connect Viber Bot")
        fields = ('service_id',)
        form_class = ViberClaimForm
        success_url = "id@channels.channel_configuration"

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.ClaimViber, self).get_context_data(**kwargs)
            context['ip_addresses'] = settings.IP_ADDRESSES
            return context

        def form_valid(self, form):
            data = form.cleaned_data

            # save our service id as our address
            self.object.address = data['service_id']
            self.object.save()

            return super(ChannelCRUDL.ClaimViber, self).form_valid(form)

    class ClaimViberPublic(OrgPermsMixin, SmartFormView):
        class ViberClaimForm(forms.ModelForm):
            auth_token = forms.CharField(help_text=_("The authentication token provided by Viber"))

            def clean_auth_token(self):
                auth_token = self.data['auth_token']
                response = requests.post('https://chatapi.viber.com/pa/get_account_info', json=dict(auth_token=auth_token))
                if response.status_code != 200 or response.json()['status'] != 0:
                    raise ValidationError("Error validating authentication token: %s" % response.json()['status_message'])
                return auth_token

            class Meta:
                model = Channel
                fields = ('auth_token',)

        title = _("Connect Public Viber Channel")
        form_class = ViberClaimForm
        success_url = "id@channels.channel_configuration"

        def form_valid(self, form):
            data = form.cleaned_data
            try:
                self.object = Channel.add_viber_public_channel(self.request.user.get_org(), self.request.user, data['auth_token'])
            except Exception as e:
                form._errors['auth_token'] = form.error_class([six.text_type(e.message)])
                return self.form_invalid(form)

            return super(ChannelCRUDL.ClaimViberPublic, self).form_valid(form)

        @transaction.non_atomic_requests
        def dispatch(self, request, *args, **kwargs):
            return super(ChannelCRUDL.ClaimViberPublic, self).dispatch(request, *args, **kwargs)

    class ClaimKannel(OrgPermsMixin, SmartFormView):
        class KannelClaimForm(forms.Form):
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The phone number or short code you are connecting"))
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            url = forms.URLField(max_length=1024, label=_("Send URL"),
                                 help_text=_("The publicly accessible URL for your Kannel instance for sending. "
                                             "ex: https://kannel.macklemore.co/cgi-bin/sendsms"))
            username = forms.CharField(max_length=64, required=False,
                                       help_text=_("The username to use to authenticate to Kannel, if left blank we "
                                                   "will generate one for you"))
            password = forms.CharField(max_length=64, required=False,
                                       help_text=_("The password to use to authenticate to Kannel, if left blank we "
                                                   "will generate one for you"))
            encoding = forms.ChoiceField(Channel.ENCODING_CHOICES, label=_("Encoding"),
                                         help_text=_("What encoding to use for outgoing messages"))
            verify_ssl = forms.BooleanField(initial=True, required=False, label=_("Verify SSL"),
                                            help_text=_("Whether to verify the SSL connection (recommended)"))
            use_national = forms.BooleanField(initial=False, required=False, label=_("Use National Numbers"),
                                              help_text=_("Use only the national number (no country code) when "
                                                          "sending (not recommended)"))

        title = _("Connect Kannel Service")
        success_url = "id@channels.channel_configuration"
        form_class = KannelClaimForm

        def form_valid(self, form):
            org = self.request.user.get_org()
            data = form.cleaned_data

            country = data['country']
            url = data['url']
            number = data['number']
            role = Channel.ROLE_SEND + Channel.ROLE_RECEIVE

            config = {Channel.CONFIG_SEND_URL: url,
                      Channel.CONFIG_VERIFY_SSL: data.get('verify_ssl', False),
                      Channel.CONFIG_USE_NATIONAL: data.get('use_national', False),
                      Channel.CONFIG_USERNAME: data.get('username', None), Channel.CONFIG_PASSWORD: data.get('password', None),
                      Channel.CONFIG_ENCODING: data.get('encoding', Channel.ENCODING_DEFAULT)}
            self.object = Channel.add_config_external_channel(org, self.request.user, country, number, Channel.TYPE_KANNEL,
                                                              config, role=role, parent=None)

            # if they didn't set a username or password, generate them, we do this after the addition above
            # because we use the channel id in the configuration
            config = self.object.config_json()
            if not config.get(Channel.CONFIG_USERNAME, None):
                config[Channel.CONFIG_USERNAME] = '%s_%d' % (self.request.branding['name'].lower(), self.object.pk)

            if not config.get(Channel.CONFIG_PASSWORD, None):
                config[Channel.CONFIG_PASSWORD] = str(uuid4())

            self.object.config = json.dumps(config)
            self.object.save()

            return super(ChannelCRUDL.ClaimKannel, self).form_valid(form)

    class ClaimExternal(OrgPermsMixin, SmartFormView):
        class EXClaimForm(forms.Form):
            scheme = forms.ChoiceField(choices=ContactURN.SCHEME_CHOICES, label=_("URN Type"),
                                       help_text=_("The type of URNs handled by this channel"))

            number = forms.CharField(max_length=14, min_length=1, label=_("Number"), required=False,
                                     help_text=_("The phone number or that this channel will send from"))

            handle = forms.CharField(max_length=32, min_length=1, label=_("Handle"), required=False,
                                     help_text=_("The Twitter handle that this channel will send from"))

            address = forms.CharField(max_length=64, min_length=1, label=_("Address"), required=False,
                                      help_text=_("The external address that this channel will send from"))

            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"), required=False,
                                        help_text=_("The country this phone number is used in"))

            url = forms.URLField(max_length=1024, label=_("Send URL"),
                                 help_text=_("The URL we will call when sending messages, with variable substitutions"))

            method = forms.ChoiceField(choices=(('POST', "HTTP POST"), ('GET', "HTTP GET"), ('PUT', "HTTP PUT")),
                                       help_text=_("What HTTP method to use when calling the URL"))

            body = forms.CharField(max_length=1024, label=_("Request Body"), required=False,
                                   help_text=_("The URL encoded form body, if any, with variable substitutions (only used for PUT or POST)"))

        class EXSendClaimForm(forms.Form):
            url = forms.URLField(max_length=1024, label=_("Send URL"),
                                 help_text=_("The URL we will POST to when sending messages, with variable substitutions"))

            method = forms.ChoiceField(choices=(('POST', "HTTP POST"), ('GET', "HTTP GET"), ('PUT', "HTTP PUT")),
                                       help_text=_("What HTTP method to use when calling the URL"))

        title = "Connect External Service"
        success_url = "id@channels.channel_configuration"

        def derive_initial(self):
            return dict(body=Channel.CONFIG_DEFAULT_SEND_BODY)

        def get_form_class(self):
            if self.request.GET.get('role', None) == 'S':  # pragma: needs cover
                return ChannelCRUDL.ClaimExternal.EXSendClaimForm
            else:
                return ChannelCRUDL.ClaimExternal.EXClaimForm

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception("No org for this user, cannot claim")

            data = form.cleaned_data

            if self.request.GET.get('role', None) == 'S':  # pragma: needs cover
                # get our existing channel
                receive = org.get_receive_channel(TEL_SCHEME)
                role = Channel.ROLE_SEND
                scheme = TEL_SCHEME
                address = receive.address
                country = receive.country
            else:
                role = Channel.ROLE_SEND + Channel.ROLE_RECEIVE
                scheme = data['scheme']
                if scheme == TEL_SCHEME:
                    address = data['number']
                    country = data['country']
                elif scheme == TWITTER_SCHEME:  # pragma: needs cover
                    address = data['handle']
                    country = None
                else:  # pragma: needs cover
                    address = data['address']
                    country = None

            # see if there is a parent channel we are adding a delegate for
            channel = self.request.GET.get('channel', None)
            if channel:  # pragma: needs cover
                # make sure they own it
                channel = self.request.user.get_org().channels.filter(pk=channel).first()

            config = {Channel.CONFIG_SEND_URL: data['url'], Channel.CONFIG_SEND_METHOD: data['method'], Channel.CONFIG_SEND_BODY: data['body']}
            self.object = Channel.add_config_external_channel(org, self.request.user, country, address, Channel.TYPE_EXTERNAL,
                                                              config, role, scheme, parent=channel)

            return super(ChannelCRUDL.ClaimExternal, self).form_valid(form)

    class ClaimAuthenticatedExternal(OrgPermsMixin, SmartFormView):
        class AEClaimForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The phone number or short code you are connecting with country code. ex: +250788123124"))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username provided by the provider to use their API"))
            password = forms.CharField(label=_("Password"),
                                       help_text=_("The password provided by the provider to use their API"))

            def clean_number(self):
                number = self.data['number']

                # number is a shortcode, accept as is
                if len(number) > 0 and len(number) < 7:
                    return number

                # otherwise, try to parse into an international format
                if number and number[0] != '+':
                    number = '+' + number

                try:
                    cleaned = phonenumbers.parse(number, None)
                    return phonenumbers.format_number(cleaned, phonenumbers.PhoneNumberFormat.E164)
                except Exception:  # pragma: needs cover
                    raise forms.ValidationError(_("Invalid phone number, please include the country code. ex: +250788123123"))

        title = "Connect External Service"
        fields = ('country', 'number', 'username', 'password')
        form_class = AEClaimForm
        success_url = "id@channels.channel_configuration"
        channel_type = "AE"
        template_name = 'channels/channel_claim_authenticated.html'

        def get_submitted_country(self, data):
            return data['country']

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception("No org for this user, cannot claim")

            data = form.cleaned_data
            self.object = Channel.add_authenticated_external_channel(org, self.request.user,
                                                                     self.get_submitted_country(data),
                                                                     data['number'], data['username'],
                                                                     data['password'], self.channel_type,
                                                                     data.get('url'))

            return super(ChannelCRUDL.ClaimAuthenticatedExternal, self).form_valid(form)

    class ClaimInfobip(ClaimAuthenticatedExternal):
        title = _("Connect Infobip")
        channel_type = Channel.TYPE_INFOBIP

    class ClaimBlackmyna(ClaimAuthenticatedExternal):
        title = _("Connect Blackmyna")
        channel_type = Channel.TYPE_BLACKMYNA

    class ClaimSmscentral(ClaimAuthenticatedExternal):
        title = _("Connect SMSCentral")
        channel_type = Channel.TYPE_SMSCENTRAL

    class ClaimStart(ClaimAuthenticatedExternal):
        title = _("Connect Start")
        channel_type = Channel.TYPE_START

    class ClaimM3tech(ClaimAuthenticatedExternal):
        title = _("Connect M3 Tech")
        channel_type = Channel.TYPE_M3TECH

    class ClaimJasmin(ClaimAuthenticatedExternal):
        class JasminForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=4, label=_("Number"),
                                     help_text=_("The short code or phone number you are connecting."))
            url = forms.URLField(label=_("URL"),
                                 help_text=_("The URL for the Jasmin server send path. ex: https://jasmin.gateway.io/send"))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username to be used to authenticate to Jasmin"))
            password = forms.CharField(label=_("Password"),
                                       help_text=_("The password to be used to authenticate to Jasmin"))

        title = _("Connect Jasmin")
        channel_type = Channel.TYPE_JASMIN
        form_class = JasminForm
        fields = ('country', 'number', 'url', 'username', 'password')

    class ClaimJunebug(ClaimAuthenticatedExternal):
        class JunebugForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=4, label=_("Number"),
                                     help_text=("The shortcode or phone number you are connecting."))
            url = forms.URLField(label=_("URL"),
                                 help_text=_("The URL for the Junebug channel. ex: https://junebug.praekelt.org/jb/channels/3853bb51-d38a-4bca-b332-8a57c00f2a48"))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username to be used to authenticate to Junebug"),
                                       required=False)
            password = forms.CharField(label=_("Password"),
                                       help_text=_("The password to be used to authenticate to Junebug"),
                                       required=False)

        title = _("Connect Junebug")
        channel_type = Channel.TYPE_JUNEBUG
        form_class = JunebugForm
        fields = ('country', 'number', 'url', 'username', 'password')

    class ClaimMblox(ClaimAuthenticatedExternal):
        class MBloxForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=4, label=_("Number"),
                                     help_text=_("The short code or phone number you are connecting."))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username for your MBlox REST API service"))
            password = forms.CharField(label=_("API Token"),
                                       help_text=_("The API token for your MBlox REST API service"))

        title = _("Connect MBlox")
        channel_type = Channel.TYPE_MBLOX
        form_class = MBloxForm
        fields = ('country', 'number', 'username', 'password')

    class ClaimChikka(ClaimAuthenticatedExternal):
        class ChikkaForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=4, label=_("Number"),
                                     help_text=_("The short code you are connecting."))
            username = forms.CharField(label=_("Client Id"),
                                       help_text=_("The Client Id found on your Chikka API credentials page"))
            password = forms.CharField(label=_("Secret Key"),
                                       help_text=_("The Secret Key found on your Chikka API credentials page"))

        title = _("Connect Chikka")
        channel_type = Channel.TYPE_CHIKKA
        readonly = ('country', )
        form_class = ChikkaForm

        def get_country(self, obj):
            return "Philippines"

        def get_submitted_country(self, data):
            return 'PH'

    class ClaimTelegram(OrgPermsMixin, SmartFormView):
        class TelegramForm(forms.Form):
            auth_token = forms.CharField(label=_("Authentication Token"),
                                         help_text=_("The Authentication token for your Telegram Bot"))

            def __init__(self, *args, **kwargs):
                self.org = kwargs.pop('org')
                super(ChannelCRUDL.ClaimTelegram.TelegramForm, self).__init__(*args, **kwargs)

            def clean_auth_token(self):
                auth_token = self.cleaned_data['auth_token']

                # does a bot already exist on this account with that auth token
                for channel in Channel.objects.filter(org=self.org, is_active=True, channel_type=Channel.TYPE_TELEGRAM):
                    if channel.config_json()[Channel.CONFIG_AUTH_TOKEN] == auth_token:
                        raise ValidationError(_("A telegram channel for this bot already exists on your account."))

                try:
                    import telegram
                    bot = telegram.Bot(token=auth_token)
                    bot.getMe()
                except telegram.TelegramError:
                    raise ValidationError(_("Your authentication token is invalid, please check and try again"))

                return self.cleaned_data['auth_token']

        title = _("Claim Telegram")
        form_class = TelegramForm
        success_url = 'uuid@channels.channel_read'
        submit_button_name = _("Connect Telegram Bot")

        def form_valid(self, form):
            auth_token = self.form.cleaned_data['auth_token']
            self.object = Channel.add_telegram_channel(self.request.user.get_org(), self.request.user, auth_token)
            return super(ChannelCRUDL.ClaimTelegram, self).form_valid(form)

        def get_form_kwargs(self):
            kwargs = super(ChannelCRUDL.ClaimTelegram, self).get_form_kwargs()
            kwargs['org'] = self.request.user.get_org()
            return kwargs

    class ClaimYo(ClaimAuthenticatedExternal):
        class YoClaimForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The phone number or short code you are connecting with country code. "
                                                 "ex: +250788123124"))
            username = forms.CharField(label=_("Account Number"),
                                       help_text=_("Your Yo! account YBS account number"))
            password = forms.CharField(label=_("Gateway Password"),
                                       help_text=_("Your Yo! SMS Gateway password"))

        title = _("Connect Yo!")
        template_name = 'channels/channel_claim_yo.html'
        channel_type = Channel.TYPE_YO
        form_class = YoClaimForm

    class ClaimVerboice(ClaimAuthenticatedExternal):
        class VerboiceClaimForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The phone number with country code or short code you are connecting. "
                                                 "ex: +250788123124 or 15543"))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username provided by the provider to use their API"))
            password = forms.CharField(label=_("Password"),
                                       help_text=_("The password provided by the provider to use their API"))
            channel = forms.CharField(label=_("Channel Name"),
                                      help_text=_("The Verboice channel that will be handling your calls"))

        title = _("Connect Verboice")
        channel_type = Channel.TYPE_VERBOICE
        form_class = VerboiceClaimForm
        fields = ('country', 'number', 'username', 'password', 'channel')

        def form_valid(self, form):  # pragma: needs cover
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_config_external_channel(org, self.request.user,
                                                              data['country'], data['number'], Channel.TYPE_VERBOICE,
                                                              dict(username=data['username'],
                                                                   password=data['password'],
                                                                   channel=data['channel']),
                                                              role=Channel.ROLE_CALL + Channel.ROLE_ANSWER)

            return super(ChannelCRUDL.ClaimAuthenticatedExternal, self).form_valid(form)

    class ClaimGlobe(ClaimAuthenticatedExternal):
        class GlobeClaimForm(forms.Form):
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The shortcode you have been assigned by Globe Labs "
                                                 "ex: 15543"))
            app_id = forms.CharField(label=_("Application Id"),
                                     help_text=_("The id of your Globe Labs application"))
            app_secret = forms.CharField(label=_("Application Secret"),
                                         help_text=_("The secret assigned to your Globe Labs application"))
            passphrase = forms.CharField(label=_("Passphrase"),
                                         help_text=_("The passphrase assigned to you by Globe Labs to support sending"))

        title = _("Connect Globe")
        template_name = 'channels/channel_claim_globe.html'
        channel_type = Channel.TYPE_GLOBE
        form_class = GlobeClaimForm
        fields = ('number', 'app_id', 'app_secret', 'passphrase')

        def get_submitted_country(self, data):  # pragma: needs cover
            return 'PH'

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_config_external_channel(org, self.request.user,
                                                              'PH', data['number'], Channel.TYPE_GLOBE,
                                                              dict(app_id=data['app_id'],
                                                                   app_secret=data['app_secret'],
                                                                   passphrase=data['passphrase']),
                                                              role=Channel.ROLE_SEND + Channel.ROLE_RECEIVE)

            return super(ChannelCRUDL.ClaimAuthenticatedExternal, self).form_valid(form)

    class ClaimHub9(ClaimAuthenticatedExternal):
        title = _("Connect Hub9")
        channel_type = Channel.TYPE_HUB9
        readonly = ('country',)

        def get_country(self, obj):  # pragma: needs cover
            return "Indonesia"

        def get_submitted_country(self, data):  # pragma: needs cover
            return "ID"

    class ClaimDartMedia(ClaimAuthenticatedExternal):
        title = _("Connect Dart Media")
        channel_type = Channel.TYPE_DARTMEDIA
        readonly = ('country',)

        def get_country(self, obj):
            return "Indonesia"

        def get_submitted_country(self, data):
            return "ID"

    class ClaimHighConnection(ClaimAuthenticatedExternal):
        title = _("Claim High Connection")
        channel_type = Channel.TYPE_HIGH_CONNECTION

    class ClaimShaqodoon(ClaimAuthenticatedExternal):
        class ShaqodoonForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The short code you are connecting with."))
            url = forms.URLField(label=_("URL"),
                                 help_text=_("The url provided to deliver messages"))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username provided to use their API"))
            password = forms.CharField(label=_("Password"),
                                       help_text=_("The password provided to use their API"))
            key = forms.CharField(label=_("Key"),
                                  help_text=_("The key provided to sign requests"))

        title = _("Connect Shaqodoon")
        channel_type = Channel.TYPE_SHAQODOON
        readonly = ('country',)
        form_class = ShaqodoonForm
        fields = ('country', 'number', 'url', 'username', 'password', 'key')

        def get_country(self, obj):
            return "Somalia"

        def get_submitted_country(self, data):  # pragma: needs cover
            return 'SO'

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_config_external_channel(org, self.request.user,
                                                              'SO', data['number'], Channel.TYPE_SHAQODOON,
                                                              dict(key=data['key'],
                                                                   send_url=data['url'],
                                                                   username=data['username'],
                                                                   password=data['password']))

            return super(ChannelCRUDL.ClaimAuthenticatedExternal, self).form_valid(form)

    class ClaimVumi(ClaimAuthenticatedExternal):
        class VumiClaimForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The phone number with country code or short code you are connecting. ex: +250788123124 or 15543"))
            account_key = forms.CharField(label=_("Account Key"),
                                          help_text=_("Your Vumi account key as found under Account -> Details"))
            conversation_key = forms.CharField(label=_("Conversation Key"),
                                               help_text=_("The key for your Vumi conversation, can be found in the URL"))
            api_url = forms.URLField(label=_("API URL"), required=False,
                                     help_text=_("Custom VUMI API Endpoint. Leave blank to use default of: '%s'" % Channel.VUMI_GO_API_URL))

        title = _("Connect Vumi")
        channel_type = Channel.TYPE_VUMI
        form_class = VumiClaimForm
        fields = ('country', 'number', 'account_key', 'conversation_key', 'api_url')

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            if not data.get('api_url'):
                api_url = Channel.VUMI_GO_API_URL
            else:
                api_url = data.get('api_url')

            self.object = Channel.add_config_external_channel(org, self.request.user,
                                                              data['country'], data['number'], self.channel_type,
                                                              dict(account_key=data['account_key'],
                                                                   access_token=str(uuid4()),
                                                                   conversation_key=data['conversation_key'],
                                                                   api_url=api_url))

            return super(ChannelCRUDL.ClaimAuthenticatedExternal, self).form_valid(form)

    class ClaimVumiUssd(ClaimVumi):
        channel_type = Channel.TYPE_VUMI_USSD

    class ClaimClickatell(ClaimAuthenticatedExternal):
        class ClickatellForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"),
                                        help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"),
                                     help_text=_("The phone number with country code or short code you are connecting. ex: +250788123124 or 15543"))
            api_id = forms.CharField(label=_("API ID"),
                                     help_text=_("Your API ID as provided by Clickatell"))
            username = forms.CharField(label=_("Username"),
                                       help_text=_("The username for your Clickatell account"))
            password = forms.CharField(label=_("Password"),
                                       help_text=_("The password for your Clickatell account"))

            def clean_number(self):
                # if this is a long number, try to normalize it
                number = self.data['number']
                if len(number) >= 8:
                    try:
                        cleaned = phonenumbers.parse(number, self.data['country'])
                        return phonenumbers.format_number(cleaned, phonenumbers.PhoneNumberFormat.E164)
                    except Exception:  # pragma: needs cover
                        raise forms.ValidationError(_("Invalid phone number, please include the country code. ex: +250788123123"))
                else:  # pragma: needs cover
                    return number

        title = _("Connect Clickatell")
        channel_type = Channel.TYPE_CLICKATELL
        form_class = ClickatellForm
        fields = ('country', 'number', 'api_id', 'username', 'password')

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_config_external_channel(org, self.request.user,
                                                              data['country'], data['number'], Channel.TYPE_CLICKATELL,
                                                              dict(api_id=data['api_id'],
                                                                   username=data['username'],
                                                                   password=data['password']))

            return super(ChannelCRUDL.ClaimAuthenticatedExternal, self).form_valid(form)

    class ClaimAfricasTalking(OrgPermsMixin, SmartFormView):
        class ATClaimForm(forms.Form):
            shortcode = forms.CharField(max_length=6, min_length=1,
                                        help_text=_("Your short code on Africa's Talking"))
            country = forms.ChoiceField(choices=(('KE', _("Kenya")), ('UG', _("Uganda")), ('MW', _("Malawi"))))
            is_shared = forms.BooleanField(initial=False, required=False,
                                           help_text=_("Whether this short code is shared with others"))
            username = forms.CharField(max_length=32,
                                       help_text=_("Your username on Africa's Talking"))
            api_key = forms.CharField(max_length=64,
                                      help_text=_("Your api key, should be 64 characters"))

        title = _("Connect Africa's Talking Account")
        fields = ('shortcode', 'country', 'is_shared', 'username', 'api_key')
        form_class = ATClaimForm
        success_url = "id@channels.channel_configuration"

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_africas_talking_channel(org, self.request.user,
                                                              country=data['country'],
                                                              phone=data['shortcode'], username=data['username'],
                                                              api_key=data['api_key'], is_shared=data['is_shared'])

            return super(ChannelCRUDL.ClaimAfricasTalking, self).form_valid(form)

    class ClaimTwilioMessagingService(OrgPermsMixin, SmartFormView):
        class TwilioMessagingServiceForm(forms.Form):
            country = forms.ChoiceField(choices=TWILIO_SUPPORTED_COUNTRIES)
            messaging_service_sid = forms.CharField(label=_("Messaging Service SID"), help_text=_("The Twilio Messaging Service SID"))

        title = _("Add Twilio Messaging Service Channel")
        fields = ('country', 'messaging_service_sid')
        form_class = TwilioMessagingServiceForm
        success_url = "id@channels.channel_configuration"

        def __init__(self, *args):
            super(ChannelCRUDL.ClaimTwilioMessagingService, self).__init__(*args)
            self.account = None
            self.client = None
            self.object = None

        def pre_process(self, *args, **kwargs):
            org = self.request.user.get_org()
            try:
                self.client = org.get_twilio_client()
                if not self.client:
                    return HttpResponseRedirect(reverse('channels.channel_claim'))
                self.account = self.client.accounts.get(org.config_json()[ACCOUNT_SID])
            except TwilioRestException:
                return HttpResponseRedirect(reverse('channels.channel_claim'))

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.ClaimTwilioMessagingService, self).get_context_data(**kwargs)
            context['account_trial'] = self.account.type.lower() == 'trial'
            return context

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            data = form.cleaned_data
            self.object = Channel.add_twilio_messaging_service_channel(org, self.request.user,
                                                                       messaging_service_sid=data['messaging_service_sid'],
                                                                       country=data['country'])

            return super(ChannelCRUDL.ClaimTwilioMessagingService, self).form_valid(form)

    class ClaimTwimlApi(OrgPermsMixin, SmartFormView):

        class TwimlApiClaimForm(forms.Form):
            ROLES = (
                (Channel.ROLE_SEND + Channel.ROLE_RECEIVE, _('Messaging')),
                (Channel.ROLE_CALL + Channel.ROLE_ANSWER, _('Voice')),
                (Channel.ROLE_SEND + Channel.ROLE_RECEIVE + Channel.ROLE_CALL + Channel.ROLE_ANSWER, _('Both')),
            )
            country = forms.ChoiceField(choices=ALL_COUNTRIES, label=_("Country"), help_text=_("The country this phone number is used in"))
            number = forms.CharField(max_length=14, min_length=1, label=_("Number"), help_text=_("The phone number without country code or short code you are connecting."))
            url = forms.URLField(max_length=1024, label=_("TwiML REST API Host"), help_text=_("The publicly accessible URL for your TwiML REST API instance ex: https://api.twilio.com"))
            role = forms.ChoiceField(choices=ROLES, label=_("Role"), help_text=_("Choose the role that this channel supports"))
            account_sid = forms.CharField(max_length=64, required=False, help_text=_("The Account SID to use to authenticate to the TwiML REST API"), widget=forms.TextInput(attrs={'autocomplete': 'off'}))
            account_token = forms.CharField(max_length=64, required=False, help_text=_("The Account Token to use to authenticate to the TwiML REST API"), widget=forms.TextInput(attrs={'autocomplete': 'off'}))

        title = _("Connect TwiML REST API")
        success_url = "id@channels.channel_configuration"
        form_class = TwimlApiClaimForm

        def form_valid(self, form):
            org = self.request.user.get_org()
            data = form.cleaned_data

            country = data.get('country')
            number = data.get('number')
            url = data.get('url')
            role = data.get('role')

            config = {Channel.CONFIG_SEND_URL: url,
                      ACCOUNT_SID: data.get('account_sid', None),
                      ACCOUNT_TOKEN: data.get('account_token', None)}

            is_short_code = len(number) <= 6

            if not is_short_code:
                phone_number = phonenumbers.parse(number=number, region=country)
                number = "{0}{1}".format(str(phone_number.country_code), str(phone_number.national_number))

            self.object = Channel.add_twiml_api_channel(org=org, user=self.request.user, country=country, address=number, config=config, role=role)

            # if they didn't set a username or password, generate them, we do this after the addition above
            # because we use the channel id in the configuration
            config = self.object.config_json()
            if not config.get(ACCOUNT_SID, None):  # pragma: needs cover
                config[ACCOUNT_SID] = '%s_%d' % (self.request.branding['name'].lower(), self.object.pk)

            if not config.get(ACCOUNT_TOKEN, None):  # pragma: needs cover
                config[ACCOUNT_TOKEN] = str(uuid4())

            self.object.config = json.dumps(config)
            self.object.save()

            return super(ChannelCRUDL.ClaimTwimlApi, self).form_valid(form)

    class Configuration(OrgPermsMixin, SmartReadView):

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.Configuration, self).get_context_data(**kwargs)

            # if this is an external channel, build an example URL
            if self.object.channel_type == Channel.TYPE_EXTERNAL:
                send_url = self.object.config_json()[Channel.CONFIG_SEND_URL]
                send_body = self.object.config_json().get(Channel.CONFIG_SEND_BODY, Channel.CONFIG_DEFAULT_SEND_BODY)
                example_payload = {
                    'to': '+250788123123',
                    'to_no_plus': '+250788123123',
                    'text': "Love is patient. Love is kind",
                    'from': self.object.address,
                    'from_no_plus': self.object.address.lstrip('+'),
                    'id': '1241244',
                    'channel': str(self.object.id)
                }
                context['example_url'] = Channel.build_send_url(send_url, example_payload)
                context['example_body'] = Channel.build_send_url(send_body, example_payload)

            context['domain'] = settings.HOSTNAME
            context['ip_addresses'] = settings.IP_ADDRESSES

            return context

    class ClaimAndroid(OrgPermsMixin, SmartFormView):
        title = _("Register Android Phone")
        fields = ('claim_code', 'phone_number')
        form_class = ClaimAndroidForm
        title = _("Claim Channel")

        def get_form_kwargs(self):
            kwargs = super(ChannelCRUDL.ClaimAndroid, self).get_form_kwargs()
            kwargs['org'] = self.request.user.get_org()
            return kwargs

        def get_success_url(self):
            return "%s?success" % reverse('public.public_welcome')

        def form_valid(self, form):
            org = self.request.user.get_org()

            if not org:  # pragma: no cover
                raise Exception(_("No org for this user, cannot claim"))

            self.object = Channel.objects.filter(claim_code=self.form.cleaned_data['claim_code']).first()

            country = self.object.country
            phone_country = ContactURN.derive_country_from_tel(self.form.cleaned_data['phone_number'],
                                                               str(self.object.country))

            # always prefer the country of the phone number they are entering if we have one
            if phone_country and phone_country != country:  # pragma: needs cover
                self.object.country = phone_country

            analytics.track(self.request.user.username, 'temba.channel_create')

            self.object.claim(org, self.request.user, self.form.cleaned_data['phone_number'])
            self.object.save()

            # trigger a sync
            self.object.trigger_sync()

            return super(ChannelCRUDL.ClaimAndroid, self).form_valid(form)

        def derive_org(self):
            user = self.request.user
            org = None

            if not user.is_anonymous():
                org = user.get_org()

            org_id = self.request.session.get('org_id', None)
            if org_id:  # pragma: needs cover
                org = Org.objects.get(pk=org_id)

            return org

    class ClaimTwitter(OrgPermsMixin, SmartTemplateView):

        @non_atomic_when_eager
        def dispatch(self, *args, **kwargs):
            """
            Decorated with @non_atomic_when_eager so that channel object is always committed to database before Mage
            tries to access it
            """
            return super(ChannelCRUDL.ClaimTwitter, self).dispatch(*args, **kwargs)

        def pre_process(self, *args, **kwargs):
            response = super(ChannelCRUDL.ClaimTwitter, self).pre_process(*args, **kwargs)

            api_key = settings.TWITTER_API_KEY
            api_secret = settings.TWITTER_API_SECRET
            oauth_token = self.request.session.get(SESSION_TWITTER_TOKEN, None)
            oauth_token_secret = self.request.session.get(SESSION_TWITTER_SECRET, None)
            oauth_verifier = self.request.GET.get('oauth_verifier', None)

            # if we have all oauth values, then we be returning from an authorization callback
            if oauth_token and oauth_token_secret and oauth_verifier:
                twitter = Twython(api_key, api_secret, oauth_token, oauth_token_secret)
                final_step = twitter.get_authorized_tokens(oauth_verifier)
                screen_name = final_step['screen_name']
                handle_id = final_step['user_id']
                oauth_token = final_step['oauth_token']
                oauth_token_secret = final_step['oauth_token_secret']

                org = self.request.user.get_org()
                if not org:  # pragma: no cover
                    raise Exception(_("No org for this user, cannot claim"))

                channel = Channel.add_twitter_channel(org, self.request.user, screen_name, handle_id, oauth_token, oauth_token_secret)
                del self.request.session[SESSION_TWITTER_TOKEN]
                del self.request.session[SESSION_TWITTER_SECRET]

                return redirect(reverse('channels.channel_read', args=[channel.uuid]))

            return response

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.ClaimTwitter, self).get_context_data(**kwargs)

            # generate temp OAuth token and secret
            twitter = Twython(settings.TWITTER_API_KEY, settings.TWITTER_API_SECRET)
            callback_url = self.request.build_absolute_uri(reverse('channels.channel_claim_twitter'))
            auth = twitter.get_authentication_tokens(callback_url=callback_url)

            # put in session for when we return from callback
            self.request.session[SESSION_TWITTER_TOKEN] = auth['oauth_token']
            self.request.session[SESSION_TWITTER_SECRET] = auth['oauth_token_secret']

            context['twitter_auth_url'] = auth['auth_url']
            return context

    class ClaimFacebook(OrgPermsMixin, SmartFormView):
        class FacebookForm(forms.Form):
            page_access_token = forms.CharField(min_length=43, required=True,
                                                help_text=_("The Page Access Token for your Application"))

            def clean_page_access_token(self):
                token = self.cleaned_data['page_access_token']

                # hit the FB graph, see if we can load the page attributes
                response = requests.get('https://graph.facebook.com/v2.5/me', params=dict(access_token=token))
                response_json = response.json()
                if response.status_code != 200:
                    default_error = _("Invalid page access token, please check it and try again.")
                    raise ValidationError(response_json.get('error', default_error).get('message', default_error))

                self.cleaned_data['page'] = response_json
                return token

        form_class = FacebookForm

        def form_valid(self, form):
            super(ChannelCRUDL.ClaimFacebook, self).form_valid(form)
            page = form.cleaned_data['page']
            channel = Channel.add_facebook_channel(self.request.user.get_org(), self.request.user,
                                                   page['name'], page['id'], form.cleaned_data['page_access_token'])

            return HttpResponseRedirect(reverse('channels.channel_configuration', args=[channel.id]))

    class ClaimLine(OrgPermsMixin, SmartFormView):
        class LineForm(forms.Form):
            channel_secret = forms.CharField(label=_("Secret"), required=True, help_text=_("The Secret of the LINE Bot"))
            channel_access_token = forms.CharField(label=_("Access Token"), required=True, help_text=_("The Access Token of the LINE Bot"))

            def clean(self):
                from django.db.models.query import Q
                from .models import TEMBA_HEADERS

                channel_secret = self.cleaned_data.get('channel_secret')
                channel_access_token = self.cleaned_data.get('channel_access_token')

                headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % channel_access_token}
                headers.update(TEMBA_HEADERS)

                response = requests.get('https://api.line.me/v1/oauth/verify', headers=headers)
                content = response.json()

                if response.status_code != 200:
                    raise ValidationError(content.get('error_desciption'))
                else:
                    channel_id = content.get('channelId')
                    channel_mid = content.get('mid')

                    credentials = {
                        'channel_id': channel_id,
                        'channel_mid': channel_mid,
                        'channel_secret': channel_secret,
                        'channel_access_token': channel_access_token
                    }

                    existing = Channel.objects.filter(Q(config__contains=channel_id) | Q(config__contains=channel_secret) | Q(config__contains=channel_access_token), channel_type=Channel.TYPE_LINE, address=channel_mid, is_active=True).first()
                    if existing:
                        raise ValidationError(_("A channel with this configuration already exists."))

                    headers.pop('Content-Type')
                    response_profile = requests.get('https://api.line.me/v1/profile', headers=headers)
                    content_profile = json.loads(response_profile.content)

                    credentials['profile'] = {
                        'picture_url': content_profile.get('pictureUrl'),
                        'display_name': content_profile.get('displayName')
                    }

                    return credentials

        form_class = LineForm
        title = _("Line Channel")
        fields = ('channel_secret', 'channel_access_token')
        success_url = "id@channels.channel_configuration"

        def form_valid(self, form):

            profile = form.cleaned_data.get('profile')
            credentials = form.cleaned_data
            credentials.pop('profile')

            self.object = Channel.add_line_channel(org=self.request.user.get_org(), user=self.request.user, credentials=credentials, name=profile.get('display_name'))

            return super(ChannelCRUDL.ClaimLine, self).form_valid(form)

    class List(OrgPermsMixin, SmartListView):
        title = _("Channels")
        fields = ('name', 'address', 'last_seen')
        search_fields = ('name', 'number', 'org__created_by__email')

        def get_queryset(self, **kwargs):
            queryset = super(ChannelCRUDL.List, self).get_queryset(**kwargs)

            # org users see channels for their org, superuser sees all
            if not self.request.user.is_superuser:
                org = self.request.user.get_org()
                queryset = queryset.filter(org=org)

            return queryset.filter(is_active=True)

        def pre_process(self, *args, **kwargs):
            # superuser sees things as they are
            if self.request.user.is_superuser:
                return super(ChannelCRUDL.List, self).pre_process(*args, **kwargs)

            # everybody else goes to a different page depending how many channels there are
            org = self.request.user.get_org()
            channels = list(Channel.objects.filter(org=org, is_active=True).exclude(org=None))

            if len(channels) == 0:
                return HttpResponseRedirect(reverse('channels.channel_claim'))
            elif len(channels) == 1:
                return HttpResponseRedirect(reverse('channels.channel_read', args=[channels[0].uuid]))
            else:
                return super(ChannelCRUDL.List, self).pre_process(*args, **kwargs)

        def get_name(self, obj):
            return obj.get_name()

        def get_address(self, obj):
            return obj.address if obj.address else _("Unknown")

    class SearchNumbers(OrgPermsMixin, SmartFormView):
        class SearchNumbersForm(forms.Form):
            area_code = forms.CharField(max_length=3, min_length=3, required=False,
                                        help_text=_("The area code you want to search for a new number in"))
            country = forms.ChoiceField(choices=TWILIO_SEARCH_COUNTRIES)

        form_class = SearchNumbersForm

        def form_invalid(self, *args, **kwargs):
            return JsonResponse([], safe=False)

        def search_available_numbers(self, client, **kwargs):
            available_numbers = []

            kwargs['type'] = 'local'
            try:
                available_numbers += client.phone_numbers.search(**kwargs)
            except TwilioRestException:  # pragma: no cover
                pass

            kwargs['type'] = 'mobile'
            try:
                available_numbers += client.phone_numbers.search(**kwargs)
            except TwilioRestException:  # pragma: no cover
                pass

            return available_numbers

        def form_valid(self, form, *args, **kwargs):
            org = self.request.user.get_org()
            client = org.get_twilio_client()
            data = form.cleaned_data

            # if the country is not US or CANADA list using contains instead of area code
            if not data['area_code']:
                available_numbers = self.search_available_numbers(client, country=data['country'])
            elif data['country'] in ['CA', 'US']:
                available_numbers = self.search_available_numbers(client, area_code=data['area_code'], country=data['country'])
            else:
                available_numbers = self.search_available_numbers(client, contains=data['area_code'], country=data['country'])

            numbers = []

            for number in available_numbers:
                numbers.append(phonenumbers.format_number(phonenumbers.parse(number.phone_number, None),
                                                          phonenumbers.PhoneNumberFormat.INTERNATIONAL))

            if not numbers:
                if data['country'] in ['CA', 'US']:
                    return HttpResponse(json.dumps(dict(error=str(_("Sorry, no numbers found, "
                                                                    "please enter another area code and try again.")))))
                else:
                    return HttpResponse(json.dumps(dict(error=str(_("Sorry, no numbers found, "
                                                                    "please enter another pattern and try again.")))))

            return JsonResponse(numbers, safe=False)

    class BaseClaimNumber(OrgPermsMixin, SmartFormView):
        class ClaimNumberForm(forms.Form):
            country = forms.ChoiceField(choices=ALL_COUNTRIES)
            phone_number = forms.CharField(help_text=_("The phone number being added"))

            def clean_phone_number(self):
                phone = self.cleaned_data['phone_number']

                # short code should not be formatted
                if len(phone) <= 6:
                    return phone

                phone = phonenumbers.parse(phone, self.cleaned_data['country'])
                return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)

        form_class = ClaimNumberForm

        def pre_process(self, *args, **kwargs):  # pragma: needs cover
            org = self.request.user.get_org()
            try:
                client = org.get_twilio_client()
            except Exception:
                client = None

            if client:
                return None
            else:
                return HttpResponseRedirect(reverse('channels.channel_claim'))

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.BaseClaimNumber, self).get_context_data(**kwargs)

            org = self.request.user.get_org()

            try:
                context['account_numbers'] = self.get_existing_numbers(org)
            except Exception as e:
                context['account_numbers'] = []
                context['error'] = str(e)

            context['search_url'] = self.get_search_url()
            context['claim_url'] = self.get_claim_url()

            context['search_countries'] = self.get_search_countries()
            context['supported_country_iso_codes'] = self.get_supported_country_iso_codes()

            return context

        def get_search_countries(self):
            search_countries = []

            for country in self.get_search_countries_tuple():
                search_countries.append(dict(key=country[0], label=country[1]))

            return search_countries

        def get_supported_country_iso_codes(self):
            supported_country_iso_codes = []

            for country in self.get_supported_countries_tuple():
                supported_country_iso_codes.append(country[0])

            return supported_country_iso_codes

        def get_search_countries_tuple(self):  # pragma: no cover
            raise NotImplementedError('method "get_search_countries_tuple" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def get_supported_countries_tuple(self):  # pragma: no cover
            raise NotImplementedError('method "get_supported_countries_tuple" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def get_search_url(self):  # pragma: no cover
            raise NotImplementedError('method "get_search_url" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def get_claim_url(self):  # pragma: no cover
            raise NotImplementedError('method "get_claim_url" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def get_existing_numbers(self, org):  # pragma: no cover
            raise NotImplementedError('method "get_existing_numbers" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def is_valid_country(self, country_code):  # pragma: no cover
            raise NotImplementedError('method "is_valid_country" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def is_messaging_country(self, country):  # pragma: no cover
            raise NotImplementedError('method "is_messaging_country" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def claim_number(self, user, phone_number, country, role):  # pragma: no cover
            raise NotImplementedError('method "claim_number" should be overridden in %s.%s'
                                      % (self.crudl.__class__.__name__, self.__class__.__name__))

        def remove_api_credentials_from_session(self):
            pass

        def form_valid(self, form, *args, **kwargs):

            # must have an org
            org = self.request.user.get_org()
            if not org:  # pragma: needs cover
                form._errors['upgrade'] = True
                form._errors['phone_number'] = form.error_class([_("Sorry, you need to have an organization to add numbers. "
                                                                   "You can still test things out for free using an Android phone.")])
                return self.form_invalid(form)

            data = form.cleaned_data

            # no number parse for short codes
            if len(data['phone_number']) > 6:
                phone = phonenumbers.parse(data['phone_number'])
                if not self.is_valid_country(phone.country_code):  # pragma: needs cover
                    form._errors['phone_number'] = form.error_class([_("Sorry, the number you chose is not supported. "
                                                                       "You can still deploy in any country using your "
                                                                       "own SIM card and an Android phone.")])
                    return self.form_invalid(form)

            # don't add the same number twice to the same account
            existing = org.channels.filter(is_active=True, address=data['phone_number']).first()
            if existing:  # pragma: needs cover
                form._errors['phone_number'] = form.error_class([_("That number is already connected (%s)" % data['phone_number'])])
                return self.form_invalid(form)

            existing = Channel.objects.filter(is_active=True, address=data['phone_number']).first()
            if existing:  # pragma: needs cover
                form._errors['phone_number'] = form.error_class([_("That number is already connected to another account - %s (%s)" % (existing.org, existing.created_by.username))])
                return self.form_invalid(form)

            # try to claim the number
            try:
                role = Channel.ROLE_CALL + Channel.ROLE_ANSWER
                if self.is_messaging_country(data['country']):
                    role += Channel.ROLE_SEND + Channel.ROLE_RECEIVE
                self.claim_number(self.request.user, data['phone_number'], data['country'], role)
                self.remove_api_credentials_from_session()

                return HttpResponseRedirect('%s?success' % reverse('public.public_welcome'))
            except Exception as e:  # pragma: needs cover
                import traceback
                traceback.print_exc(e)
                if e.message:
                    form._errors['phone_number'] = form.error_class([six.text_type(e.message)])
                else:
                    form._errors['phone_number'] = _("An error occurred connecting your Twilio number, try removing your "
                                                     "Twilio account, reconnecting it and trying again.")
                return self.form_invalid(form)

    class ClaimTwilio(BaseClaimNumber):

        def __init__(self, *args):
            super(ChannelCRUDL.ClaimTwilio, self).__init__(*args)
            self.account = None
            self.client = None

        def get_context_data(self, **kwargs):
            context = super(ChannelCRUDL.ClaimTwilio, self).get_context_data(**kwargs)
            context['account_trial'] = self.account.type.lower() == 'trial'
            return context

        def pre_process(self, *args, **kwargs):
            org = self.request.user.get_org()
            try:
                self.client = org.get_twilio_client()
                if not self.client:
                    return HttpResponseRedirect(reverse('channels.channel_claim'))
                self.account = self.client.accounts.get(org.config_json()[ACCOUNT_SID])
            except TwilioRestException:
                return HttpResponseRedirect(reverse('channels.channel_claim'))

        def get_search_countries_tuple(self):
            return TWILIO_SEARCH_COUNTRIES

        def get_supported_countries_tuple(self):
            return ALL_COUNTRIES

        def get_search_url(self):
            return reverse('channels.channel_search_numbers')

        def get_claim_url(self):
            return reverse('channels.channel_claim_twilio')

        def get_existing_numbers(self, org):
            client = org.get_twilio_client()
            if client:
                twilio_account_numbers = client.phone_numbers.list()
                twilio_short_codes = client.sms.short_codes.list()

            numbers = []
            for number in twilio_account_numbers:
                parsed = phonenumbers.parse(number.phone_number, None)
                numbers.append(dict(number=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                                    country=region_code_for_number(parsed)))

            org_country = timezone_to_country_code(org.timezone)
            for number in twilio_short_codes:
                numbers.append(dict(number=number.short_code, country=org_country))

            return numbers

        def is_valid_country(self, country_code):
            return True

        def is_messaging_country(self, country):
            return country in [c[0] for c in TWILIO_SUPPORTED_COUNTRIES]

        def claim_number(self, user, phone_number, country, role):
            analytics.track(user.username, 'temba.channel_claim_twilio', properties=dict(number=phone_number))

            # add this channel
            return Channel.add_twilio_channel(user.get_org(), user, phone_number, country, role)

    class ClaimNexmo(BaseClaimNumber):
        class ClaimNexmoForm(forms.Form):
            country = forms.ChoiceField(choices=NEXMO_SUPPORTED_COUNTRIES)
            phone_number = forms.CharField(help_text=_("The phone number being added"))

            def clean_phone_number(self):
                if not self.cleaned_data.get('country', None):  # pragma: needs cover
                    raise ValidationError(_("That number is not currently supported."))

                phone = self.cleaned_data['phone_number']
                phone = phonenumbers.parse(phone, self.cleaned_data['country'])

                return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)

        form_class = ClaimNexmoForm

        template_name = 'channels/channel_claim_nexmo.html'

        def pre_process(self, *args, **kwargs):
            org = Org.objects.get(pk=self.request.user.get_org().pk)
            try:
                client = org.get_nexmo_client()
            except Exception:  # pragma: needs cover
                client = None

            if client:
                return None
            else:  # pragma: needs cover
                return HttpResponseRedirect(reverse('channels.channel_claim'))

        def is_valid_country(self, country_code):
            return country_code in NEXMO_SUPPORTED_COUNTRY_CODES

        def is_messaging_country(self, country):
            return country in [c[0] for c in NEXMO_SUPPORTED_COUNTRIES]

        def get_search_url(self):
            return reverse('channels.channel_search_nexmo')

        def get_claim_url(self):
            return reverse('channels.channel_claim_nexmo')

        def get_supported_countries_tuple(self):
            return NEXMO_SUPPORTED_COUNTRIES

        def get_search_countries_tuple(self):
            return NEXMO_SUPPORTED_COUNTRIES

        def get_existing_numbers(self, org):
            client = org.get_nexmo_client()
            if client:
                account_numbers = client.get_numbers(size=100)

            numbers = []
            for number in account_numbers:
                if number['type'] == 'mobile-shortcode':  # pragma: needs cover
                    phone_number = number['msisdn']
                else:
                    parsed = phonenumbers.parse(number['msisdn'], number['country'])
                    phone_number = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                numbers.append(dict(number=phone_number, country=number['country']))

            return numbers

        def claim_number(self, user, phone_number, country, role):
            analytics.track(user.username, 'temba.channel_claim_nexmo', dict(number=phone_number))

            # add this channel
            channel = Channel.add_nexmo_channel(user.get_org(),
                                                user,
                                                country,
                                                phone_number)

            return channel

    class SearchNexmo(SearchNumbers):
        class SearchNexmoForm(forms.Form):
            area_code = forms.CharField(max_length=7, required=False,
                                        help_text=_("The area code you want to search for a new number in"))
            country = forms.ChoiceField(choices=NEXMO_SUPPORTED_COUNTRIES)

        form_class = SearchNexmoForm

        def form_valid(self, form, *args, **kwargs):  # pragma: needs cover
            org = self.request.user.get_org()
            client = org.get_nexmo_client()
            data = form.cleaned_data

            try:
                available_numbers = client.search_numbers(data['country'], data['area_code'])
                numbers = []

                for number in available_numbers:
                    numbers.append(phonenumbers.format_number(phonenumbers.parse(number['msisdn'], data['country']),
                                                              phonenumbers.PhoneNumberFormat.INTERNATIONAL))

                return JsonResponse(numbers, safe=False)
            except Exception as e:
                return JsonResponse(dict(error=str(e)))

    class ClaimPlivo(BaseClaimNumber):
        class ClaimPlivoForm(forms.Form):
            country = forms.ChoiceField(choices=PLIVO_SUPPORTED_COUNTRIES)
            phone_number = forms.CharField(help_text=_("The phone number being added"))

            def clean_phone_number(self):
                if not self.cleaned_data.get('country', None):  # pragma: needs cover
                    raise ValidationError(_("That number is not currently supported."))

                phone = self.cleaned_data['phone_number']
                phone = phonenumbers.parse(phone, self.cleaned_data['country'])

                return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)

        form_class = ClaimPlivoForm
        template_name = 'channels/channel_claim_plivo.html'

        def pre_process(self, *args, **kwargs):
            client = self.get_valid_client()

            if client:
                return None
            else:
                return HttpResponseRedirect(reverse('channels.channel_claim'))

        def get_valid_client(self):
            auth_id = self.request.session.get(Channel.CONFIG_PLIVO_AUTH_ID, None)
            auth_token = self.request.session.get(Channel.CONFIG_PLIVO_AUTH_TOKEN, None)

            try:
                client = plivo.RestAPI(auth_id, auth_token)
                validation_response = client.get_account()
                if validation_response[0] != 200:
                    client = None
            except plivo.PlivoError:  # pragma: needs cover
                client = None

            return client

        def is_valid_country(self, country_code):
            return country_code in PLIVO_SUPPORTED_COUNTRY_CODES

        def is_messaging_country(self, country):
            return country in [c[0] for c in PLIVO_SUPPORTED_COUNTRIES]

        def get_search_url(self):
            return reverse('channels.channel_search_plivo')

        def get_claim_url(self):
            return reverse('channels.channel_claim_plivo')

        def get_supported_countries_tuple(self):
            return PLIVO_SUPPORTED_COUNTRIES

        def get_search_countries_tuple(self):
            return PLIVO_SUPPORTED_COUNTRIES

        def get_existing_numbers(self, org):
            client = self.get_valid_client()

            account_numbers = []
            if client:
                status, data = client.get_numbers()

                if status == 200:
                    for number_dict in data['objects']:

                        region = number_dict['region']
                        country_name = region.split(',')[-1].strip().title()
                        country = pycountry.countries.get(name=country_name).alpha2

                        if len(number_dict['number']) <= 6:
                            phone_number = number_dict['number']
                        else:
                            parsed = phonenumbers.parse('+' + number_dict['number'], None)
                            phone_number = phonenumbers.format_number(parsed,
                                                                      phonenumbers.PhoneNumberFormat.INTERNATIONAL)

                        account_numbers.append(dict(number=phone_number, country=country))

            return account_numbers

        def claim_number(self, user, phone_number, country, role):

            auth_id = self.request.session.get(Channel.CONFIG_PLIVO_AUTH_ID, None)
            auth_token = self.request.session.get(Channel.CONFIG_PLIVO_AUTH_TOKEN, None)

            # add this channel
            channel = Channel.add_plivo_channel(user.get_org(),
                                                user,
                                                country,
                                                phone_number,
                                                auth_id,
                                                auth_token)

            analytics.track(user.username, 'temba.channel_claim_plivo', dict(number=phone_number))

            return channel

        def remove_api_credentials_from_session(self):
            if Channel.CONFIG_PLIVO_AUTH_ID in self.request.session:
                del self.request.session[Channel.CONFIG_PLIVO_AUTH_ID]
            if Channel.CONFIG_PLIVO_AUTH_TOKEN in self.request.session:
                del self.request.session[Channel.CONFIG_PLIVO_AUTH_TOKEN]

    class SearchPlivo(SearchNumbers):
        class SearchPlivoForm(forms.Form):
            area_code = forms.CharField(max_length=3, min_length=3, required=False,
                                        help_text=_("The area code you want to search for a new number in"))
            country = forms.ChoiceField(choices=PLIVO_SUPPORTED_COUNTRIES)

        form_class = SearchPlivoForm

        def pre_process(self, *args, **kwargs):  # pragma: needs cover
            client = self.get_valid_client()

            if client:
                return None
            else:
                return HttpResponseRedirect(reverse('channels.channel_claim'))

        def get_valid_client(self):  # pragma: needs cover
            auth_id = self.request.session.get(Channel.CONFIG_PLIVO_AUTH_ID, None)
            auth_token = self.request.session.get(Channel.CONFIG_PLIVO_AUTH_TOKEN, None)

            try:
                client = plivo.RestAPI(auth_id, auth_token)
                validation_response = client.get_account()

                if validation_response[0] != 200:
                    client = None
            except Exception:
                client = None

            return client

        def form_valid(self, form, *args, **kwargs):  # pragma: needs cover
            data = form.cleaned_data
            client = self.get_valid_client()

            results_numbers = []
            try:
                status, response_data = client.search_phone_numbers(dict(country_iso=data['country'], pattern=data['area_code']))

                if status == 200:
                    for number_dict in response_data['objects']:
                        results_numbers.append('+' + number_dict['number'])

                numbers = []
                for number in results_numbers:
                    numbers.append(phonenumbers.format_number(phonenumbers.parse(number, None),
                                                              phonenumbers.PhoneNumberFormat.INTERNATIONAL))
                return JsonResponse(numbers)
            except Exception as e:
                return JsonResponse(dict(error=str(e)))


class ChannelEventCRUDL(SmartCRUDL):
    model = ChannelEvent
    actions = ('calls',)

    class Calls(InboxView):
        title = _("Calls")
        fields = ('contact', 'event_type', 'channel', 'time')
        default_order = '-time'
        search_fields = ('contact__urns__path__icontains', 'contact__name__icontains')
        system_label = SystemLabel.TYPE_CALLS
        select_related = ('contact', 'channel')

        @classmethod
        def derive_url_pattern(cls, path, action):
            return r'^calls/$'

        def get_context_data(self, *args, **kwargs):
            context = super(ChannelEventCRUDL.Calls, self).get_context_data(*args, **kwargs)
            context['actions'] = []
            return context


class ChannelLogCRUDL(SmartCRUDL):
    model = ChannelLog
    actions = ('list', 'read')

    class List(OrgPermsMixin, SmartListView):
        fields = ('channel', 'description', 'created_on')
        link_fields = ('channel', 'description', 'created_on')
        paginate_by = 50

        def derive_queryset(self, **kwargs):
            channel = Channel.objects.get(pk=self.request.GET['channel'])
            events = ChannelLog.objects.filter(channel=channel).order_by('-created_on').select_related('msg__contact', 'msg')

            # monkey patch our queryset for the total count
            events.count = lambda: channel.get_log_count()
            return events

        def get_context_data(self, **kwargs):
            context = super(ChannelLogCRUDL.List, self).get_context_data(**kwargs)
            context['channel'] = Channel.objects.get(pk=self.request.GET['channel'])
            return context

    class Read(ChannelCRUDL.AnonMixin, SmartReadView):
        fields = ('description', 'created_on')

        def derive_queryset(self, **kwargs):
            queryset = super(ChannelLogCRUDL.Read, self).derive_queryset(**kwargs)
            return queryset.filter(channel__org=self.request.user.get_org()).order_by('-created_on')
