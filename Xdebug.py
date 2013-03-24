import sublime
import sublime_plugin
import os
import socket
import base64
import threading
import webbrowser
import collections
import urllib.parse
from xml.dom.minidom import parseString

PLUGIN_FOLDER = os.path.basename(os.path.dirname(os.path.realpath(__file__)))
ICON_PATH = "Packages/" + PLUGIN_FOLDER + '/icons/'

ICON_BREAKPOINT = ICON_PATH + 'breakpoint.png'
ICON_CURRENT = ICON_PATH + 'current.png'
ICON_CURRENT_BREAKPOINT = ICON_PATH +'current_breakpoint.png'

TITLE_WINDOW_STACK = "Xdebug Stack"
TITLE_WINDOW_CONTEXT = "Xdebug Context"

DEFAULT_IDE_KEY = 'default.sublime.xdebug'
DEFAULT_PORT = 9000

xdebug_current = None
protocol = None
buffers = {}


class DebuggerException(Exception):
    pass


class ProtocolException(DebuggerException):
    pass


class ProtocolConnectionException(ProtocolException):
    pass


class Protocol(object):
    """
    Represents DBGp Protocol Language
    """

    read_rate = 1024

    def __init__(self):
        self.port = get_project_setting('port') or get_setting('port') or DEFAULT_PORT
        self.clear()

    def clear(self):
        self.buffer = ''
        self.connected = False
        self.listening = False
        self.server = None
        del self.transaction_id
        try:
            self.sock.close()
        except:
            pass
        self.sock = None

    def transaction_id():
        """
        The transaction_id property.
        """

        def fget(self):
            self._transaction_id += 1
            return self._transaction_id

        def fset(self, value):
            self._transaction_id = value

        def fdel(self):
            self._transaction_id = 0
        return locals()

    transaction_id = property(**transaction_id())

    def read_until_null(self):
        if self.connected:
            while not '\x00' in self.buffer:
                self.buffer += self.sock.recv(self.read_rate).decode('utf8')
            data, self.buffer = self.buffer.split('\x00', 1)
            return data
        else:
            raise(ProtocolConnectionException, "Not Connected")

    def read_data(self):
        length = self.read_until_null()
        message = self.read_until_null()
        if int(length) == len(message):
            return message
        else:
            raise(ProtocolException, "Length mismatch")

    def read(self):
        data = self.read_data()
        #print('<---', data)
        document = parseString(data)
        return document

    def send(self, command, *args, **kwargs):
        if 'data' in kwargs:
            data = kwargs['data']
            del kwargs['data']
        else:
            data = None

        tid = self.transaction_id
        parts = [command, '-i %i' % tid]

        if args:
            parts.extend(args)
        if kwargs:
            parts.extend(['-%s %s' % pair for pair in kwargs.items()])
        parts = [part.strip() for part in parts if part.strip()]
        command = ' '.join(parts)
        if data:
            command += ' -- ' + base64.b64encode(data)

        try:
            self.sock.send(bytes(command + '\x00', 'utf8'))
            #print('--->', command)
        except Exception as x:
            raise(ProtocolConnectionException, x)

    def accept(self):
        serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if serv:
            try:
                serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                serv.settimeout(1)
                serv.bind(('', self.port))
                serv.listen(1)
                self.listening = True
                self.sock = None
            except Exception as x:
                raise(ProtocolConnectionException, x)

            while self.listening:
                try:
                    self.sock, address = serv.accept()
                    self.listening = False
                except socket.timeout:
                    pass

            if self.sock:
                self.connected = True
                self.sock.settimeout(None)
            else:
                self.connected = False
                self.listening = False

            try:
                serv.close()
                serv = None
            except:
                pass
            return self.sock
        else:
            raise ProtocolConnectionException('Could not create socket')


