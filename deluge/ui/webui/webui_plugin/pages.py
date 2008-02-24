#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# deluge_webserver.py
#
# Copyright (C) Martijn Voncken 2007 <mvoncken@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, write to:
#     The Free Software Foundation, Inc.,
#     51 Franklin Street, Fifth Floor
#     Boston, MA  02110-1301, USA.
#
#  In addition, as a special exception, the copyright holders give
#  permission to link the code of portions of this program with the OpenSSL
#  library.
#  You must obey the GNU General Public License in all respects for all of
#  the code used other than OpenSSL. If you modify file(s) with this
#  exception, you may extend this exception to your version of the file(s),
#  but you are not obligated to do so. If you do not wish to do so, delete
#  this exception statement from your version. If you delete this exception
#  statement from all source files in the program, then also delete it here.
#
from webserver_common import ws, proxy, log
from utils import *
from render import render, error_page
import page_decorators as deco
import config_tabs_webui #auto registers
import config_tabs_deluge #auto registers
from config import config_page
from torrent_options import torrent_options
from torrent_move import torrent_move
#import forms
#
from debugerror import deluge_debugerror
web.webapi.internalerror = deluge_debugerror
#

import lib.webpy022 as web
from lib.webpy022.http import seeother, url
from lib.static_handler import static_handler


from operator import attrgetter
import os

from json_api import json_api

#special/complex pages:
from torrent_add import torrent_add

#routing:
urls = (
    "/login", "login",
    "/index", "index",
    "/torrent/info/(.*)", "torrent_info",
    "/torrent/info_inner/(.*)", "torrent_info_inner",
    "/torrent/stop/(.*)", "torrent_stop",
    "/torrent/start/(.*)", "torrent_start",
    "/torrent/reannounce/(.*)", "torrent_reannounce",
    "/torrent/recheck/(.*)", "torrent_recheck",
    "/torrent/add(.*)", "torrent_add",
    "/torrent/delete/(.*)", "torrent_delete",
    "/torrent/move/(.*)", "torrent_move",
    "/torrent/queue/up/(.*)", "torrent_queue_up",
    "/torrent/queue/down/(.*)", "torrent_queue_down",
    "/torrent/files/(.*)","torrent_files",
    "/torrent/options/(.*)","torrent_options",
    "/pause_all", "pause_all",
    "/resume_all", "resume_all",
    "/refresh/set", "refresh_set",
    "/refresh/(.*)", "refresh",
    "/config/(.*)", "config_page",
    "/home", "home",
    "/about", "about",
    "/logout", "logout",
    "/connect","connect",
    #remote-api:
    "/remote/torrent/add(.*)", "remote_torrent_add",
    "/json/(.*)","json_api",
    #static:
    "/static/(.*)", "static",
    "/template/static/(.*)", "template_static",
    #"/downloads/(.*)","downloads" disabled until it can handle large downloads
    #default-pages
    "/", "home",
    "", "home",
    "/robots.txt","robots"
)
#/routing

#pages:
class login:
    @deco.deluge_page_noauth
    def GET(self, name):
        vars = web.input(error = None)
        return render.login(vars.error)

    def POST(self):
        vars = web.input(pwd = None, redir = None)

        if ws.check_pwd(vars.pwd):
            #start new session
            start_session()
            do_redirect()
        elif vars.redir:
            seeother(url('/login', error=1, redir=vars.redir))
        else:
            seeother('/login?error=1')

