import gi
gi.require_version('Soup', '3.0')
import sys

from gi.repository import GObject, GLib, Gio, Soup
from httpmsconfig import plugin_version

USER_AGENT = "Euterpe-Rhythmbox-Plugin/{}".format(plugin_version)


def call_callback(callback, status, data, args):
    try:
        v = callback(status, data, *args)
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

    def _message_cb(self, source, result, data):
        message = source.get_async_result_message(result)
        status = message.get_status()
        if status >= 200 and status <= 299:
            call_callback(
                self.callback,
                status,
                source.send_and_read_finish(result).get_data(),
                data,
            )
        else:
            call_callback(self.callback, status, None, data)

    def set_headers(self, headers):
        self.headers = headers

    def get_url(self, url, callback, *args):
        self.url = url
        self.callback = callback
        try:
            global loader_session
            req = Soup.Message.new("GET", url)
            for k, v in self.headers.items():
                req.props.request_headers.append(k, v)
            loader_session.send_and_read_async(
                req,
                Soup.MessagePriority.NORMAL,
                self._cancel,
                self._message_cb,
                args,
            )
        except Exception:
            sys.excepthook(*sys.exc_info())
            callback(None, *args)

    def post_url(self, url, callback, content_type, body, *args):
        self.url = url
        self.callback = callback
        try:
            global loader_session
            req = Soup.Message.new("POST", url)
            for k, v in self.headers.items():
                req.props.request_headers.append(k, v)
            req.set_request_body_from_bytes(content_type, GLib.Bytes.new(body))
            loader_session.send_and_read_async(
                req,
                Soup.MessagePriority.NORMAL,
                self._cancel,
                self._message_cb,
                args,
            )
        except Exception:
            sys.excepthook(*sys.exc_info())
            callback(None, None, *args)

    def cancel(self):
        self._cancel.cancel()
