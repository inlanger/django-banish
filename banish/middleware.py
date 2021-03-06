# Copyright 2008-2010 Yousef Ourabi

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import sys
import re
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.core.exceptions import MiddlewareNotUsed
from django.core.cache import cache

from models import Banishment 

class BanishMiddleware(object):
    
    """
        middleware init is called once per server on startup - do the heavy lifting here.
    """
    def __init__(self):
        
        # If disabled or not enabled raise MiddleWareNotUsed so django processes next middleware.
        self.ENABLED = getattr(settings, 'BANISH_ENABLED', False)
        self.DEBUG = getattr(settings, 'BANSIH_DEBUG', False)
        self.ABUSE_THRESHOLD = getattr(settings, 'BANSIH_ABUSE_THRESHOLD', 75)
        self.MESSAGE = getattr(settings, 'BANSIH_MESSAGE', 'You are banned.')

        if not self.ENABLED:
            raise MiddleWareNotUsed("django-banish is not enabled via settings.py")

        if self.DEBUG:
            print >> sys.stderr, "[django-banish] status = enabled"

        # Prefix All keys in cache to avoid key collisions
        self.BANISH_PREFIX = 'DJANGO_BANISH:'
        self.ABUSE_PREFIX = 'DJANGO_BANISH_ABUSE:'

        self.BANNED_AGENTS = []

        # Populate various 'banish' buckets
        for ban in Banishment.objects.all():
            print >> sys.stderr, "IP BANISHMETN: ", ban.type
            
            if ban.type == 'ip-address':
                cache_key = self.BANISH_PREFIX + ban.condition
                cache.set(cache_key, "1")

            if ban.type == 'user-agent':
                self.BANNED_USER_AGENTS.append(ban.condition)

    
    # To Handle X_FORWARDED_FOR, use SetRemoteAddrFromForwardedFor MiddleWare
    def process_request(self, request):
        ip = request.META['REMOTE_ADDR']
        user_agent = request.META['HTTP_USER_AGENT']

        if self.DEBUG:
            print >> sys.stderr, "GOT IP FROM Request: %s and User Agent %s" % (ip, user_agent)
       
        # Check ban conditions
        if self.is_banned(ip) or self.monitor_abuse(ip) or user_agent in self.BANNED_AGENTS:
            return HttpResponseForbidden(self.MESSAGE, mimetype="text/html")

    def is_banned(self, ip):
        """
            If a key BANISH MC key exists we know the user is banned.
        """
        is_banned = cache.get(self.BANISH_PREFIX + ip)
        return is_banned


    def monitor_abuse(self, ip):
        """
            Track the number of hits per second for a given IP
            If the count is over ABUSE_THRESHOLD banish user
        """
        cache_key = self.ABUSE_PREFIX + ip
        abuse_count = cache.get(cache_key)
        print >> sys.stderr, "ABUSE COUNT: ", abuse_count

        over_abuse_limit = False

        if not abuse_count:
            cache.set(cache_key, 1, 60)
        else:
            if abuse_count >= self.ABUSE_THRESHOLD:
                over_abuse_limit = True
                
                # Store IP Abuse in memcache and database
                ban = Banishment (
                    ban_reason = "IP Abuse limit exceeded",
                    type = "ip-address",
                    condition = ip,
                )
                ban.save()
                cache.set(self.BANISH_PREFIX + ip, "1")

            cache.incr(cache_key)
        
        return over_abuse_limit
