#!/usr/bin/env python3

import json
import gettext
import urllib.parse
import os.path

import rb
from gi.repository import GObject, RB, Peas, GLib, Gtk, GdkPixbuf

gettext.install('rhythmbox', RB.locale_dir())

# Change this once I find out how to create a "settings" dialog for the plugin
HARD_CODED_SERVER_ADDRESS = 'http://httpms.example.com/'


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

    def get_playback_uri(self, entry):
        playback_url = entry.get_string(RB.RhythmDBPropType.MOUNTPOINT)
        print('Returning playback uri: {}'.format(playback_url))
        return playback_url


class HTTPMSSource(RB.BrowserSource):
    def __init__(self, **kwargs):
        RB.BrowserSource.__init__(self, **kwargs)
        self.loader = None
        self.selected = False
        self.search_count = 1
        self.base = HARD_CODED_SERVER_ADDRESS

    def do_selected(self):
        if self.selected:
            return
        self.selected = True
        self.setup()

    def cancel_request(self):
        if self.loader:
            self.loader.cancel()
            self.loader = None

    def do_search(self, arg1, arg2, term):
        '''
        Honestly I have no idea what arg1 and arg2 are.
        '''

        self.cancel_request()
        self.new_model()

        search_url = urllib.parse.urljoin(self.base, '/search/')

        print("Searching for {}".format(term))

        url = urllib.parse.urljoin(search_url, urllib.parse.quote(term))
        self.loader = rb.Loader()
        self.loader.get_url(url, self.search_tracks_api)

    def search_tracks_api(self, data):
        if data is None:
            print("No data in search_tracks_api callback")
            return

        shell = self.props.shell
        db = shell.props.db
        entry_type = self.props.entry_type

        data = data.decode('utf-8')
        stuff = json.loads(data)

        db.entry_delete_by_type(entry_type)
        db.commit()

        for item in stuff:
            self.add_track(db, entry_type, item)

    def setup(self):
        print("Running the setup")

    def add_track(self, db, entry_type, item):

        uri = urllib.parse.urljoin(self.base, '/file/')
        uri = urllib.parse.urljoin(uri, '{}'.format(item['id']))

        entry = db.entry_lookup_by_location(uri)
        if entry:
            db.entry_set(
                entry,
                RB.RhythmDBPropType.LAST_SEEN,
                self.search_count,
            )
        else:
            entry = RB.RhythmDBEntry.new(db, entry_type, uri)
            db.entry_set(entry, RB.RhythmDBPropType.MOUNTPOINT, uri)
            db.entry_set(entry, RB.RhythmDBPropType.ARTIST, item['artist'])
            db.entry_set(entry, RB.RhythmDBPropType.TITLE, item['title'])
            db.entry_set(entry, RB.RhythmDBPropType.ALBUM, item['album'])
            db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, item['track'])
            db.entry_set(entry, RB.RhythmDBPropType.LAST_SEEN, self.search_count)

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
        model = RB.RhythmDBQueryModel.new_empty(db)

        db.do_full_query_async_parsed(model, q)
        self.props.query_model = model


GObject.type_register(HTTPMSSource)
