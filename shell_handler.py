import pty
import sys, os, io, select
import subprocess, signal
import queue


class ShellHandler:
    def __init__(self):
        # could instead use separate ptys for stdin/stdout, but doing so seems to make the shell think there is no "controlling terminal"
        self.std_io, std_io_write = pty.openpty()

        self.q_stdin = queue.Queue()
        self.q_stdout = queue.Queue()

        self.done = False

        # this runs a custom config on startup in addition to .bashrc
        #self.proc = subprocess.Popen(['/bin/bash --init-file <(echo "source ~/.bashrc ; source .dtermrc")'],
        self.proc = subprocess.Popen(['/bin/bash -i'],
                                                          shell=True,
                                                          start_new_session=True,
                                                          stdin=std_io_write,
                                                          stdout=std_io_write,
                                                          stderr=std_io_write)

    # writes a command to stdin, followed by a newline, which triggers the background process to run that command
    def run_command(self, cmd):
        # ctrl+u  to clear any in-progress commands  # TODO: this will overwrite any currently yanked strings
        self.q_stdin.put(b'\x15')
        # commands with tab characters will trigger tab-completion - add the "verbatim" character to actually print a tab
        self.q_stdin.put(str.encode(cmd.replace('\t', '\x16\t') + '\n'))


    # writes an incomplete command to stdin, followed by a tab, which triggers tab completion in the shell
    def first_tab(self, cmd):
        # ctrl+u  to clear any in-progress commands  # TODO: this will overwrite any currently yanked strings
        self.q_stdin.put(b'\x15')
        self.q_stdin.put(str.encode(cmd + '\t'))


    def second_tab(self, cmd):
        # ctrl+u  to clear any in-progress commands  # TODO: this will overwrite any currently yanked strings
        self.q_stdin.put(b'\x15')
        self.q_stdin.put(str.encode(cmd + '\t\t'))  # yes, this has to be two MORE tab characters


    def thread_handle_io(self):
        # creating local variables here rather than calling self.obj over and over again (I wonder how many nanoseconds this saves?)
        std_io = self.std_io

        q_stdin = self.q_stdin
        q_stdout = self.q_stdout

        while not self.done:
            # returns lists of files which are non-blocked and available for read or write
            rlist, wlist, xlist = select.select([std_io], [std_io], [])

            # read from stdout/stderr
            if rlist:
                data = os.read(std_io, 1048576)  # MiB
                if data:
                    q_stdout.put(data)
                    continue

            # if stdin is available for writing, and there is a command in the queue, write that command
            if q_stdin.qsize() and wlist:
                os.write(std_io, q_stdin.get())