class index:
    "page containing the torrent list."
    @deco.deluge_page
    @deco.auto_refreshed
    def GET(self, name):
        vars = web.input(sort=None, order=None ,filter=None , category=None)

        torrent_list = get_torrent_list()
        all_torrents = torrent_list[:]

        #filter-state
        if vars.filter:
            torrent_list = filter_torrent_state(torrent_list, vars.filter)
            setcookie("filter", vars.filter)
        else:
            setcookie("filter", "")

        #filter-cat
        if vars.category:
            torrent_list = [t for t in torrent_list if t.category == vars.category]
            setcookie("category", vars.category)
        else:
            setcookie("category", "")

        #sorting:
        if vars.sort:
            torrent_list.sort(key=attrgetter(vars.sort))
            if vars.order == 'up':
                torrent_list = reversed(torrent_list)

            setcookie("order", vars.order)
            setcookie("sort", vars.sort)

        return render.index(torrent_list, all_torrents)

class torrent_info:
    @deco.deluge_page
    @deco.auto_refreshed
    @deco.torrent
    def GET(self, torrent):
        return render.torrent_info(torrent)

class torrent_info_inner:
    @deco.deluge_page
    @deco.torrent
    def GET(self, torrent):
        vars = web.input(tab = None)
        if vars.tab:
            active_tab = vars.tab
        else:
            active_tab =  getcookie("torrent_info_tab") or "details"
        setcookie("torrent_info_tab", active_tab)
        return render.torrent_info_inner(torrent, active_tab)

#next 4 classes: a pattern is emerging here.
#todo: DRY (in less lines of code)
#deco.deluge_command, or a subclass?
class torrent_start:
    @deco.check_session
    @deco.torrent_ids
    def POST(self, torrent_ids):
        proxy.resume_torrent(torrent_ids)
        do_redirect()

class torrent_stop:
    @deco.check_session
    @deco.torrent_ids
    def POST(self, torrent_ids):
        proxy.pause_torrent(torrent_ids)
        do_redirect()

class torrent_reannounce:
    @deco.check_session
    @deco.torrent_ids
    def POST(self, torrent_ids):
        proxy.force_reannounce(torrent_ids)
        do_redirect()

class torrent_recheck:
    @deco.check_session
    @deco.torrent_ids
    def POST(self, torrent_ids):
        proxy.force_recheck(torrent_ids)
        do_redirect()

class torrent_delete:
    @deco.deluge_page
    @deco.torrent_list
    def GET(self, torrent_list):
            torrent_str = ",".join([t.id for t in torrent_list])
            #todo: remove the ",".join!
            return render.torrent_delete(torrent_str, torrent_list)

    @deco.check_session
    @deco.torrent_ids
    def POST(self, torrent_ids):
        vars = web.input(data_also = None, torrent_also = None)
        data_also = bool(vars.data_also)
        torrent_also = bool(vars.torrent_also)
        proxy.remove_torrent(torrent_ids, torrent_also, data_also)
        do_redirect()

class torrent_queue_up:
    @deco.check_session
    @deco.torrent_list
    def POST(self, torrent_list):
        return error_page('Queue is broken, we know about it.')
        #a bit too verbose..
        torrent_list.sort(lambda x, y : x.queue - y.queue)
        torrent_ids = [t.id for t in torrent_list]
        for torrent_id in torrent_ids:
            #async_proxy.get_core().call("queue_queue_up", None, torrent_id)
            async_proxy.queue_queue_up(None, torrent_id)
        do_redirect()

class torrent_queue_down:
    @deco.check_session
    @deco.torrent_list
    def POST(self, torrent_list):
        return error_page('Queue is broken, we know about it.')
        #a bit too verbose..
        torrent_list.sort(lambda x, y : x.queue - y.queue)
        torrent_ids = [t.id for t in torrent_list]
        for torrent_id in reversed(torrent_ids):
            #async_proxy.get_core().call("queue_queue_down", None, torrent_id)
            async_proxy.queue_queue_down(None, torrent_id)
        do_redirect()

class torrent_files:
    @deco.check_session
    def POST(self, torrent_id):
        torrent = get_torrent_status(torrent_id)
        file_priorities = web.input(file_priorities=[]).file_priorities
        #file_priorities contains something like ['0','2','3','4']
        #transform to: [1,0,0,1,1,1]
        proxy_prio = [0 for x in xrange(len(torrent.file_priorities))]
        for pos in file_priorities:
            proxy_prio[int(pos)] = 1

        proxy.set_torrent_file_priorities(torrent_id, proxy_prio)
        do_redirect()

