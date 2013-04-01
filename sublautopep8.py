# coding=utf-8
import os
from collections import namedtuple
import re
from Queue import Queue

import sublime
import sublime_plugin

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

try:
    import sublimeautopep8lib.autopep8 as autopep8
    from sublimeautopep8lib.common import AutoPep8Thread, handle_threads
except ImportError:
    import AutoPEP8.sublimeautopep8lib.autopep8 as autopep8
    from AutoPEP8.sublimeautopep8lib.common import AutoPep8Thread, handle_threads


plugin_path = os.path.split(os.path.abspath(__file__))[0]
pycoding = re.compile("coding[:=]\s*([-\w.]+)")
if sublime.platform() == 'windows':
    BASE_NAME = 'AutoPep8 (Windows).sublime-settings'
else:
    BASE_NAME = 'AutoPep8.sublime-settings'


def pep8_params():
    params = ['-d']  # args for preview

    # read settings
    settings = sublime.load_settings(BASE_NAME)
    for opt in ("ignore", "select", "max-line-length"):
        params.append("--{0}={1}".format(opt, settings.get(opt, "")))

    if settings.get("list-fixes", None):
        params.append("--{0}={1}".format(opt, settings.get(opt)))

    for opt in ("verbose", "aggressive"):
        opt_count = settings.get(opt, 0)
        params.extend(["--" + opt] * opt_count)

    # autopep8.parse_args raises exception without it
    params.append('fake-arg')
    return autopep8.parse_args(params)[0]


class AutoPep8Command(sublime_plugin.TextCommand):

    def sel(self):
        sels = self.view.sel()
        if len(sels) == 1 and sels[0].a == sels[0].b:
            sels = [namedtuple('sel', ['a', 'b'])(0, self.view.size())]

        for sel in sels:
            region = sublime.Region(sel.a, sel.b)
            yield region, self.view.substr(region)

    def run(self, edit, preview=True):
        max_threads = sublime.load_settings(BASE_NAME).get('max-threads', 5)
        threads = []
        queue = Queue()
        stdoutput = StringIO()

        for region, substr in self.sel():
            args = {'pep8_params': pep8_params(), 'view': self.view,
                    'filename': self.view.file_name(),
                    'source': substr,
                    'preview': preview,
                    'stdoutput': stdoutput,
                    'edit': edit, 'region': region}
            queue.put(args)
            if len(threads) < max_threads:
                th = AutoPep8Thread(queue)
                th.start()
                threads.append(th)

        for _ in range(len(threads)):
            queue.put(None)
        if len(threads) > 0:
            sublime.set_timeout(lambda: handle_threads(threads, preview), 100)

    def is_visible(self, *args):
        view_syntax = self.view.settings().get('syntax')
        syntax_list = sublime.load_settings(
            BASE_NAME).get('syntax_list', ["Python"])
        return os.path.splitext(os.path.basename(view_syntax))[0] in syntax_list


class AutoPep8OutputCommand(sublime_plugin.TextCommand):

    def run(self, edit, text):
        self.view.insert(edit, 0, text)
        self.view.end_edit(edit)

    def is_visible(self, *args):
        return False


class AutoPep8FileCommand(sublime_plugin.WindowCommand):

    file_names = None

    def run(self, paths=None, preview=True):
        if not paths:
            return
        max_threads = sublime.load_settings(BASE_NAME).get('max-threads', 5)
        threads = []
        queue = Queue()

        for path in self.file_names:
            stdoutput = StringIO()
            in_data = open(path, 'r').read()

            args = {'pep8_params': pep8_params(), 'filename': path,
                    'source': in_data, 'preview': preview,
                    'stdoutput': stdoutput}

            queue.put(args)
            if len(threads) < max_threads:
                th = AutoPep8Thread(queue)
                th.start()
                threads.append(th)

        for _ in range(len(threads)):
            queue.put(None)
        if len(threads) > 0:
            sublime.set_timeout(lambda: handle_threads(threads, preview), 100)

    def files(self, path):
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                if filename.endswith('py'):
                    yield os.path.join(dirpath, filename)

    def is_visible(self, *args, **kwd):
        paths = kwd.get('paths')
        if not paths:
            return False
        files = []
        for path in paths:
            if os.path.isdir(path):
                files.extend(self.files(path))
            if os.path.isfile(path) and path.endswith('py'):
                files.append(path)
        if not (files and filter(lambda item: item.endswith('py'), files)):
            return False
        self.file_names = files
        return True


class AutoPep8Listener(sublime_plugin.EventListener):

    def on_pre_save_async(self, view):
        view_syntax = view.settings().get('syntax')
        syntax_list = sublime.load_settings(
            BASE_NAME).get('syntax_list', ["Python"])
        if os.path.splitext(os.path.basename(view_syntax))[0] in syntax_list:
            view.run_command("auto_pep8", {"preview": False})

    def on_pre_save(self, view):
        if sublime.version() < '3000':
            self.on_pre_save_async(view)
