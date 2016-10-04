import sublime, sublime_plugin

import imp
import os
import subprocess
import sys
import threading


def is_ST3():
    '''check if ST3 based on python version'''
    return sys.version_info >= (3, 0)


if is_ST3():
    import queue
    import io
else:
    import Queue as queue
    import StringIO as io


class CodeFightsCommand(sublime_plugin.TextCommand):
    def run(self, edit,
            generateOutputs=False, generator_ext=None,
            validate=False, validator_ext=None,
            autoBugfixes=False, autoBugfixes_validate=None,
            getLimits=False, update_limits=None,
            styleChecker=False, styleChecker_ext=None, styleChecker_fix=None,
            generateTests=False,
            kill=False):

        valid_args = ['generateOutputs', 'validate', 'autoBugfixes', 
                      'getLimits', 'styleChecker', 'generateTests']
        ext_by_arg = {
            'generateOutputs': ['json'],
            'validate': ['py', 'js', 'java', 'cpp', 'cs', 'fs', 
                         'perl', 'php', 'rb', 'scala', 'swift', 'go', 
                         'hs', 'md', 'r', 'vb'],
            'autoBugfixes': ['py'],
            'getLimits': ['md'],
            'styleChecker': ['py', 'js', 'java', 'cpp', 'md'],
            'generateTests': [None]
        }
        arg_by_ext = {}
        for arg in ext_by_arg:
            for ext in ext_by_arg[arg]:
                arg_by_ext.setdefault(ext, []).append(arg)
        self.killed = False

        if kill:
            if hasattr(self, 'thread') and self.thread is not None:
                self.thread = None
                self.killed = True
                self.to_panel("\nCodeFights execution killed.\n")
            return

        if is_ST3():
            self.panel = self.view.window().create_output_panel('codefights_output')
            self.view.window().run_command('show_panel', {'panel': 'output.codefights_output'})      
        else:
            self.show_tests_panel()

        if len(self.view.file_name()) > 0:
            full_path = self.view.file_name()            
            task_path, file_name = os.path.split(full_path)
            data_folder, task_name = os.path.split(task_path)
            file_name = file_name.split('.')

            if len(file_name) < 2:
                file_name.append(None)

            file_ext = file_name[-1]
            args = []
            for arg in valid_args:
                if eval(arg):  #: from string to argument
                    args.append(arg)
            command = None

            if len(args) == 0:
                self.to_panel("No argument specified!\n")
                return
            elif len(args) == 1:
                if file_ext in ext_by_arg[args[0]]:
                    command = args[0]
                else:
                    self.to_panel("Invalid file extension! Expected one of the following: {0}\n".\
                        format(ext_by_arg[args[0]]))
                    return
            else:
                found_command = None
                for arg in args:
                    if file_ext in ext_by_arg[arg]:
                        if found_command is None:
                            found_command = arg
                        else:
                            self.to_panel("Ambiguous arguments for the current file extension!\n")
                            return
                if found_command is None:
                    print args, ext_by_arg
                    self.to_panel("Invalid file extension!\n")
                    return
                command = found_command

            if command == 'generateOutputs':
                settings = sublime.load_settings('CodeFights.sublime-settings')
                if generator_ext is None:
                    generator_ext = settings.get('generate_from')
                self.thread = CodeFightsOutputsGenerator(task_name, data_folder, generator_ext)
            elif command == 'validate':
                if validator_ext is None:
                    validator_ext = file_ext
                self.thread = CodeFightsValidator(task_name, data_folder, validator_ext)
            elif command == 'autoBugfixes':
                settings = sublime.load_settings('CodeFights.sublime-settings')
                bug_limit = settings.get('bug_limit')
                self.thread = CodeFightsBugfixes(task_name, data_folder, 
                                                 file_ext, autoBugfixes_validate, bug_limit)
            elif command == 'getLimits':
                self.thread = CodeFightsGetLimits(task_name, data_folder, update_limits)
            elif command == 'styleChecker':
                if styleChecker_ext is None:
                    styleChecker_ext = file_ext
                self.thread = CodeFightsStyleChecker(task_name, data_folder, 
                                                     styleChecker_ext, styleChecker_fix)
            elif command == 'generateTests':
                if file_name[0] != 'tests':
                    self.to_panel('Tests file should be called "tests"!')
                    return
                self.thread = CodeFightsTestsGenerator(task_name, data_folder)
            else:
                self.to_panel("No command found!\n")
                return

            self.thread.start()
            self.handle_thread()
        else:
            self.to_panel("Something went wrong; is any file open?\n")

    def handle_thread(self):
        if self.thread is None:
            if self.killed:
                self.killed = False
            else:
                self.to_panel('No process to launch!\n')
            return

        if self.thread.is_alive():
            while not self.thread.queue.empty():
                line = self.thread.queue.get()
                self.to_panel(line)
            sublime.set_timeout(self.handle_thread, 100)
        while not self.thread.queue.empty():
            line = self.thread.queue.get()
            self.to_panel(line)
        if self.thread.result is True:
            self.to_panel('\nFinished successfully.\n')
        elif self.thread.result is False:
            self.to_panel('\nFinished with an error.\n')
            self.to_panel(self.thread.error)
        if self.thread.result is not None:
            self.view.run_command('revert')
            self.thread = None


    def to_panel(self, txt):
        if is_ST3():
            self.print_to_panel(txt)
        else:
            self.append_data(txt)

    def print_to_panel(self, txt):
        self.panel.run_command('code_fights_print', {'text' : txt})

    def append_data(self, data):
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.insert(edit, self.output_view.size(), data)
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)

    def show_tests_panel(self):
        if not hasattr(self, 'output_view'):
            self.output_view = self.view.window().get_output_panel("tests")
        self.clear_test_view()
        self.view.window().run_command("show_panel", {"panel": "output.tests"})

    def clear_test_view(self):
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.erase(edit, sublime.Region(0, self.output_view.size()))
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)


class CodeFightsPrintCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        self.view.insert(edit, self.view.size(), text)


class CodeFightsValidator(threading.Thread):
    def __init__(self, task_name, data_folder, ext):
        self.task_name = task_name
        self.data_folder = data_folder
        self.ext = ext
        self.result = None
        self.queue = queue.Queue()
        threading.Thread.__init__(self)

    def run(self):
        try:
            self.queue.put('Validation of task "{0}" started...\n'.format(self.task_name))

            if self.ext == 'md':
                self.ext = 'ALL'

            validator_path = os.path.join(self.data_folder, '_validator')

            def execute():
                popen = subprocess.Popen(['node', os.path.join(validator_path, 'validator.js'), 
                                          self.task_name, self.ext],
                                          cwd=validator_path,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                stdout_lines = iter(popen.stdout.readline, "")
                for stdout_line in stdout_lines:
                    if is_ST3():
                        stdout_line = stdout_line.decode('utf-8')
                        if stdout_line:
                            stdout_line = stdout_line.replace('[31m', '::==> ').\
                                                      replace('[39m', '')
                            yield stdout_line
                        else:
                            break                        
                    else:
                        yield stdout_line.replace('[31m', '::==> ').replace('[39m', '')

                popen.stdout.close()
                popen.wait()

            for line in execute():
                if 'Solution source(' in line:
                    line = '\n' + line
                self.queue.put(line)

            self.result = True
        except Exception as e:
            self.result = False
            self.error = str(e)


class CodeFightsOutputsGenerator(threading.Thread):
    def __init__(self, task_name, data_folder, start_ext=None):
        self.task_name = task_name
        self.data_folder = data_folder
        self.start_ext = start_ext
        self.result = None
        self.queue = queue.Queue()
        threading.Thread.__init__(self)

    def run(self):
        try:
            self.queue.put('Generating outputs for task "{0}"...\n'.format(self.task_name))

            try:
                generateOuputs_path = os.path.join(self.data_folder, '_utils', 
                                                   'generateOutputs', 'generateOutputs.py')
                generateOutputs = imp.load_source('generateOutputs', generateOuputs_path)
            except Exception as e:
                raise Exception(str(e) + '\n')

            exts = ['py', 'java', 'cpp', 'js']
            if self.start_ext in exts:
                pos = exts.index(self.start_ext)
                exts[0], exts[pos] = exts[pos], exts[0]

            final_ext = None
            for ext in exts:
                res = generateOutputs.main(["", self.task_name, ext, '-r'], False)
                if res:
                    final_ext = ext
                    break

            if final_ext is None:
                raise Exception('Failed to generate outputs.\n')
            else:
                self.queue.put('Generated from "{0}.{1}".\n'.format(self.task_name, final_ext))

            self.result = True
        except Exception as e:
            self.result = False
            self.error = str(e)


class CodeFightsBugfixes(threading.Thread):
    def __init__(self, task_name, data_folder, ext, validate, bug_limit):
        self.task_name = task_name
        self.data_folder = data_folder
        self.ext = ext
        self.result = None
        self.queue = queue.Queue()
        self.validate = validate
        self.bug_limit = bug_limit
        threading.Thread.__init__(self)

    def run(self):
        self.queue.put('at least I started')
        try:
            if self.ext != 'py':
                raise Exception('Launch from file with ".py" extension!\n')

            self.queue.put('Generating bufixes for task "{0}"...\n'.format(self.task_name))

            try:
                bugCollection_path = os.path.join(self.data_folder, '_utils', 
                                                     'automaticalBugfixes',
                                                     'bugCollection.py')
                imp.load_source('bugCollection', bugCollection_path)
                automaticalBugfixes_path = os.path.join(self.data_folder, '_utils', 
                                                        'automaticalBugfixes', 
                                                        'automaticalBugfixes.py')
                automaticalBugfixes = imp.load_source('automaticalBugfixes', 
                                                      automaticalBugfixes_path)
            except Exception as e:
                raise Exception(str(e) + '\n')

            stream = io.StringIO()
            args = [self.task_name, self.validate, self.bug_limit, stream]

            thread = threading.Thread(target=automaticalBugfixes.main, args=args)
            thread.start()
            cur_pos = 0
            while thread.is_alive():
                ln = stream.tell()
                if ln > cur_pos:
                    new_text = stream.getvalue()[cur_pos:]
                    self.queue.put(new_text)
                    cur_pos += len(new_text)
            ln = stream.tell()
            if ln > cur_pos:
                new_text = stream.getvalue()[cur_pos:]
                self.queue.put(new_text)
                cur_pos += len(new_text)                    
            stream.close()

            self.result = True

        except Exception as e:
            self.result = False
            self.error = str(e)


class CodeFightsGetLimits(threading.Thread):
    def __init__(self, task_name, data_folder, upd):
        self.task_name = task_name
        self.data_folder = data_folder
        self.upd = upd
        self.result = None
        self.queue = queue.Queue()
        threading.Thread.__init__(self)

    def run(self):
        try:
            self.queue.put('Fetching constraints for task "{0}"...\n'.format(self.task_name))

            try:
                getLimits_path = os.path.join(self.data_folder, '_utils', 
                                              'getLimits', 'getLimits.py')
                getLimits = imp.load_source('getLimits', getLimits_path)
            except Exception as e:
                raise Exception(str(e))

            for task, args_limits in getLimits.main(self.task_name, self.upd):
                self.queue.put('\n' + task + '\n')
                if isinstance(args_limits, list):
                    for arg in args_limits:
                        self.queue.put(str(arg) + '\n')
                else:
                    self.queue.put(args_limits + '\n')

            self.result = True

        except Exception as e:
            self.result = False
            self.error = str(e)


class CodeFightsStyleChecker(threading.Thread):
    def __init__(self, task_name, data_folder, task_ext, fix):
        self.task_name = task_name
        self.data_folder = data_folder
        self.task_ext = task_ext
        self.fix = fix
        self.result = None
        self.queue = queue.Queue()
        threading.Thread.__init__(self)

    def run(self):
        try:
            if self.task_ext == 'java':
                self.queue.put('codeStyleChecker for java is not supported.\n')
                return
            if self.task_ext == 'md':
                self.task_ext = 'js,cpp,py'

            try:
                codeStyleChecker_path = os.path.join(self.data_folder, '_utils', 
                                                     'codeStyleChecker', 'codeStyleChecker.py')
                codeStyleChecker = imp.load_source('codeStyleChecker', codeStyleChecker_path)
            except Exception as e:
                raise Exception(str(e))

            stream = io.StringIO()
            args = ["", self.task_name, self.task_ext]
            if self.fix:
                args.append('--fix')

            thread = threading.Thread(target=codeStyleChecker.main, args=(args, stream, ))
            thread.start()
            cur_pos = 0
            while thread.is_alive():
                ln = stream.tell()
                if ln > cur_pos:
                    new_text = stream.getvalue()[cur_pos:]
                    self.queue.put(new_text)
                    cur_pos += len(new_text)
            ln = stream.tell()
            if ln > cur_pos:
                new_text = stream.getvalue()[cur_pos:]
                self.queue.put(new_text)
                cur_pos += len(new_text)                    
            stream.close()

            self.result = True
        except Exception as e:
            self.result = False
            self.error = str(e)


class CodeFightsTestsGenerator(threading.Thread):
    def __init__(self, task_name, data_folder):
        self.task_name = task_name
        self.data_folder = data_folder
        self.result = None
        self.queue = queue.Queue()
        threading.Thread.__init__(self)

    def run(self):
        try:
            self.queue.put('Tests generations for task "{0}" started...\n'.format(self.task_name))

            generateTests_path = os.path.join(self.data_folder, '_utils', 'generateTests')

            def excecute():
                run_command = 'python2' if sys.platform.find('linux') != -1 else 'python'
                popen = subprocess.Popen([run_command, os.path.join(generateTests_path, 
                                                                    'generateTests.py'),
                                          self.task_name, '-o'],
                                         cwd=generateTests_path,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                stdout_lines = iter(popen.stdout.readline, '')
                for stdout_line in stdout_lines:
                    if is_ST3():
                        stdout_line = stdout_line.decode('utf-8')
                        if stdout_line:
                            stdout_line = stdout_line.replace('[31m', '::==> ').\
                                                      replace('[39m', '')
                            yield stdout_line
                        else:
                            break                        
                    else:
                        yield stdout_line.replace('[31m', '::==> ').replace('[39m', '')

                popen.stdout.close()
                popen.wait()

            for line in excecute():
                self.queue.put(line)

            self.result = True
        except Exception as e:
            self.result = False
            self.error = str(e)
