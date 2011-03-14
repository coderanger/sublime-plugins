import itertools
import sublime
import sublime_plugin
import os
import subprocess
import threading
import time

def remove_longest_substring(s1, s2):
    for i, (c1, c2) in enumerate(itertools.izip_longest(s1, s2)):
        if c1 != c2:
            return s1[i:]
    return ''


def run_git_cmd(path, *args):
    proc = subprocess.Popen(['git']+list(args), cwd=path, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode != 0:
        return ''
    return out


def git_branch(path):
    git_dir = run_git_cmd(path, 'rev-parse', '--git-dir')
    if not git_dir:
        return None
    rebase_info = branch = ''
    if os.path.isfile(os.path.join(git_dir, 'rebase-merge', 'interactive')):
        rebase_info = '|REBASE-i'
        branch = open(os.path.join(git_dir, 'rebase-merge', 'head-name')).read().strip()
    elif os.path.isdir(os.path.join(git_dir, 'rebase-merge')):
        rebase_info = '|REBASE-m'
        branch = open(os.path.join(git_dir, 'rebase-merge', 'head-name')).read().strip()
    else:
        if os.path.isdir(os.path.join(git_dir, 'rebase-apply')):
            if os.path.isfile(os.path.join(git_dir, 'rebase-apply', 'rebasing')):
                rebase_info = '|REBASE'
            elif os.path.isfile(os.path.join(git_dir, 'rebase-apply', 'applying')):
                rebase_info = '|AM'
            else:
                rebase_info = '|AM/REBASE'
        elif os.path.isfile(os.path.join(git_dir, 'MERGE_HEAD')):
            rebase_info = 'MERGING'
        elif os.path.isfile(os.path.join(git_dir, 'BISECT_LOG')):
            rebase_info = 'BISECTING'
        branch = run_git_cmd(path, 'symbolic-ref', 'HEAD')
        if not branch:
            branch = run_git_cmd(path, 'describe', '--exact-match', 'HEAD')
        if not branch:
            branch = open(os.path.join(git_dir, 'HEAD')).read().strip()[:7]
        if not branch:
            branch = 'unknown'
    branch = remove_longest_substring(branch, 'refs/heads/')
    return branch + rebase_info


class GitThread(threading.Thread):
    def __init__(self):
        super(GitThread, self).__init__()
        self.daemon = True
        self.view_lock = threading.Lock()
        self.quit_lock = threading.Lock()
        self.views = {}
        self.status = {}
        self._quit = False
        self.status_setter()

    def run(self):
        while 1:
            with self.quit_lock:
                if self._quit:
                    return
            files = {}
            with self.view_lock:
                for vid, view in self.views.iteritems():
                    filename = view.file_name()
                    if filename:
                        files[vid] = filename
            status = {}
            for vid, filename in files.iteritems():
                status[vid] = git_branch(os.path.dirname(filename))
            with self.view_lock:
                self.status = status
            time.sleep(1)

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

    def status_setter(self):
        with self.view_lock:
            for vid, view in self.views.iteritems():
                s = self.status.get(view.id())
                if s:
                    view.set_status('git', 'Branch '+s)
                else:
                    view.erase_status('git')
        sublime.set_timeout(self.status_setter, 1000)


class git(sublime_plugin.EventListener):
    def __init__(self, *args, **kwargs):
        sublime_plugin.EventListener.__init__(self, *args, **kwargs)
        self.thread = GitThread()
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
