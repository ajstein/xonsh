# -*- coding: utf-8 -*-
"""The main xonsh script."""
import os
import sys
import enum
import builtins
from argparse import ArgumentParser, ArgumentTypeError
from contextlib import contextmanager

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None

from xonsh import __version__
from xonsh.shell import Shell
from xonsh.pretty import pprint, pretty
from xonsh.jobs import ignore_sigtstp
from xonsh.tools import HAVE_PYGMENTS, setup_win_unicode_console, print_color, ON_WINDOWS

if HAVE_PYGMENTS:
    import pygments
    from xonsh import pyghooks


def path_argument(s):
    """Return a path only if the path is actually legal

    This is very similar to argparse.FileType, except that it doesn't return
    an open file handle, but rather simply validates the path."""

    s = os.path.abspath(os.path.expanduser(s))
    if not os.path.isfile(s):
        raise ArgumentTypeError('"%s" must be a valid path to a file' % s)
    return s


parser = ArgumentParser(description='xonsh', add_help=False)
parser.add_argument('-h', '--help',
                    dest='help',
                    action='store_true',
                    default=False,
                    help='show help and exit')
parser.add_argument('-V', '--version',
                    dest='version',
                    action='store_true',
                    default=False,
                    help='show version information and exit')
parser.add_argument('-c',
                    help="Run a single command and exit",
                    dest='command',
                    required=False,
                    default=None)
parser.add_argument('-i',
                    help='force running in interactive mode',
                    dest='force_interactive',
                    action='store_true',
                    default=False)
parser.add_argument('-l',
                    help='run as a login shell',
                    dest='login',
                    action='store_true',
                    default=False)
parser.add_argument('--config-path',
                    help='specify a custom static configuration file',
                    dest='config_path',
                    default=None,
                    type=path_argument)
parser.add_argument('--no-rc',
                    help="Do not load the .xonshrc files",
                    dest='norc',
                    action='store_true',
                    default=False)
parser.add_argument('-D',
                    dest='defines',
                    help='define an environment variable, in the form of '
                         '-DNAME=VAL. May be used many times.',
                    metavar='ITEM',
                    nargs='*',
                    default=None)
parser.add_argument('--shell-type',
                    help='What kind of shell should be used. '
                         'Possible options: readline, prompt_toolkit, random. '
                         'Warning! If set this overrides $SHELL_TYPE variable.',
                    dest='shell_type',
                    choices=('readline', 'prompt_toolkit', 'best', 'random'),
                    default=None)
parser.add_argument('file',
                    metavar='script-file',
                    help='If present, execute the script in script-file'
                         ' and exit',
                    nargs='?',
                    default=None)
parser.add_argument('args',
                    metavar='args',
                    help='Additional arguments to the script specified '
                         'by script-file',
                    nargs='*',
                    default=[])


def arg_undoers():
    au = {
        '-h': (lambda args: setattr(args, 'help', False)),
        '-V': (lambda args: setattr(args, 'version', False)),
        '-c': (lambda args: setattr(args, 'command', None)),
        '-i': (lambda args: setattr(args, 'force_interactive', Fals)),
        '-l': (lambda args: setattr(args, 'login', False)),
        '-c': (lambda args: setattr(args, 'command', None)),
        '--config-path': (lambda args: delattr(args, 'config_path')),
        '--no-rc': (lambda args: setattr(args, 'norc', False)),
        '-D': (lambda args: setattr(args, 'defines', None)),
        '--shell-type': (lambda args: setattr(args, 'shell_type', None)),
        }
    au['--help'] = au['-h']
    au['--version'] = au['-V']
    return au

def undo_args(args):
    """Undoes missaligned args."""
    au = arg_undoers()
    for a in args.args:
        if a in au:
            au[a](args)
        else:
            for k in au:
                if a.startswith(k):
                    au[k](args)

def _pprint_displayhook(value):
    if value is not None:
        builtins._ = None  # Set '_' to None to avoid recursion
        if HAVE_PYGMENTS:
            s = pretty(value)  # color case
            lexer = pyghooks.XonshLexer()
            tokens = list(pygments.lex(s, lexer=lexer))
            print_color(tokens)
        else:
            pprint(value)  # black & white case
        builtins._ = value