class XdebugView(object):
    """
    The XdebugView is sort of a normal view with some convenience methods.

    See lookup_view.
    """
    def __init__(self, view):
        self.view = view
        self.current_line = None
        self.context_data = {}
        self.breaks = {}  # line : meta { id: bleh }

    def __getattr__(self, attr):
        if hasattr(self.view, attr):
            return getattr(self.view, attr)
        if attr.startswith('on_'):
            return self
        raise(AttributeError, "%s does not exist" % attr)

    def __call__(self, *args, **kwargs):
        pass

    def center(self, lineno):
        line = self.lines(lineno)[0]
        self.view.show_at_center(line)

    def add_breakpoint(self, row):
        if row is None:
            return
        if not row in self.breaks:
            self.breaks[row] = {}
            if protocol and protocol.connected:
                protocol.send('breakpoint_set', t='line', f=self.uri(), n=row)
                res = protocol.read().firstChild
                self.breaks[row]['id'] = res.getAttribute('id')

    def del_breakpoint(self, row):
        if row in self.breaks:
            if protocol and protocol.connected:
                protocol.send('breakpoint_remove', d=self.breaks[row]['id'])
            del self.breaks[row]

    def view_breakpoints(self):
        self.view.add_regions('xdebug_breakpoint', self.lines(list(self.breaks.keys())), get_setting('breakpoint_scope'), ICON_BREAKPOINT, sublime.HIDDEN)

    def breakpoint_init(self):
        if not self.breaks:
            return
        uri = self.uri()
        for row in self.breaks:
            protocol.send('breakpoint_set', t='line', f=uri, n=row)
            res = protocol.read().firstChild
            self.breaks[row]['id'] = res.getAttribute('id')

    def breakpoint_clear(self):
        if not self.breaks:
            return
        for row in self.breaks.copy().keys():
            self.del_breakpoint(row)

    def uri(self):
        """
        Server file path uri for local file path
        """
        return get_real_path(self.view.file_name(), True)

    def lines(self, data=None):
        lines = []
        if data is None:
            regions = self.view.sel()
        else:
            if not isinstance(data, list):
                data = [data]
            regions = []
            for item in data:
                if isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
                    regions.append(self.view.line(self.view.text_point(int(item) - 1, 0)))
                else:
                    regions.append(item)
        for region in regions:
            lines.extend(self.view.split_by_newlines(region))
        return [self.view.line(line) for line in lines]

    def rows(self, lines):
        if not isinstance(lines, list):
            lines = [lines]
        return [self.view.rowcol(line.begin())[0] + 1 for line in lines]

    def append(self, content, edit=None, end=False):
        if not edit:
            edit = self.view.begin_edit()
            end = True
        self.view.insert(edit, self.view.size(), content + "\n")
        if end:
            self.view.end_edit(edit)
        return edit

    def on_load(self):
        if self.current_line:
            self.current(self.current_line)
            self.current_line = None

    def current(self, line):
        if self.is_loading():
            self.current_line = line
            return
        region = self.lines(line)
        icon = ICON_CURRENT

        if line in self.breaks.keys():
            icon = ICON_CURRENT_BREAKPOINT

        self.add_regions('xdebug_current_line', region, get_setting('current_line_scope'), icon, sublime.HIDDEN)
        self.center(line)

    def add_context_data(self, propName, propType, propData):
        """
        Store context data
        """
        self.context_data[propName] = {'type': propType, 'data': propData}

    def on_selection_modified(self):
        """
        Show selected variable in an output panel when clicked
        """
        if protocol and protocol.connected and self.context_data:
            data = ''
            point = self.view.sel()[0].a
            var_name = self.view.substr(self.view.word(point))
            if not var_name.startswith('$'):
                var_name = '$' + var_name
            is_variable = sublime.score_selector(self.view.scope_name(point), 'variable')

            if is_variable and var_name in self.context_data:
                kind = self.context_data[var_name]['type']
                if kind == 'array' or kind == 'object':
                    for key in sorted(self.context_data.keys()):
                        if key.startswith(var_name):
                            data += '{k} ({t}) = {d}\n'.format(k=key, t=self.context_data[key]['type'], d=self.context_data[key]['data'])
                else:
                    data += '{k} ({t}) = {d}\n'.format(k=var_name, t=kind, d=self.context_data[var_name]['data'])

            window = self.view.window()
            if window:
                output = window.get_output_panel('xdebug_inspect')
                output.run_command("xdebug_view_update", {'data' : data} )
                window.run_command('show_panel', {"panel": 'output.xdebug_inspect'})


