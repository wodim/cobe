# Copyright (C) 2012 Peter Teichman
# -*- coding: utf-8 -*-

import atexit
import fileinput
import logging
import os
import park
import re
import readline
import sys
import string

from . import analysis

from .brain import Brain
from .model import Model
from .varint import decode, decode_one, encode_one

log = logging.getLogger(__name__)


class DumpCommand(object):
    @classmethod
    def add_subparser(cls, parser):
        subparser = parser.add_parser("dump")
        subparser.set_defaults(run=cls.run)

    @staticmethod
    def run(args):
        store = park.SQLiteStore("cobe.store")
        analyzer = analysis.WhitespaceAnalyzer()
        model = Model(analyzer, store)

        print "Tokens:"
        for token, token_id in model.tokens.token_ids.iteritems():
            print token, decode_one(token_id)

        print "Normalized tokens:"
        for key in model._prefix_keys("n"):
            print key

        print "3-gram counts:"
        get_token = model.tokens.get_token
        for ngram, count in model._prefix_items("3", strip_prefix=True):
            # This needs a more efficient way to get the token ids,
            # maybe a simple varint-aware string split.
            grams = [get_token(encode_one(i)) for i in decode(ngram)]
            print grams, decode_one(count)


class TrainCommand(object):
    @classmethod
    def add_subparser(cls, parser):
        subparser = parser.add_parser("train", help="Train files of text")
        subparser.add_argument("file", nargs="+")
        subparser.set_defaults(run=cls.run)

    @staticmethod
    def run(args):
        brain = Brain("cobe.store")

        files = fileinput.FileInput(args.file,
                                    openhook=fileinput.hook_compressed)

        def lines():
            for line in files:
                if files.isfirstline():
                    print
                    print files.filename()

                if (files.lineno() % 1000) == 0:
                    print "%d..." % files.lineno(),
                    sys.stdout.flush()

                yield line.decode("utf-8", "replace")

            # Finish the count status line printed above
            print

        brain.train_many(lines())
        files.close()


class TrainIrcLogCommand:
    @classmethod
    def add_subparser(cls, parser):
        subparser = parser.add_parser("train-irc-log",
                                      help="Train a file of IRC log text")
        subparser.add_argument("-i", "--ignore-nick", action="append",
                               dest="ignored_nicks",
                               help="Ignore an IRC nick")
        subparser.add_argument("-o", "--only-nick", action="append",
                               dest="only_nicks",
                               help="Only train from specified nicks")
        subparser.add_argument("file", nargs="+")
        subparser.set_defaults(run=cls.run)

    @classmethod
    def run(cls, args):
        brain = Brain("cobe.store")

        files = fileinput.FileInput(args.file,
                                    openhook=fileinput.hook_compressed)

        lines = cls._irc_lines(files, ignored_nicks=args.ignored_nicks,
                               only_nicks=args.only_nicks)
        brain.train_many(lines)
        files.close()

    @classmethod
    def _irc_lines(cls, files, ignored_nicks=None, only_nicks=None):
        for line in files:
            if files.isfirstline():
                print
                print files.filename()

            if (files.lineno() % 1000) == 0:
                print "%d..." % files.lineno(),
                sys.stdout.flush()

            msg = cls._parse_irc_message(line, ignored_nicks=ignored_nicks,
                                         only_nicks=only_nicks)

            if msg is not None:
                yield msg.decode("utf-8", "replace")

        # Finish the count status line printed above
        print

    @classmethod
    def _parse_irc_message(cls, msg, ignored_nicks=None, only_nicks=None):
        # only match lines of the form "HH:MM <nick> message"
        match = re.match("\d+:\d+\s+<(.+?)>\s+(.*)", msg)
        if not match:
            return None

        nick = match.group(1)
        msg = match.group(2)

        if ignored_nicks is not None and nick in ignored_nicks:
            return None

        if only_nicks is not None and nick not in only_nicks:
            return None

        # strip "username: " at the beginning of messages
        match = re.search("^\S+[,:]\s+(\S.*)", msg)
        if match:
            msg = match.group(1)

        # strip kibot style '"asdf" --user, 06-oct-09' quotes
        msg = re.sub("\"(.*)\" --\S+,\s+\d+-\S+-\d+",
                     lambda m: m.group(1), msg)

        return msg


class ConsoleCommand:
    @classmethod
    def add_subparser(cls, parser):
        subparser = parser.add_parser("console", help="Interactive console")
        subparser.set_defaults(run=cls.run)

    @staticmethod
    def run(args):
        brain = Brain("cobe.store")

        history = os.path.expanduser("~/.cobe_history")
        try:
            readline.read_history_file(history)
        except IOError:
            pass
        atexit.register(readline.write_history_file, history)

        while True:
            try:
                text = raw_input("> ").decode("utf-8")
            except EOFError:
                print
                sys.exit(0)

            brain.train(text)
            print brain.reply(text)


class OneLinerCommand:
    @classmethod
    def add_subparser(cls, parser):
        subparser = parser.add_parser("oneliner", help="Dump one line and exit immediately")
        subparser.set_defaults(run=cls.run)

    @staticmethod
    def run(args):
        brain = Brain("cobe.store")
        _reply = brain.reply(u'')
        reply = u''

        for i in _reply:
            if i in string.ascii_letters + string.digits + u'áéíóúÁÉÍÓÚñÑlçÇ' + string.punctuation + ' ':
                reply += i

        if reply[-1] in string.ascii_lowercase and reply[-1] != '.':
            reply += '.'

        print reply
