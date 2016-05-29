import sublime, sublime_plugin

import imp
import os
import shutil
import subprocess
import sys
import tempfile
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
            generateOutputs_or_validate=False,
            validator_ext=None, generator_ext=None,
            bugfixes_or_getLimits=False, 
            upd=None, bog_command=None,
            check_style=False, 
            style_checker_ext=None, style_fix=None,            
            kill=False):
        """Main command.

        Args:
            generateOutputs_or_validate -- launches on ctrl+shift+c
                validator_ext -- 'py', 'cpp', 'java', 'js', 'ALL'
                generator_ext -- where to start, 'py', 'cpp', 'java', 'js'
            bugfixes_or_getLimits -- launches on ctrl+shift+m
                upd -- getLimits key, if true updates README
                bog_command -- if None, command is determined by extension
                               if True, bugfixes is launched
                               if False, getLimits is launched
            check_style -- launches on ctrl+shift+h
                style_checker_ext -- 'py', 'cpp', 'java', 'js', 'ALL'
                style_fix -- if true, fixes solutions
            kill -- launches on ctrl+h
        """

        self.killed = False

        if kill:
            if self.thread is not None:
                self.thread = None
                self.killed = True
                self.to_panel("\nCodeFights execution killed.\n")
            return

        settings = sublime.load_settings('CodeFights.sublime-settings')

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
                self.to_panel("The file has no extension!\n")
                return

            if generateOutputs_or_validate:
                if generator_ext is not None or file_name[1] == 'json' and validator_ext is None:
                    if generator_ext is None:
                        generator_ext = settings.get('generate_from')
                    self.thread = CodeFightsOutputsGenerator(task_name, data_folder, generator_ext)
                elif validator_ext is not None or file_name[1] in ['py', 'js', 'java', 'cpp', 'md']:
                    if validator_ext is None:
                        validator_ext = file_name[1]
                    self.thread = CodeFightsValidator(task_name, data_folder, validator_ext)
                else:
                    self.to_panel("Incorrect file extension! Expected \
                        'py', 'java', 'cpp', 'js', 'json' or 'md'\n")
                    return
            elif bugfixes_or_getLimits:
                if bog_command is None and file_name[1] == 'py' or bog_command is True:
                    self.thread = CodeFightsBugfixes(task_name, data_folder, file_name[1], full_path)
                elif bog_command is None and file_name[1] == 'md' or bog_command is False:
                    self.thread = CodeFightsGetLimits(task_name, data_folder, upd)
                else:
                    self.to_panel("Incorrect file extension! Expected 'py' or 'md'\n")
                    return
            elif check_style:
                if style_checker_ext is None:
                    style_checker_ext = file_name[1]
                if style_checker_ext in ['py', 'java', 'js', 'cpp', 'md']:
                    self.thread = CodeFightsStyleChecker(task_name, data_folder, style_checker_ext, style_fix)
                else:
                    self.to_panel("Incorrect file extension! Expected \
                        'py', 'java', 'cpp', 'js', 'json' or 'md'\n")
                    return
            else:
                self.to_panel("Incorrect command!\n")
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
                                         cwd=validator_path, stdout=subprocess.PIPE)
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
    def __init__(self, task_name, data_folder, ext, full_path):
        self.task_name = task_name
        self.data_folder = data_folder
        self.ext = ext
        self.full_path = full_path
        self.result = None
        self.queue = queue.Queue()
        threading.Thread.__init__(self)

    def run(self):
        try:
            if self.ext != 'py':
                raise Exception('Launch from file with ".py" extension!\n')

            self.queue.put('Generating bufixes for task "{0}"...\n'.format(self.task_name))

            try:
                automaticalBugfixes_path = os.path.join(self.data_folder, '_utils', 
                                                        'automaticalBugfixes', 
                                                        'automaticalBugfixes.py')
                automaticalBugfixes = imp.load_source('automaticalBugfixes', 
                                                      automaticalBugfixes_path)
            except Exception as e:
                raise Exception(str(e) + '\n')

            bugfixes = automaticalBugfixes.addingBugfixes(["", self.task_name])
            fh, abs_path = tempfile.mkstemp()
            with open(abs_path, 'w') as temp_snippet:
                with open(self.full_path, 'r') as old_snippet:
                    for line in old_snippet:
                        temp_snippet.write('# ' + line)
            os.close(fh)
            os.remove(self.full_path)
            shutil.move(abs_path, self.full_path)
            with open(self.full_path, 'a') as snippet:
                snippet.write('\n')
                for line in bugfixes:
                    snippet.write(line)

            self.queue.put('Bugfixes generated.\n')
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