class XdebugListenCommand(sublime_plugin.TextCommand):
    """
    Start listening for Xdebug connections
    """
    def run(self, edit):
        global protocol
        protocol = Protocol()

        threading.Thread(target=self.thread_callback).start()

    def thread_callback(self):
        protocol.accept()
        if protocol and protocol.connected:
            sublime.set_timeout(self.gui_callback, 0)

    def gui_callback(self):
        sublime.status_message('Xdebug: Connected')
        init = protocol.read().firstChild
        uri = init.getAttribute('fileuri')
        show_file(self.view.window(), uri)

        for view in buffers.values():
            view.breakpoint_init()

        self.view.run_command('xdebug_continue', {'state': 'run'})

    def is_enabled(self):
        if protocol:
            return False
        return True


class XdebugClearAllBreakpointsCommand(sublime_plugin.TextCommand):
    """
    Clear breakpoints in all open buffers
    """
    def run(self, edit):
        for view in buffers.values():
            view.breakpoint_clear()
            view.view_breakpoints()


class XdebugBreakpointCommand(sublime_plugin.TextCommand):
    """
    Toggle a breakpoint
    """
    def run(self, edit):
        view = lookup_view(self.view)
        for row in view.rows(view.lines()):
            if row in view.breaks:
                view.del_breakpoint(row)
            else:
                view.add_breakpoint(row)
        view.view_breakpoints()


class XdebugCommand(sublime_plugin.TextCommand):
    """
    The Xdebug main quick panel menu
    """
    def run(self, edit):
        """
        Open quick panel and show Xdebug options
        """
        self.url = get_project_setting('url')

        mapping = collections.OrderedDict()
        mapping['xdebug_breakpoint'] = 'Add/Remove Breakpoint'
        mapping['xdebug_clear_all_breakpoints'] = 'Clear all Breakpoints'

        if protocol and protocol.connected:
            mapping['xdebug_status'] = 'Status'
            mapping['xdebug_execute'] = 'Execute'

        if protocol:
            mapping['xdebug_clear'] = 'Stop debugging'
            if self.url:
                mapping['xdebug_clear_web'] = 'Stop debugging (Launch browser)'
            mapping['xdebug_clear_close'] = 'Stop debugging (Close windows)'
        else:
            mapping['xdebug_listen'] = 'Start debugging'
            if self.url:
                mapping['xdebug_listen_web'] = 'Start debugging (Launch browser)'

        self.cmds = list(mapping.keys())
        self.items = list(mapping.values())
        self.view.window().show_quick_panel(self.items, self.callback)

    def callback(self, index):
        """
        Handle selection from quick panel
        """
        if index == -1:
            return

        close_window = False
        ide_key = get_project_setting('ide_key') or get_setting('ide_key') or DEFAULT_IDE_KEY

        if self.url:
            launch_browser = True
        else:
            sublime.status_message('Xdebug: No URL defined in project settings file.')

        command = self.cmds[index]
        if command is 'xdebug_listen_web':
            command = 'xdebug_listen'
        elif command is 'xdebug_clear_web':
            command = 'xdebug_clear'
        else:
            launch_browser = False
        if command is 'xdebug_clear_close':
            close_window = True
            command = 'xdebug_clear'

        self.view.run_command(command)

        if protocol and command == 'xdebug_listen':
            if launch_browser:
                webbrowser.open(self.url + '?XDEBUG_SESSION_START=' + ide_key)

            window = sublime.active_window()
            window.set_layout({
                "cols": [0.0, 0.5, 1.0],
                "rows": [0.0, 0.7, 1.0],
                "cells": [[0, 0, 2, 1], [0, 1, 1, 2], [1, 1, 2, 2]]
            })

        if command == 'xdebug_clear':
            if launch_browser:
                webbrowser.open(self.url + '?XDEBUG_SESSION_STOP=' + ide_key)
            if close_window:
                self.view.run_command('xdebug_close_windows')


