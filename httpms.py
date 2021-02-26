#!/usr/bin/env python3

import json
import gettext
import urllib.parse
import os.path
import base64

from httpmsloader import Loader
from gi.repository import GObject, RB, Peas, GLib, Gtk, GdkPixbuf

gettext.install('rhythmbox', RB.locale_dir())


class HTTPMSPlugin(GObject.Object, Peas.Activatable):
    object = GObject.property(type=GObject.Object)

    def __init__(self):
        super(HTTPMSPlugin, self).__init__()

    def do_activate(self):
        print("Activating HTTPMS plugin")

        shell = self.object
        db = shell.props.db
        entry_type = HTTPMSEntryType()
        db.register_entry_type(entry_type)

        model = RB.RhythmDBQueryModel.new_empty(db)
        self.source = GObject.new(HTTPMSSource,
                                  shell=shell,
                                  name=("HTTPMS"),
                                  plugin=self,
                                  query_model=model,
                                  entry_type=entry_type)

        self.icon = None
        icon_path = os.path.join(
            Peas.PluginInfo.get_module_dir(self.plugin_info),
            "assets",
            "icon-128.png",
        )
        if icon_path is not None:
            _, width, height = Gtk.IconSize.lookup(Gtk.IconSize.LARGE_TOOLBAR)
            icon = GdkPixbuf.Pixbuf.new_from_file_at_size(
                icon_path,
                width,
                height,
            )
            self.source.set_property("icon", icon)
            self.icon = icon

        group = RB.DisplayPageGroup.get_by_id("shared")
        shell.append_display_page(self.source, group)
        shell.register_entry_type_for_source(self.source, entry_type)

    def do_deactivate(self):
        print("Deactivating HTTPMS plugin")

        self.source.delete_thyself()
        del self.source

        del self.icon


class HTTPMSEntryType(RB.RhythmDBEntryType):
    def __init__(self):
        RB.RhythmDBEntryType.__init__(self, name='httpms-entry')

    def do_can_sync_metadata(self, entry):
        return False

    def do_get_playback_uri(self, entry):
        return entry.get_string(RB.RhythmDBPropType.MOUNTPOINT)