class XonshMode(enum.Enum):
    single_command = 0
    script_from_file = 1
    script_from_stdin = 2
    interactive = 3

def premain(argv=None):
    """Setup for main xonsh entry point, returns parsed arguments."""
    if setproctitle is not None:
        setproctitle(' '.join(['xonsh'] + sys.argv[1:]))
    args, other = parser.parse_known_args(argv)
    if args.file is not None:
        real_argv = (argv or sys.argv)
        i = real_argv.index(args.file)
        args.args = real_argv[i+1:]
        undo_args(args)
    if args.help:
        parser.print_help()
        exit()
    if args.version:
        version = '/'.join(('xonsh', __version__)),
        print(version)
        exit()
    shell_kwargs = {'shell_type': args.shell_type,
                    'completer': False,
                    'login': False}
    if args.login:
        shell_kwargs['login'] = True
    if args.config_path is None:
        shell_kwargs['config'] = args.config_path
    if args.norc:
        shell_kwargs['rc'] = ()
    setattr(sys, 'displayhook', _pprint_displayhook)
    if args.command is not None:
        args.mode = XonshMode.single_command
        shell_kwargs['shell_type'] = 'none'
    elif args.file is not None:
        args.mode = XonshMode.script_from_file
        shell_kwargs['shell_type'] = 'none'
    elif not sys.stdin.isatty() and not args.force_interactive:
        args.mode = XonshMode.script_from_stdin
        shell_kwargs['shell_type'] = 'none'
    else:
        args.mode = XonshMode.interactive
        shell_kwargs['completer'] = True
        shell_kwargs['login'] = True
    shell = builtins.__xonsh_shell__ = Shell(**shell_kwargs)
    from xonsh import imphooks
    env = builtins.__xonsh_env__
    env['XONSH_LOGIN'] = shell_kwargs['login']
    if args.defines is not None:
        env.update([x.split('=', 1) for x in args.defines])
    env['XONSH_INTERACTIVE'] = False
    if ON_WINDOWS:
        setup_win_unicode_console(env.get('WIN_UNICODE_CONSOLE', True))
    return args


def main(argv=None):
    """Main entry point for xonsh cli."""
    args = premain(argv)
    env = builtins.__xonsh_env__
    shell = builtins.__xonsh_shell__
    if args.mode == XonshMode.single_command:
        # run a single command and exit
        shell.default(args.command)
    elif args.mode == XonshMode.script_from_file:
        # run a script contained in a file
        if os.path.isfile(args.file):
            with open(args.file) as f:
                code = f.read()
            code = code if code.endswith('\n') else code + '\n'
            sys.argv = args.args
            env['ARGS'] = [args.file] + args.args
            code = shell.execer.compile(code, mode='exec', glbs=shell.ctx,
                                        filename=args.file)
            shell.execer.exec(code, mode='exec', glbs=shell.ctx)
        else:
            print('xonsh: {0}: No such file or directory.'.format(args.file))
    elif args.mode == XonshMode.script_from_stdin:
        # run a script given on stdin
        code = sys.stdin.read()
        code = code if code.endswith('\n') else code + '\n'
        code = shell.execer.compile(code, mode='exec', glbs=shell.ctx,
                                    filename='<stdin>')
        shell.execer.exec(code, mode='exec', glbs=shell.ctx)
    else:
        # otherwise, enter the shell
        env['XONSH_INTERACTIVE'] = True
        ignore_sigtstp()
        if not env['LOADED_CONFIG'] and not any(env['LOADED_RC_FILES']):
            print('Could not find xonsh configuration or run control files.')
            code = '$[xonfig wizard --confirm]'
            shell.execer.exec(code, mode='single', glbs=shell.ctx)
        shell.cmdloop()
    postmain(args)


def postmain(args=None):
    """Teardown for main xonsh entry point, accepts parsed arguments."""
    if ON_WINDOWS:
        setup_win_unicode_console(enable=False)
    del builtins.__xonsh_shell__


@contextmanager
def main_context(argv=None):
    """Generator that runs pre- and post-main() functions. This has two iterations.
    The first yields the shell. The second returns None but cleans
    up the shell.
    """
    args = premain(argv)
    yield builtins.__xonsh_shell__
    postmain(args)



if __name__ == '__main__':
    main()