class XdebugContinueCommand(sublime_plugin.TextCommand):
    """
    Continue execution menu and commands.

    This command shows the quick panel and executes the selected option.
    """
    states = collections.OrderedDict()
    states['run'] = 'Run'
    states['step_over'] = 'Step Over'
    states['step_into'] = 'Step Into'
    states['step_out'] = 'Step Out'
    states['stop'] = 'Stop'
    states['detach'] = 'Detach'

    state_index = list(states.keys())
    state_options = list(states.values())

    def run(self, edit, state=None):
        if not state or not state in self.states:
            self.view.window().show_quick_panel(self.state_options, self.callback)
        else:
            self.callback(state)

    def callback(self, state):
        if state == -1:
            return
        if isinstance(state, int):
            state = self.state_index[state]

        global xdebug_current
        reset_current()

        protocol.send(state)
        res = protocol.read().firstChild

        for child in res.childNodes:
            if child.nodeName == 'xdebug:message':
                #print('>>>break ' + child.getAttribute('filename') + ':' + child.getAttribute('lineno'))
                sublime.status_message('Xdebug: breakpoint')
                xdebug_current = show_file(self.view.window(), child.getAttribute('filename'))
                if not xdebug_current is None:
                    xdebug_current.current(int(child.getAttribute('lineno')))

        if (res.getAttribute('status') == 'break'):
            # TODO stack_get
            protocol.send('context_get')
            res = protocol.read().firstChild
            result = ''

            def getValues(node):
                result = ''
                for child in node.childNodes:
                    if child.nodeName == 'property':
                        propName = child.getAttribute('fullname')
                        propType = child.getAttribute('type')
                        propValue = None
                        try:
                            # Try to base64 decode value
                            propValue = ' '.join(base64.b64decode(t.data).decode('utf8') for t in child.childNodes if t.nodeType == t.TEXT_NODE or t.nodeType == t.CDATA_SECTION_NODE)
                        except:
                            # Return raw value
                            propValue = ' '.join(t.data for t in child.childNodes if t.nodeType == t.TEXT_NODE or t.nodeType == t.CDATA_SECTION_NODE)
                        if propName:
                            if propName.lower().find('password') != -1:
                                propValue = '*****'
                            result = result + propName + ' [' + propType + '] = ' + propValue + '\n'
                            result = result + getValues(child)
                            if xdebug_current:
                                xdebug_current.add_context_data(propName, propType, propValue)
                return result

            result = getValues(res)
            add_debug_info('context', result)
            if xdebug_current:
                xdebug_current.on_selection_modified()

            protocol.send('stack_get')
            res = protocol.read().firstChild
            result = ''
            for child in res.childNodes:
                if child.nodeName == 'stack':
                    propWhere = child.getAttribute('where')
                    propLevel = child.getAttribute('level')
                    propType = child.getAttribute('type')
                    propFile = urllib.parse.unquote(child.getAttribute('filename'))
                    propLine = child.getAttribute('lineno')
                    result = result + '{level:>3}: {type:<10} {where:<10} {filename}:{lineno}\n' \
                                              .format(level=propLevel, type=propType, where=propWhere, lineno=propLine, filename=propFile)
            add_debug_info('stack', result)

        if res.getAttribute('status') == 'stopping' or res.getAttribute('status') == 'stopped':
            self.view.run_command('xdebug_clear')
            self.view.run_command('xdebug_listen')
            sublime.status_message('Xdebug: Page finished executing. Reload to continue debugging.')

    def is_enabled(self):
        if protocol and protocol.connected:
            return True
        if protocol:
            sublime.status_message('Xdebug: Waiting for executing to start')
            return False
        sublime.status_message('Xdebug: Not running')
        return False