class HTTPMSSource(RB.BrowserSource):
    def __init__(self, **kwargs):
        RB.BrowserSource.__init__(self, **kwargs)
        self.loader = None
        self.selected = False
        self.search_count = 1
        self.logged_in = False

    def use_auth(self, address, username="", password=""):
        '''
        Stores the address, username and password in the plugin's memory for
        use when API or song requests are made to the HTTPMS server. username
        and password may be empty strings.
        '''
        self.address_base = address
        self.address_with_auth = address
        self.auth_headers = {}

        if len(username) > 0:
            self.address_with_auth = self.get_address_with_basicauth_in_host(
                address,
                username,
                password,
            )

            self.auth_headers["Authorization"] = self.get_basic_auth_header(
                username,
                password,
            )

        self.logged_in = True

    def get_address_with_basicauth_in_host(self, address, username, password):
        '''
        Inserts the username and password into the address hostname. For
        HTTP basic authentication. And returns the result.
        '''
        up = urllib.parse.urlparse(address)
        hostwithauth = "{}:{}@{}".format(
            urllib.parse.quote(username, safe=''),
            urllib.parse.quote(password, safe=''),
            up.netloc,
        )
        up = up._replace(netloc=hostwithauth)
        return up.geturl()

    def get_basic_auth_header(self, username, password):
        '''
        Returns the HTTP Basic Authentication header for the given username
        and password.
        '''
        return "Basic {}".format(
            base64.b64encode(
                "{}:{}".format(username, password).encode('utf-8'),
            ).decode('ascii')
        )

    def do_selected(self):
        '''
        Executed when the HTTPMS plugin is selected in the Rhythmbox plugin
        list.
        '''
        if self.selected:
            return
        self.selected = True
        self.setup()

    def cancel_request(self):
        '''
        Cancels any ongoing request to the server REST API for getting
        songs meta data.
        '''
        if self.loader:
            print("Cancelling ongoing search")
            self.loader.cancel()
            self.loader = None

    def search_tracks_api(self, data):
        '''
        This functions loads 'data' into the source's database. The data is
        assumed to be a JSON with a list of tracks. It must be a list of
        tracks like the one returned from searching into the HTTPMS via its
        REST API.
        '''
        if data is None:
            print("No data in search_tracks_api callback")
            return

        shell = self.props.shell
        db = shell.props.db
        entry_type = self.props.entry_type

        data = data.decode('utf-8')
        try:
            stuff = json.loads(data)
        except Exception as err:
            print('Error decoding server response: {}'.format(err))
            return

        db.entry_delete_by_type(entry_type)
        db.commit()

        for item in stuff:
            self.add_track(db, entry_type, item)

        self.props.load_status = RB.SourceLoadStatus.LOADED

    def setup(self):
        '''
        This function loads the plugin initial view. It is responsible
        for setting up its GTK widgets, loading its data from the plugin's
        data file and generally setting up its state. At the end of
        this function the plugin should be usable.
        '''

        print("Running the setup")

        self.saved_entry_view = self.get_entry_view()
        self.props.show_browser = True
        self.saved_entry_view.props.sort_order = "Track,ascending"

        for child in self.get_children():
            self.grid = child

        self.fix_browser_size()
        self.add_menu_buttons()

        self.builder = Gtk.Builder()

        ui_file = os.path.join(
            Peas.PluginInfo.get_module_dir(self.props.plugin.plugin_info),
            "httpms-rhythmbox.glade",
        )

        self.builder.add_from_file(ui_file)
        self.builder.connect_signals(self)

        self.login_win = self.builder.get_object("login_scroll_view")
        self.pack_start(self.login_win, expand=True, fill=True, padding=0)
        self.reorder_child(self.login_win, 0)

        self.login_spinner = self.builder.get_object("login_spinner")
        self.failed_indicator = self.builder.get_object(
            "login_failed_indicator",
        )
        self.login_entry_address = self.builder.get_object("server_url")
        self.login_entry_user = self.builder.get_object("service_username")
        self.login_entry_pass = self.builder.get_object("service_password")
        self.login_button = self.builder.get_object("login_button")

        self.login_win.show()
        self.load_auth_data()

        if self.user_logged_in():
            self.load_upstream_data()
        else:
            self.show_login_screen()

        self.bind_settings_dynamic()

        self.art_store = RB.ExtDB(name="album-art")
        shell = self.props.shell
        player = shell.props.shell_player
        player.connect('playing-song-changed', self.playing_entry_changed_cb)

    def fix_browser_size(self):
        '''
        For whatever reason the Gtk.Panel divider by default is way too
        close to the top element. WHich is the browser for albums
        and artists. And its position is not remembered between runs.
        So on setup we set it to a more reasonable value here.
        '''
        for gch in self.grid.get_children():
            if not isinstance(gch, Gtk.Paned):
                continue
            gch.set_position(200)
            break

    def bind_settings_dynamic(self):
        '''
        This method finds the Gtk.Paned and Rb.LibraryBrowser from the source
        children tree and binds their settings.
        '''
        paned = None
        browser = None

        for gch in self.grid.get_children():
            if not isinstance(gch, Gtk.Paned):
                continue
            paned = gch
            for pch in paned.get_children():
                if not isinstance(pch, RB.LibraryBrowser):
                    continue
                browser = pch
                break
            break

        print('Binding settings')
        self.bind_settings(
            self.saved_entry_view,
            paned,
            browser,
            True,
        )

    def add_menu_buttons(self):
        '''
        Adds the Sync and Logout buttons to the source menu, next to the
        search bar.
        '''
        source_toolbar = None
        for gch in self.grid.get_children():
            if isinstance(gch, RB.SourceToolbar):
                source_toolbar = gch
                break

        if source_toolbar is None:
            print('Unable to add menu buttons: RB.SourceToolbar was not found')
            return

        toolbar = None
        for tch in source_toolbar.get_children():
            if isinstance(tch, Gtk.Toolbar):
                toolbar = tch
                break

        if toolbar is None:
            print('Unable to add menu buttons: Gtk.Toolbar was not found')
            return

        logout = Gtk.ToolButton.new(None, "Logout")
        sync = Gtk.ToolButton.new(None, "Sync")
        sync.connect('clicked', self.sync_clicked_cb)
        logout.connect('clicked', self.logout_clicked_cb)

        toolbar.add(sync)
        toolbar.add(logout)

        logout.show()
        sync.show()

    def sync_clicked_cb(self, btn):
        '''
        Executed when the "Sync" button in clicked. This method clears the
        source database and makes a request for the latest data from the
        server.
        '''
        self.load_upstream_data()

    def logout_clicked_cb(self, btn):
        '''
        Executed when the logout button is pressed. The method clears the
        source database, removes the stored credentials and shows the login
        page.
        '''
        self.store_auth_data("", "", "")
        self.logged_in = False
        self.login_entry_address.set_text("")
        self.builder.get_object("service_username").set_text("")
        self.builder.get_object("service_password").set_text("")

        self.show_login_screen()

        db = self.props.shell.props.db
        entry_type = self.props.entry_type
        db.entry_delete_by_type(entry_type)
        db.commit()

    def show_login_screen(self):
        '''
        Hides the browser and entry list view. In their place shows the
        login screen.
        '''
        self.login_win.show()
        self.grid.hide()

    def load_upstream_data(self):
        '''
        Makes a request to the upstream server and gets all the data for
        tracks. Then loads them into the source's database.
        '''
        self.login_win.hide()
        self.props.load_status = RB.SourceLoadStatus.LOADING
        self.new_model()

        self.cancel_request()
        search_url = urllib.parse.urljoin(self.address_base, '/search/')
        print("Loading HTTPMS into the database")
        self.loader = Loader()
        self.loader.set_headers(self.auth_headers)
        self.loader.get_url(search_url, self.search_tracks_api)

    def add_track(self, db, entry_type, item):
        '''
        Adds this track to the source's database.
        '''

        # track_url is the canonical unique URL for this track.
        track_url = urllib.parse.urljoin(
            self.address_base,
            '/file/{}'.format(item['id']),
        )

        # play_url is the URL at which this track can be loaded.
        # Sometimes this can be different from track_url. For
        # example when the URL includes a token or basic auth.
        play_url = urllib.parse.urljoin(
            self.address_with_auth,
            '/file/{}'.format(item['id']),
        )

        album_url = urllib.parse.urljoin(
            self.address_with_auth,
            '/album/{}/artwork'.format(item['album_id']),
        )

        entry = db.entry_lookup_by_location(track_url)
        if entry:
            db.entry_set(
                entry,
                RB.RhythmDBPropType.LAST_SEEN,
                self.search_count,
            )
        else:
            entry = RB.RhythmDBEntry.new(db, entry_type, track_url)
            db.entry_set(entry, RB.RhythmDBPropType.MOUNTPOINT, play_url)
            db.entry_set(entry, RB.RhythmDBPropType.ARTIST, item['artist'])
            db.entry_set(entry, RB.RhythmDBPropType.TITLE, item['title'])
            db.entry_set(entry, RB.RhythmDBPropType.ALBUM, item['album'])
            db.entry_set(entry, RB.RhythmDBPropType.ALBUM_SORT_KEY,
                         item['album_id'])
            db.entry_set(entry, RB.RhythmDBPropType.COMMENT,
                         'Album {}'.format(item['album_id']))
            db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER,
                         item['track'])
            db.entry_set(entry, RB.RhythmDBPropType.MB_ALBUMID,
                         album_url)
            db.entry_set(entry, RB.RhythmDBPropType.LAST_SEEN,
                         self.search_count)

        db.commit()

    def new_model(self):
        shell = self.props.shell
        entry_type = self.props.entry_type
        db = shell.props.db

        self.search_count = self.search_count + 1
        q = GLib.PtrArray()
        db.query_append_params(q, RB.RhythmDBQueryType.EQUALS,
                               RB.RhythmDBPropType.TYPE, entry_type)
        db.query_append_params(
            q,
            RB.RhythmDBQueryType.EQUALS,
            RB.RhythmDBPropType.LAST_SEEN,
            self.search_count,
        )
        model = RB.RhythmDBQueryModel.new_for_entry_type(db, entry_type, False)

        db.do_full_query_async_parsed(model, q)
        self.props.query_model = model

    def playing_entry_changed_cb(self, player, entry):
        '''
        playing_entry_changed_cb changes the album artwork on every
        track change.
        '''
        if not entry:
            return
        if entry.get_entry_type() != self.props.entry_type:
            return

        au = entry.get_string(RB.RhythmDBPropType.MB_ALBUMID)
        if au:
            key = RB.ExtDBKey.create_storage(
                "title", entry.get_string(RB.RhythmDBPropType.TITLE))
            key.add_field("artist", entry.get_string(
                RB.RhythmDBPropType.ARTIST))
            key.add_field("album", entry.get_string(
                RB.RhythmDBPropType.ALBUM))
            self.art_store.store_uri(key, RB.ExtDBSourceType.EMBEDDED, au)

    def login_button_clicked_cb(self, data):
        '''
        This function is bound to the login button. It uses the data from
        the entry fields and tries them with the remote server. If the
        request is successful then it stores them into the plugin settings
        and shows the browser and entry list instead of the login form.
        '''
        self.try_url = self.login_entry_address.get_text().strip()
        self.try_username = self.login_entry_user.get_text().strip()
        self.try_password = self.login_entry_pass.get_text()

        if self.try_url == "":
            print('Empty URL is not accepted')
            return

        if not self.try_url.startswith("http://") or \
                not self.try_url.startswith("https://"):
            self.try_url = 'https://{}'.format(self.try_url)

        self.login_entry_address.set_sensitive(False)
        self.login_entry_user.set_sensitive(False)
        self.login_entry_pass.set_sensitive(False)
        self.login_button.set_sensitive(False)
        self.login_spinner.props.active = True
        self.failed_indicator.hide()

        try_url = urllib.parse.urljoin(self.try_url, '/search/')
        try_url += '?=absolutelynotthereonehundredpercent'

        loader = Loader()
        loader.set_headers({
            "Authorization": self.get_basic_auth_header(
                self.try_username,
                self.try_password,
            )
        })
        loader.get_url(try_url, self.try_auth_credentials_callback)

    def try_auth_credentials_callback(self, data):
        '''
        This callback is called from the request which tries the server
        address and auth credentials. If they are OK data will not be a
        None. In this case the credentials are stored and the server data
        is loaded into the source's database.

        If the credentials are not OK then the login form is made active
        again so that the user can other address/credentials.
        '''
        self.login_entry_address.set_sensitive(True)
        self.login_entry_user.set_sensitive(True)
        self.login_entry_pass.set_sensitive(True)
        self.login_button.set_sensitive(True)
        self.login_spinner.props.active = False

        if data is None:
            print("Authentication unsuccessful")
            self.failed_indicator.show()
            del self.try_url
            del self.try_username
            del self.try_password
            return

        self.use_auth(self.try_url, self.try_username, self.try_password)
        self.store_auth_data(
            self.try_url,
            self.try_username,
            self.try_password,
        )

        del self.try_url
        del self.try_username
        del self.try_password

        self.load_upstream_data()
        self.grid.show()

    def user_logged_in(self):
        '''
        Returns true if there is an active server address and possibly auth
        credentials stored in the source's memory.
        '''
        return self.logged_in

    def load_auth_data(self):
        '''
        Reads the plugin data file and tries to load its content into the
        source's memory. It looks for server address and credentials.
        '''
        file_name = self.key_file_name()
        if file_name is None:
            print('Could not load the user data directory')
            return

        kf = GLib.KeyFile.new()

        loaded = False
        try:
            loaded = kf.load_from_file(file_name, GLib.KeyFileFlags.NONE)
        except GLib.Error as err:
            print('Loading auth file error: {}'.format(err))

        if not loaded:
            return

        try:
            address = kf.get_string("auth", "address")
            username = kf.get_string("auth", "username")
            password = kf.get_string("auth", "password")
            if len(address) > 0:
                self.use_auth(address, username, password)
        except GLib.Error as err:
            print('Reading auth file error: {}'.format(err))

    def store_auth_data(self, address, username, password):
        '''
        Stores the provided server address and auth credentials in the
        plugin's data file.
        '''
        file_name = self.key_file_name()
        if file_name is None:
            print('Could not load the user data directory')
            return

        kf = GLib.KeyFile.new()
        kf.set_string("auth", "address", address)
        kf.set_string("auth", "username", username)
        kf.set_string("auth", "password", password)

        try:
            kf.save_to_file(file_name)
        except GLib.Error as err:
            print('Saving auth data to file: {}'.format(err))

    def key_file_name(self):
        '''
        Returns the name (on the file system) of the plugin's data
        file. This file is used to store settings between different
        runs of the plugin.
        '''
        data_dir = RB.user_data_dir()
        if data_dir is None:
            return None

        return os.path.join(data_dir, "httpms.auth")


GObject.type_register(HTTPMSSource)