class pause_all:
    @deco.check_session
    def POST(self, name):
        proxy.pause_torrent(proxy.get_session_state())
        do_redirect()

class resume_all:
    @deco.check_session
    def POST(self, name):
        proxy.resume_torrent(proxy.get_session_state())
        do_redirect()

class refresh:
    def GET(self, name):
        return self.POST(name)
        #WRONG, but makes it easyer to link with <a href> in the status-bar

    @deco.check_session
    def POST(self, name):
        auto_refresh = {'off': '0', 'on': '1'}[name]
        setcookie('auto_refresh', auto_refresh)
        if not getcookie('auto_refresh_secs'):
            setcookie('auto_refresh_secs', 10)
        do_redirect()

class refresh_set:
    @deco.deluge_page
    def GET(self, name):
        return render.refresh_form()

    @deco.check_session
    def POST(self, name):
        vars = web.input(refresh = 0)
        refresh = int(vars.refresh)
        if refresh > 0:
            setcookie('auto_refresh', '1')
            setcookie('auto_refresh_secs', str(refresh))
            do_redirect()
        else:
            error_page(_('refresh must be > 0'))

class home:
    @deco.check_session
    def GET(self, name):
        do_redirect()

class about:
    @deco.deluge_page_noauth
    def GET(self, name):
        return render.about()

class logout:
    def GET(self):
        return self.POST()
        #WRONG, but makes it easyer to link with <a href> in the status-bar
    @deco.check_session
    def POST(self, name):
        end_session()
        seeother('/login')

class connect:
    @deco.check_session
    @deco.deluge_page_noauth
    def GET(self, name):
        if proxy.connected():
               error = _("Not Connected to a daemon")
        else:
            error = None
        connect_list = ["http://localhost:58846"]
        return render.connect(connect_list, error)

    def POST(self):
        vars = web.input(uri = None, other_uri = None)
        uri = ''
        if vars.uri == 'other_uri':
            if not vars.other:
                return error_page(_("no uri"))
            url = vars.other
        else:
            uri = vars.uri
        #TODO: more error-handling
        proxy.set_core_uri(uri)
        do_redirect()


#other stuff:
class remote_torrent_add:
    """
    For use in remote scripts etc.
    curl ->POST pwd and torrent as file
    greasemonkey: POST pwd torrent_name and data_b64
    """
    @deco.remote
    def POST(self, name):
        vars = web.input(pwd = None, torrent = {},
            data_b64 = None , torrent_name= None)

        if not ws.check_pwd(vars.pwd):
            return 'error:wrong password'

        if vars.data_b64: #b64 post (greasemonkey)
            data_b64 = unicode(vars.data_b64)
            torrent_name = vars.torrent_name
        else:  #file-post (curl)
            data_b64 = base64.b64encode(vars.torrent.file.read())
            torrent_name = vars.torrent.filename
        proxy.add_torrent_filecontent(torrent_name, data_b64)
        return 'ok'

class static(static_handler):
    base_dir = os.path.join(os.path.dirname(__file__), 'static')

class template_static(static_handler):
    def get_base_dir(self):
        return os.path.join(os.path.dirname(__file__),
                'templates/%s/static' % ws.config.get('template'))

class downloads(static_handler):
    def GET(self, name):
        self.base_dir = proxy.get_config_value('default_download_path')
        if not ws.config.get('share_downloads'):
            raise Exception('Access to downloads is forbidden.')
        return static_handler.GET(self, name)

class robots:
    def GET(self):
        "no robots/prevent searchengines from indexing"
        web.header("Content-Type", "text/plain")
        print "User-agent: *\nDisallow:/\n"

#/pages

