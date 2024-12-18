import pty
import sys, os, io, select
import subprocess, signal
import threading
import shlex
import re

from PySide6.QtCore import Qt, QSize, QEvent, QObject, Signal, QThread
from PySide6.QtGui import QTextCursor, QFont, QColor, QScreen, QKeyEvent
from PySide6.QtWidgets import (QApplication, QMainWindow, QSizeGrip,
                               QWidget, QTextEdit, QPlainTextEdit, QPushButton, QLineEdit,
                               QVBoxLayout, QHBoxLayout)

from main_window import MainWindow
from shell_handler import ShellHandler
from key_handler import KeyHandler


# TODO: need to configure TermInfo for programs that expect it
# TODO: need to support shells other than bash
# TODO: need to handle setPlainText() (and other functions?) clearing the undo/redo history
# TODO: need to interpret ansi codes (colors, buffer management, cursor movement, etc...)   https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
# TODO: need to interpret escape characters like '\r' to move cursor to beginning of line
# TODO: need to pass signals (like ctrl+c to terminate process) to the shell subprocess
# TODO: need to be able to interact with programs that "take over" the terminal - ex:  less, vim, htop
# TODO: need to implement a "password mode" for the cmd area AND ensure that the handling of said password is secure (likely with a professional audit, someday)


# TODO: might be useful to keep track of any child processes created from the shell -  "pgrep -P <bash.pid>"  or  "pstree"  may be helpful - "jobs" command for commands run with "&"
# TODO: setting stdout to NONBLOCK might improve speed (if possible)  https://stackoverflow.com/questions/8980050/persistent-python-subprocess
# TODO: speed optimizations everywhere - prioritize reading STDOUT and writing to the text area


# constantly reads a given queue, and then sends the resulting text to a given function via qt signals
class QueueReader(QThread):
    signal = Signal(str)

    def __init__(self, queue, func):
        super().__init__()
        self.queue = queue
        self.signal.connect(func)
        self.done = False

    def run(self):
        q = self.queue
        s = self.signal
        while not self.done:
            text = q.get().decode('utf-8')
            s.emit(text)


# constantly queries the background shell process to see if it is still alive
def thread_monitor_subprocess():
    global done
    while not done:
        return_code = shell.proc.poll()
        if return_code is not None:
            # communicate to the main thread that the shell has exited
            done = True
            cleanup(0)


# click the button -> run the command
def btn_run_clicked():
    cmd = win.cmd_area.toPlainText()
    win.cmd_area.setPlainText('')
    shell.run_command(cmd)
    win.cmd_area.setFocus()


def cleanup(exit_code=0):
    for r in readers:
        r.done = True
        r.queue.put(b' ')
    shell.proc.kill()
    shell.done = True
    app.exit()
    exit(exit_code)


# entry point
if __name__ == '__main__':
    done = False
    readers = []
    shell = ShellHandler()
    #print(f'Starting process  {shell.proc.pid} : {" ".join(shell.proc.args)}')

    key_handler = KeyHandler()

    app = QApplication()
    win = MainWindow(key_handler)
    win.run_button.clicked.connect(btn_run_clicked)

    key_handler.win = win
    key_handler.shell = shell

    win.show()

    io_thread = threading.Thread(target=shell.thread_handle_io)
    io_thread.start()

    stdout_reader = QueueReader(shell.q_stdout, win.append_stdout_to_text_area)
    readers.append(stdout_reader)

    stdout_reader_thread = threading.Thread(target=stdout_reader.run)
    stdout_reader_thread.start()

    monitor_thread = threading.Thread(target=thread_monitor_subprocess)
    monitor_thread.start()

    try:
        app.exec()
    except:
        # TODO: this should probably be more robust
        cleanup(1)
        pass
    cleanup(0)
