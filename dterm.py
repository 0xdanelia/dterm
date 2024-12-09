import sys, os
import subprocess
import threading
import shlex

from PySide6.QtCore import Qt, QSize, QEvent, QObject
from PySide6.QtGui import QTextCursor, QFont, QColor, QScreen, QKeyEvent
from PySide6.QtWidgets import (QApplication, QMainWindow, QSizeGrip,
                               QWidget, QTextEdit, QPlainTextEdit, QPushButton, QLineEdit,
                               QVBoxLayout, QHBoxLayout)


keys = Qt.Key
mods = Qt.KeyboardModifier


# TODO: need to configure TermInfo for programs that expect it
# TODO: need to support shells other than bash
# TODO: setPlainText() clears the undo/redo history - need to save it separately or use a different function in some places
# TODO: need to implement tab-completion
# TODO: need to run expected "default" commands like 'shopt -s expand_aliases' and 'source .bashrc'
# TODO: need to interpret ansi codes (colors, buffer management, cursor movement, etc...)   https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
# TODO: need to interpret escape sequences like '\r' to move cursor to beginning of line, or '\t' to insert a tab character


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ### Window settings
        self.setWindowTitle('dterm')

        self.setGeometry(0, 0, 1000, 800)
        center = QScreen.availableGeometry(QApplication.primaryScreen()).center()
        geo = self.frameGeometry()
        geo.moveCenter(center)
        self.move(geo.topLeft())

        #self.statusBar()
        #self.setMinimumSize()
        #self.setMaximumSize()

        self.font = QFont()
        self.font.setFamily('Courier New')
        self.font.setPointSize(12)

        ### Text editor area
        self.text_edit_area = QTextEdit()  # TODO: this is slow to update very long lines - unsure if fixable
        self.text_edit_area.setFont(self.font)
        self.default_text_color = QColor(200, 200, 200)
        self.text_edit_area.setTextColor(self.default_text_color)

        # TODO: making copies of existing keyPressEvent functions is probably a bad practice
        self.text_edit_area_keyPressEvent = self.text_edit_area.keyPressEvent  # this saves original functionality of keyPressEvent()
        self.text_edit_area.keyPressEvent = self.text_edit_key_pressed  # this overrides keyPressEvent() for special functionality

        ### Command line area
        self.command_line_area = QPlainTextEdit()
        self.command_line_area.setFont(self.font)
        self.command_line_area.setFixedHeight(80)
        self.command_line_area.setLineWrapMode(QPlainTextEdit.NoWrap)

        # TODO: making copies of existing keyPressEvent functions is probably a bad practice
        self.command_line_area_keyPressEvent = self.command_line_area.keyPressEvent  # this saves original functionality of keyPressEvent()
        self.command_line_area.keyPressEvent = self.command_line_key_pressed  # this overrides keyPressEvent() for special functionality

        ### Run button
        self.run_button = QPushButton('Run')
        self.run_button.setFixedWidth(100)
        self.run_button.setFixedHeight(80)
        self.run_button.clicked.connect(self.btn_run_clicked)

        ### Layouts
        self.cmd_layout = QHBoxLayout()
        self.cmd_layout.addWidget(self.command_line_area)
        self.cmd_layout.addWidget(self.run_button)

        self.window_layout = QVBoxLayout()
        self.window_layout.addWidget(self.text_edit_area)
        self.window_layout.addLayout(self.cmd_layout)

        self.window_layout.setContentsMargins(10, 10, 10, 10)
        self.window_layout.setSpacing(20)

        self.window_widget = QWidget()
        self.window_widget.setLayout(self.window_layout)
        self.setCentralWidget(self.window_widget)

        self.command_line_area.setFocus()

        ### Background functionality
        self.bash = subprocess.Popen(['/bin/bash', '-i'], shell=True, bufsize=0, universal_newlines=False, text=False,
                                                               stdin=subprocess.PIPE,
                                                               stdout=subprocess.PIPE,
                                                               stderr=subprocess.PIPE)

        self.done = False  # this is to indicate to all threads whether they should exit or not

        self.command_history = []
        self.command_history_idx = None
        self.saved_command = None

        self.kill_label = QWidget()  # This widget exists just to signal the cleanup() function and end the program
        self.kill_label.windowTitleChanged.connect(self.cleanup)  # TODO: connecting via the window title change is janky

        # this widget is not visible - it is used to safely transfer standard output between threads
        self.stdout_buffer = QLineEdit()
        self.stdout_buffer.setMaxLength(1073741824)  # GiB - the default max length isn't very big
        # changing the window title triggers a signal for the main thread to run the update_text_area() function
        self.stdout_buffer.windowTitleChanged.connect(self.update_text_area)  # TODO: connecting via the window title change is janky

        # this thread is constantly reading from stdout and updating the buffer widget
        self.stdout_thread = threading.Thread(target=self.thread_read_from_stdout)
        self.stdout_thread.start()

        # this thread is constantly reading from stderr
        self.stderr_thread = threading.Thread(target=self.thread_read_from_stderr)
        self.stderr_thread.start()

        # this thread tries to detect if the background shell process exited or crashed
        self.monitor_thread = threading.Thread(target=self.thread_monitor_subprocess)
        self.monitor_thread.start()


    # click the button -> run the command
    def btn_run_clicked(self):
        cmd = self.command_line_area.toPlainText()
        self.run_command(cmd)
        self.command_line_area.setFocus()


    # meant to be called after the stdout_buffer is filled with new text
    # appends new text to the text area and clears the stdout_buffer so it is ready for more input
    def update_text_area(self):
        new_text = self.stdout_buffer.text()
        if new_text:
            self.stdout_buffer.clear()  # clear the buffer first so thread_read_from_stdout() can start filling it again right away
            self.text_edit_area.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)  # Moving cursor to end so that stdout appends to end
            # TODO: this function will be replaced
            self.process_ANSI_colors(new_text)
            #self.text_edit_area.insertPlainText(new_text)
            self.text_edit_area.ensureCursorVisible()  # scroll to the bottom  # TODO: may want to make this behavior optional


    # constantly queries the background shell process to see if it is still alive
    def thread_monitor_subprocess(self):
        print('thread_monitor_subprocess()  starting up')
        while not self.done:
            return_code = self.bash.poll()
            if return_code is not None:
                # communicate to the main thread that the shell has exited
                self.kill_label.setWindowTitle(str(return_code))
        print('thread_monitor_subprocess()  shutting down')


    # grab stdout and update the buffer widget which can then be read from the main thread
    def thread_read_from_stdout(self):
        print('thread_read_from_stdout()  starting up')
        name = 1
        while not self.done:
            try:
                while not self.done and self.stdout_buffer.text() != '':
                    # the update_text_area() function will clear the buffer after grabbing the contents
                    # wait until it is cleared before trying to fill buffer with new text
                    continue
                out = self.bash.stdout.read(1048576)  # MiB
                if out:
                    self.stdout_buffer.setText(out.decode())
                    # cycling the window title between "1" and "-1" triggers the update_text_area() function
                    name = name * -1
                    self.stdout_buffer.setWindowTitle(str(name))
            except Exception as e:
                print(f'Exception:{e}')
        print('thread_read_from_stdout()  shutting down')


    # grab stderr and just print it for now  # TODO: need to display stderr on main window somewhere
    def thread_read_from_stderr(self):
        print('thread_read_from_stderr()  starting up')
        while not self.done:
            try:
                err = self.bash.stderr.read(1048576)  # MiB
                if err:
                    print('\x1b[1;31m' + err.decode() + '\x1b[0m')  # style: bold + red, then reset style afterwards
            except Exception as e:
                print(e)
        print('thread_read_from_stderr()  shutting down')


    # sends the contents of the command box to the background shell to be executed as a command
    def run_command(self, cmd):
        self.command_line_area.setPlainText('')

        # save this command to history, but avoid saving duplicate commands back-to-back
        if cmd and (not self.command_history or self.command_history[-1] != cmd):
            self.command_history.append(cmd)

        # running a command resets any command history traversal (via UP and DOWN keys)
        self.command_history_idx = None
        self.saved_command = None

        # write the command to stdin - the newline character triggers the background shell to run the command
        self.bash.stdin.write(str.encode(cmd + '\n'))


    # handler for special keys pressed while the text area is in focus
    def text_edit_key_pressed(self, event):
        key = event.key()
        #print(f"KEY {key}")
        #text_cursor = self.text_edit_area.textCursor()

        # [CTRL] + [SHIFT] + [DOWN]  move cursor to command line area
        if key == keys.Key_Down and event.modifiers() == (mods.ShiftModifier | mods.ControlModifier):
            self.command_line_area.setFocus()

        # If a non-special key is pressed, use default functionality of QTextEdit.keyPressEvent()
        else:
            self.text_edit_area_keyPressEvent(event)


    # handler for special keys pressed while the command line is in focus
    def command_line_key_pressed(self, event):
        key = event.key()
        #print(f"KEY {key}")
        cmd = self.command_line_area.toPlainText()
        cmd_cursor = self.command_line_area.textCursor()

        # [ENTER]  execute the written command
        if key in [keys.Key_Enter, keys.Key_Return] and event.modifiers() != mods.ShiftModifier:
            # hitting enter with a blank command inserts a newline in the output area
            if not cmd:
                self.text_edit_area.append('')
                self.text_edit_area.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)
            else:
                self.run_command(cmd)

        # [SHIFT] + [ENTER]  inserts a newline instead of running the command
        elif key in [keys.Key_Enter, keys.Key_Return] and event.modifiers() == mods.ShiftModifier:
            self.command_line_area.insertPlainText('\n')

        # [CTRL] + [SHIFT] + [UP]  move cursor to text edit area
        elif key == keys.Key_Up and event.modifiers() == (mods.ShiftModifier | mods.ControlModifier):
            self.text_edit_area.setFocus()

        # [UP]  cycle up through command history - only if cursor is on first line of command text area - skip if earliest history command is already selected
        elif key == keys.Key_Up and cmd_cursor.block().blockNumber() == 0 and not event.modifiers() and self.command_history and self.command_history_idx != 0:
            if self.command_history_idx is None:
                # no history item selected, save current command text and scroll back to most recently executed command
                self.command_history_idx = len(self.command_history) - 1
                self.saved_command = cmd
            else:
                self.command_history_idx -= 1

            self.command_line_area.setPlainText(self.command_history[self.command_history_idx])
            self.command_line_area.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)

        # [DOWN]  cycle down through command history - only if cursor is on last line of command text area - skip if no history command is currently selected
        elif key == keys.Key_Down and cmd_cursor.block().blockNumber() == self.command_line_area.blockCount() - 1 and not event.modifiers() and self.command_history_idx is not None:
            self.command_history_idx += 1
            if self.command_history_idx == len(self.command_history):
                # scrolled past most recent history command and back to saved command text
                self.command_history_idx = None
                self.command_line_area.setPlainText(self.saved_command)
                self.command_line_area.moveCursor(QTextCursor.EndOfBlock, QTextCursor.MoveAnchor)

            elif self.command_history_idx > 0:
                self.command_line_area.setPlainText(self.command_history[self.command_history_idx])
                self.command_line_area.moveCursor(QTextCursor.EndOfBlock, QTextCursor.MoveAnchor)

        # If a non-special key is pressed, use default functionality of QPlainTextEdit.keyPressEvent()
        else:
            self.command_line_area_keyPressEvent(event)


    # TODO: this code is awful - just a quick proof of concept for basic colors
    # TODO: need a module to parse text for both ANSI codes and escape sequences for handling
    # echo -e "default\e[31mred\e[32mgreen\e[33myellow\e[34mblue\e[35mmagenta\e[36mcyan\e[30mblack\e[37mwhite\e[0mdefault"
    def process_ANSI_colors(self, text):
        white = QColor(255, 255, 255)
        red = QColor(255, 0, 0)
        green = QColor(0, 255, 0)
        blue = QColor(0, 0, 255)
        cyan = QColor(0, 255, 255)
        magenta = QColor(255, 0 ,255)
        yellow = QColor(255, 255, 0)
        black = QColor(0, 0, 0)

        lines = text.split('\n')
        is_first_line = True

        for line in lines:
            if not is_first_line:
                # the previous line must have ended in a newline if we hit this code, so insert it here
                self.text_edit_area.insertPlainText('\n')
            is_first_line = False

            if '' not in line:
                # lines without escape characters can just be printed as is
                self.text_edit_area.insertPlainText(line)
            else:
                escapes = line.split('')
                if not line.startswith(''):
                    # if the first character is not an escape, then the first element after the split is just regular text
                    self.text_edit_area.insertPlainText(escapes[0])

                # if the first character in the line is an escape, then the first element here is just an empty string due to the split
                # if the first character is not an escape, then the first element here was already printed above
                # either way, skip the first element here
                for esc in escapes[1:]:
                    if esc.startswith('[0m'):
                        self.text_edit_area.setTextColor(self.default_text_color)
                        self.text_edit_area.insertPlainText(esc[3:])
                    elif esc.startswith('[37m'):
                        self.text_edit_area.setTextColor(white)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[31m'):
                        self.text_edit_area.setTextColor(red)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[32m'):
                        self.text_edit_area.setTextColor(green)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[33m'):
                        self.text_edit_area.setTextColor(yellow)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[34m'):
                        self.text_edit_area.setTextColor(blue)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[35m'):
                        self.text_edit_area.setTextColor(magenta)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[36m'):
                        self.text_edit_area.setTextColor(cyan)
                        self.text_edit_area.insertPlainText(esc[4:])
                    elif esc.startswith('[30m'):
                        self.text_edit_area.setTextColor(black)
                        self.text_edit_area.insertPlainText(esc[4:])
                    else:
                        # any escape sequences not handled above are just printed as is (with the escape character included)
                        self.text_edit_area.insertPlainText('' + esc)


    # kill the background shell process and set the 'done' flag so that the various threads know to shut themselves down
    def cleanup(self, code=0):
        self.done = True
        self.bash.kill()
        sys.exit(code)


# entry point
if __name__ == '__main__':
    app = QApplication()

    window = MainWindow()
    window.show()

    try:
        app.exec()
    except:
        window.cleanup(1)  # TODO: need more robust exit code management
    window.cleanup(0)
