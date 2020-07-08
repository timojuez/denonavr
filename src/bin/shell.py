#from code import InteractiveConsole #TODO
import argparse, os, sys, time, re, ast, traceback
from threading import Thread
from contextlib import suppress
from .. import Amp, amp, VERSION
try: import readline
except ImportError: pass


class CLI:
    
    def __init__(self):
        parser = argparse.ArgumentParser(description='Controller for Network Amp - CLI')
        parser.add_argument('--host', type=str, default=None, help='Amp IP or hostname')
        parser.add_argument('--port', type=int, default=None, help='Amp port')
        parser.add_argument('--protocol', type=str, default=None, help='Amp protocol')
        group = parser.add_mutually_exclusive_group(required=False)
        group.add_argument('--return', dest="ret", type=str, metavar="CMD", default=None, help='Return line that starts with CMD')
        group.add_argument('-f','--follow', default=False, action="store_true", help='Monitor amp messages')
        group.add_argument("file", metavar="HIFI FILE", type=str, nargs="?", help='Run hifi script')
        
        parser.add_argument("-c", "--command", default=[], metavar="CMD", nargs="+", help='Execute commands')
        parser.add_argument('--verbose', '-v', action='count', default=0, help='Verbose mode')
        self.args = parser.parse_args()
        assert(not (self.args.ret and self.args.follow))
        assert(self.args.command or not self.args.ret)
        
    def __call__(self):
        matches = (lambda cmd:cmd.startswith(self.args.ret)) if self.args.ret else None
        if len(self.args.command) == 0 and not self.args.file: self.print_header()
        self.amp = Amp(
            self.args.host, port=self.args.port, protocol=self.args.protocol, verbose=self.args.verbose)
        if self.args.follow: self.amp.bind(on_receive_raw_data=self.receive)
        with self.amp:
            self.compiler = Compiler(
                # environment variables for hifish
                __query__ = self.query,
                __return__ = matches,
                __wait__ = .1,
                amp = self.amp,
                help = self.print_help,
                help_attr = self.print_help_attr,
            )
            for cmd in self.args.command: self.compiler.run(cmd)
            if self.args.file: self.parse_file()
            if not self.args.file and not self.args.command or self.args.follow: self.prompt()
    
    def query(self, cmd, matches, wait):
        """ calling $"cmd" or $'cmd' from within hifish. @matches comes from --return """
        r = self.amp.query(cmd, matches)
        if wait: time.sleep(wait)
        return r
        
    def print_header(self):
        print("$_ HIFI SHELL %s"%VERSION)
        print("Copyright (c) 2020 Timo L. Richter\n")

    def prompt(self):
        self.amp.bind(on_disconnected=self.on_disconnected)
        while True:
            try: cmd = input("%s $ "%self.amp.prompt).strip()
            except KeyboardInterrupt: pass
            except EOFError: break
            else: 
                try: self.compiler.run(cmd)
                except Exception as e: print(traceback.format_exc())
            print()
        print()

    def parse_file(self):
        with open(self.args.file) as fp:
            self.compiler.run(fp.read(),self.args.file,"exec")
            
    def print_help(self):
        print(
            "Internal functions:\n"
            "\thelp()\tShow help\n"
            "\twait(seconds)\tSleep given amount of seconds\n"
            "\texit()\tQuit\n"
            "\n"
            "High level functions (protocol independent)\n"
            "\t$attribute\tVariable that contains amp's attribute, potentially read and writeable\n"
            "\tTo see a list of attributes, type help_attr()\n"
            "\n"
            "Low level functions (protocol dependent)\n"
            "\tCMD or $'CMD'\tSend CMD to the amp and return answer\n"
        )

    def print_help_attr(self):
        print("Current protocol supports these attributes:\n")
        for name, f in sorted(self.amp.features.items(), key=lambda e:e[0]):
            if not name: continue
            print("\t$%(name)s  %(title)s  %(type)s "%dict(name=name, type=f.type.__name__, title=f.name), end="")
            if isinstance(f,amp.features.IntFeature) or isinstance(f,amp.features.FloatFeature):
                print("[%s..%s] "%(f.min,f.max), end="")
            elif isinstance(f,amp.features.SelectFeature) or isinstance(f,amp.features.BoolFeature): 
                print(f.options, end="")
            print()
        print()
    
    def receive(self, data): print(data)
    
    def on_disconnected(self):
        print("\nConnection closed", file=sys.stderr)
        exit()


