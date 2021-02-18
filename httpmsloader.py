import gi
gi.require_version('Soup', '2.4')
import sys

from gi.repository import GObject, GLib, Gio, Soup
from httpmsconfig import plugin_version

USER_AGENT = "HTTPS-Rhythmbox-Plugin/{}".format(plugin_version)


def call_callback(callback, data, args):
    try:
        v = callback(data, *args)
        return v
    except Exception:
        sys.excepthook(*sys.exc_info())


loader_session = None


class Loader(object):
    def __init__(self):
        self.headers = {}
        global loader_session
        if loader_session is None:
            loader_session = Soup.Session()
            loader_session.props.user_agent = USER_AGENT
        self._cancel = Gio.Cancellable()

    def _message_cb(self, session, message, data):
        status = message.props.status_code
        if status == 200:
            call_callback(
                self.callback,
                message.props.response_body_data.get_data(),
                self.args,
            )
        else:
            call_callback(self.callback, None, self.args)

    def set_headers(self, headers):
        self.headers = headers

    def get_url(self, url, callback, *args):
        self.url = url
        self.callback = callback
        self.args = args
        try:
            global loader_session
            req = Soup.Message.new("GET", url)
            for k, v in self.headers.items():
                req.props.request_headers.append(k, v)
            loader_session.queue_message(req, self._message_cb, None)
        except Exception:
            sys.excepthook(*sys.exc_info())
            callback(None, *args)

    def cancel(self):
        self._cancel.cancel()
