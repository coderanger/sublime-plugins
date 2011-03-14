import sublime
import sublime_plugin
import multiprocessing.connection
import os
import sys
import threading
import time


def walk_back_path(path):
    yield path
    while 1:
        last = path
        path = os.path.dirname(path)
        if last == path:
            break
        yield path


class PyZenThread(threading.Thread):
    def __init__(self):
        super(PyZenThread, self).__init__()
        self.daemon = True
        self.view_lock = threading.Lock()
        self.quit_lock = threading.Lock()
        self.views = {}
        self.status = {}
        self._quit = False
        self.status_setter()

    def run(self):
        self.write_pidfile()
        for i in xrange(10):
            with self.quit_lock:
                if self._quit:
                    return
            try:
                listener = multiprocessing.connection.Listener('/tmp/.sublimepyzen.%s'%os.getpid())
            except Exception, e:
                time.sleep(1)
            else:
                break
        else:
            print e
            return
        while 1:
            with self.quit_lock:
                if self._quit:
                    listener.close()
                    return
            conn = listener.accept()
            base_path, info = conn.recv()
            conn.close()
            if base_path == 'QUIT' or base_path == 'PING':
                continue
            with self.view_lock:
                self.status[base_path] = info

    def add_view(self, view):
        with self.view_lock:
            self.views[view.id()] = view

    def remove_view(self, view):
        with self.view_lock:
            if view.id() in self.views:
                del self.views[view.id()]

    def quit(self):
        with self.quit_lock:
            self._quit = True
        try:
            client = multiprocessing.connection.Client('/tmp/.sublimepyzen.%s'%os.getpid())
            client.send(['QUIT', None])
            client.close()
        except Exception:
            pass

    def write_pidfile(self):
        if sys.platform == 'darwin':
            base_path = os.path.join(os.environ['HOME'], 'Library', 'Application Support', 'Sublime Text 2')
        pid_path = os.path.join(base_path, 'sublime2.pid')
        pid_file = open(pid_path, 'w')
        pid_file.write('%s\n'%os.getpid())
        pid_file.close()

    def status_setter(self):
        with self.view_lock:
            for vid, view in self.views.iteritems():
                view_file = view.file_name()
                if not view_file:
                    continue
                for path in walk_back_path(view_file):
                    s = self.status.get(path)
                    if s is None:
                        continue
                    view.set_status('pyzen', s[2])
                    break
                else:
                    view.erase_status('pyzen')
        sublime.set_timeout(self.status_setter, 1000)


class pyzen(sublime_plugin.EventListener):
    def __init__(self, *args, **kwargs):
        sublime_plugin.EventListener.__init__(self, *args, **kwargs)
        self.thread = PyZenThread()
        self.thread.start()

    def __del__(self):
        if hasattr(self, 'thread') and self.thread and self.thread.is_alive():
            self.thread.quit()
            self.thread.join()

    def on_load(self, view):
        self.thread.add_view(view)

    def on_new(self, view):
        self.thread.add_view(view)

    def on_close(self, view):
        self.thread.remove_view(view)