class AmpCommandTransformation(ast.NodeTransformer):
    """ transformer for the parsed python syntax tree """

    def _query_call(self, cmd):
        """ returns __query__(@cmd, __return__, __wait__) """
        node = ast.Call(
            func=ast.Name(id="__query__", ctx=ast.Load()),
            args=[
                ast.Str(Preprocessor.decode(cmd),ctx=ast.Load()),
                ast.Name(id="__return__",ctx=ast.Load()),
                ast.Name(id="__wait__",ctx=ast.Load()),
            ],
            keywords=[],
            ctx=ast.Load())
        self.generic_visit(node)
        return node
     
    def visit_Expr(self, node):
        """ handle amp commands outside of $, like MVUP;MVUP; """
        if isinstance(node.value, ast.Name): node.value = self._query_call(node.value.id)
        self.generic_visit(node)
        return node
        
    def visit_Constant(self, node):
        """ handle $'cmd' """
        if node.value.startswith("__PREPRO_DOLLAR__"):
            return self._query_call(node.value.replace("__PREPRO_DOLLAR__","",1))
        return node
        
    def visit_Str(self, node):
        """ handle $'cmd' """
        if node.s.startswith("__PREPRO_DOLLAR__"):
            return self._query_call(node.s.replace("__PREPRO_DOLLAR__","",1))
        return node
    
    def visit(self, node):
        r = super().visit(node)
        # undo preprocessing
        if isinstance(node, ast.Name): node.id = Preprocessor.decode(node.id)
        elif isinstance(node, ast.ClassDef): node.name = Preprocessor.decode(node.name)
        elif isinstance(node, ast.keyword): node.arg = Preprocessor.decode(node.arg)
        elif isinstance(node, ast.AsyncFunctionDef): node.name = Preprocessor.decode(node.name)
        elif isinstance(node, ast.FunctionDef): node.name = Preprocessor.decode(node.name)
        elif isinstance(node, ast.arg): node.arg = Preprocessor.decode(node.arg)
        elif isinstance(node, ast.Constant): node.value = Preprocessor.decode(node.value)
        elif isinstance(node, ast.Str): node.s = Preprocessor.decode(node.s)
        return r
        

class Preprocessor:
    """ Taking care of syntax that might be incompatible with the python parser
    like $ or ? outside of strings """
    
    replace = [
        #str,   replace,                ocurrance after parsing
        ("?",   "__PREPRO_QUESTION__",  "__PREPRO_QUESTION__"),
        ("$'",  "'__PREPRO_DOLLAR__",   "__PREPRO_DOLLAR__"),
        ('$"',  '"__PREPRO_DOLLAR__',   "__PREPRO_DOLLAR__"),
        ("$",   "amp.",                 "amp."),
    ]
    
    @classmethod
    def encode(self, source):
        for s,repl,find in self.replace: source = source.replace(s,repl)
        return source
        
    @classmethod
    def decode(self, data):
        for s,repl,find in self.replace: data = data.replace(find,s)
        return data


class Compiler(Preprocessor):

    def __init__(self, **env): 
        self.env = dict(**env, wait=time.sleep, __name__="__main__")

    def run(self, source, filename="<input>", mode="single"):
        tree = ast.parse(Preprocessor.encode(source),mode=mode)
        tree = AmpCommandTransformation().visit(tree)
        tree = ast.fix_missing_locations(tree)
        #print(ast.dump(tree))
        exec(compile(tree, filename=filename, mode=mode), self.env)
    
    
main = lambda:CLI()()
if __name__ == "__main__":
    main()