class XdebugClearCommand(sublime_plugin.TextCommand):
    """
    Close the socket and stop listening to xdebug
    """
    def run(self, edit):
        global protocol
        try:
            protocol.clear()
            reset_current()
        except:
            pass
        finally:
            protocol = None

    def is_enabled(self):
        if protocol:
            return True
        return False


class XdebugStatus(sublime_plugin.TextCommand):
    """
    DBGp status command
    """
    def run(self, edit):
        protocol.send('status')
        res = protocol.read().firstChild
        sublime.status_message(res.getAttribute('reason') + ': ' + res.getAttribute('status'))

    def is_enabled(self):
        if protocol and protocol.connected:
            return True
        return False


class XdebugExecute(sublime_plugin.TextCommand):
    """
    Execute arbitrary DBGp command
    """
    def run(self, edit):
        self.view.window().show_input_panel('Xdebug Execute', '',
            self.on_done, self.on_change, self.on_cancel)

    def is_enabled(self):
        if protocol and protocol.connected:
            return True
        return False

    def on_done(self, line):
        if ' ' in line:
            command, args = line.split(' ', 1)
        else:
            command, args = line, ''
        protocol.send(command, args)
        res = protocol.read().firstChild

        window = self.view.window()
        output = window.get_output_panel('xdebug_execute')
        output.run_command("xdebug_view_update", {'data' : res.toprettyxml()} )
        window.run_command('show_panel', {"panel": 'output.xdebug_execute'})

    def on_change(self, line):
        pass

    def on_cancel(self):
        pass


class XdebugCloseWindowsCommand(sublime_plugin.TextCommand):
    """
    Close all Xdebug related windows
    """
    def run(self, edit):
        window = sublime.active_window()
        window.set_layout({
            "cols": [0.0, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1]]
        })

        window.run_command('hide_panel', {"panel": 'output.xdebug_inspect'})

        for v in window.views():
            if v.name() == TITLE_WINDOW_STACK or v.name() == TITLE_WINDOW_CONTEXT:
                window.focus_view(v)
                window.run_command('close')


class XdebugViewUpdateCommand(sublime_plugin.TextCommand):
    """
    Update view for Xdebug plugin
    """
    def run(self, edit, data=None, readonly=False):
        v = self.view
        v.set_read_only(False)
        v.erase(edit, sublime.Region(0, v.size()))
        if not data is None:
            v.insert(edit, 0, data)
        if readonly:
            v.set_read_only(True)


class EventListener(sublime_plugin.EventListener):
    def on_new(self, view):
        lookup_view(view).on_new()

    def on_clone(self, view):
        lookup_view(view).on_clone()

    def on_load(self, view):
        lookup_view(view).on_load()

    def on_close(self, view):
        lookup_view(view).on_close()

    def on_pre_save(self, view):
        lookup_view(view).on_pre_save()

    def on_post_save(self, view):
        lookup_view(view).on_post_save()

    def on_modified(self, view):
        lookup_view(view).on_modified()

    def on_selection_modified(self, view):
        lookup_view(view).on_selection_modified()

    def on_activated(self, view):
        lookup_view(view).on_activated()

    def on_deactivated(self, view):
        lookup_view(view).on_deactivated()

    def on_query_context(self, view, key, operator, operand, match_all):
        lookup_view(view).on_query_context(key, operator, operand, match_all)


def lookup_view(v):
    """
    Convert a Sublime View into an XdebugView
    """
    if isinstance(v, XdebugView):
        return v
    if isinstance(v, sublime.View):
        id = v.buffer_id()
        if id in buffers:
            buffers[id].view = v
        else:
            buffers[id] = XdebugView(v)
        return buffers[id]
    return None


def show_file(window, uri):
    """
    Open or focus file in window, which is currently being debugged.

    Keyword arguments:
    window -- Which window where to display the file.
    uri -- URI path of file on server received from Xdebug response.

    """
    if window:
        window.focus_group(0)
    # Map web server path to local system path
    filename = get_real_path(uri)

    # Check if file exists if being referred to file system
    if os.path.exists(filename):
        found = False
        window = sublime.active_window()
        view = window.find_open_file(filename)
        # Focus file if window is already open
        if not view is None:
            found = True
            window.focus_view(view)

        # Otherwise open file
        if not found:
            #view = window.open_file(filename, sublime.TRANSIENT)
            view = window.open_file(filename)

        return lookup_view(view)


def reset_current():
    """
    Reset the current line marker
    """
    global xdebug_current
    if xdebug_current:
        xdebug_current.erase_regions('xdebug_current_line')
        xdebug_current = None


def get_project_setting(key):
    """
    Get a project setting.

    Xdebug project settings are stored in the sublime project file
    as a dictionary:

        "settings":
        {
            "xdebug": { "key": "value", ... }
        }
    """
    try:
        s = sublime.active_window().active_view().settings()
        xdebug = s.get('xdebug')
        if xdebug:
            if key in xdebug:
                return xdebug[key]
    except:
        pass


def get_setting(key):
    """
    Get Xdebug setting
    """
    s = sublime.load_settings("Xdebug.sublime-settings")
    if s and s.has(key):
        return s.get(key)


def add_debug_info(name, data):
    """
    Adds data to the debug output windows
    """
    found = False
    v = None
    window = sublime.active_window()

    if name == 'context':
        group = 1
        fullName = TITLE_WINDOW_CONTEXT
    if name == 'stack':
        group = 2
        fullName = TITLE_WINDOW_STACK

    for v in window.views():
        if v.name() == fullName:
            found = True
            break

    if not found:
        v = window.new_file()
        v.set_scratch(True)
        v.set_read_only(True)
        v.set_name(fullName)
        v.settings().set('word_wrap', False)
        found = True

    if found:
        window.set_view_index(v, group, 0)
        v.run_command('xdebug_view_update', {'data': data, 'readonly': True})

    window.focus_group(0)


def get_real_path(uri, server=False):
    """
    Get real path

    Keyword arguments:
    uri -- Uri of file that needs to be mapped and located
    server -- Map local path to server path

    """
    if uri is None:
        return uri

    # URLdecode uri
    uri = urllib.parse.unquote(uri)

    # Get filename
    try:
        if sublime.platform() == 'windows':
            transport, filename = uri.split(':///', 1)  # scheme:///C:/path/file => scheme, C:/path/file
        else:
            transport, filename = uri.split('://', 1)  # scheme:///path/file => scheme, /path/file
    except:
        filename = uri

    # Get real path for the filesystem and remove trailing slashes
    uri = os.path.realpath(filename)

    path_mapping = get_project_setting('path_mapping') or get_setting('path_mapping')
    if not path_mapping is None:
        # Go through path mappings
        for server_path, local_path in path_mapping.items():
            server_path = os.path.realpath(server_path)
            local_path = os.path.realpath(local_path)
            # Replace path if mapping available
            if server:
                # Map local path to server path
                if local_path in uri:
                    return urllib.parse.quote("file://" + uri.replace(local_path, server_path))
            else:
                # Map server path to local path
                if server_path in uri:
                    return uri.replace(server_path, local_path)
    else:
        sublime.status_message("Xdebug: No path mapping defined, returning given path.")

    if server:
        return urllib.parse.quote("file://" + uri)

    return uri