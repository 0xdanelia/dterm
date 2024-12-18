import sys, os, io, select
import subprocess, signal
import shlex
import re

from PySide6.QtCore import Qt, QSize, QEvent, QObject, Slot
from PySide6.QtGui import QTextCursor, QFont, QColor, QScreen, QKeyEvent


keys = Qt.Key
mods = Qt.KeyboardModifier


class KeyHandler(QObject):

    def __init__(self):
        super().__init__()
        self.win = None
        self.shell = None

    # handler for special keys pressed while the text area is in focus
    def text_edit_key_pressed(self, event):
        key = event.key()
        # print(f"KEY {key}")
        # text_cursor = self.text_area.textCursor()

        # [CTRL] + [SHIFT] + [DOWN]  move cursor to command line area
        if key == keys.Key_Down and event.modifiers() == (mods.ShiftModifier | mods.ControlModifier):
            self.win.cmd_area.setFocus()

        # If a non-special key is pressed, use default functionality of QTextEdit.keyPressEvent()
        else:
            self.win.text_area_keyPressEvent(event)


    # handler for special keys pressed while the command line is in focus
    def command_line_key_pressed(self, event):
        key = event.key()
        # print(f"KEY {key}    MOD {event.modifiers()}")
        cmd = self.win.cmd_area.toPlainText()

        # tab completion works by hitting [TAB] twice - check here if we are expecting the second tab
        if self.win.first_tab and key == keys.Key_Tab and not event.modifiers():
            self.win.first_tab = False
            self.win.second_tab = True
            self.shell.second_tab(cmd)
            return

        self.win.first_tab = False
        self.win.first_tab_first_line = True
        self.win.second_tab = False
        self.win.second_tab_first_line = True

        # [ENTER]  execute the written command
        if key in [keys.Key_Enter, keys.Key_Return] and not event.modifiers():
            if not cmd:
                # hitting enter with a blank command inserts a newline in the output area
                # TODO: should also reset the html style to the default
                #self.win.text_area.appendHtml('')
                self.shell.run_command('')
                self.win.text_area.moveCursor(QTextCursor.End)
            else:
                # if the command contains unclosed quotes, instead just insert a newline
                if not self.check_unclosed_chars(cmd):
                    self.win.cmd_area.insertPlainText('\n')
                    self.win.cmd_area.ensureCursorVisible()
                    return

                # run the command
                self.win.cmd_area.setPlainText('')
                # add the cmd to history (avoiding back-to-back duplicates)
                if not self.win.cmd_history or cmd != self.win.cmd_history[-1]:
                    self.win.cmd_history.append(cmd)
                self.win.history_idx = -1
                self.win.in_progress_cmd = ''
                self.shell.run_command(cmd)

        # [SHIFT] + [ENTER]  inserts a newline instead of running the command
        elif key in [keys.Key_Enter, keys.Key_Return] and event.modifiers() == mods.ShiftModifier:
            self.win.cmd_area.insertPlainText('\n')

        # [CTRL] + [SHIFT] + [ENTER]  force submit the command
        # this overwrites the "helpful" checks to make sure quotes, parens, and brackets are properly closed
        elif key in [keys.Key_Enter, keys.Key_Return] and event.modifiers() == (mods.ShiftModifier | mods.ControlModifier):
            self.win.cmd_area.setPlainText('')
            self.shell.run_command(cmd)
            # add the cmd to history (avoiding back-to-back duplicates)
            if not self.win.cmd_history or cmd != self.win.cmd_history[-1]:
                self.win.cmd_history.append(cmd)
            self.win.history_idx = -1
            self.win.in_progress_cmd = ''

        # [TAB]  use bash-completion rules to autofill the command text box
        elif key == keys.Key_Tab and not event.modifiers():
            self.win.first_tab = True
            self.shell.first_tab(cmd)

        # [CTRL] + [SHIFT] + [c]  send SIGINT  (what ctrl+c does on standard terminals)
        elif key == keys.Key_C and event.modifiers() == (mods.ShiftModifier | mods.ControlModifier):
            # self.bash.send_signal(signal.SIGINT)
            os.killpg(os.getpgid(self.shell.proc.pid), signal.SIGINT)

        # [CTRL] + [SHIFT] + [UP]  move cursor to text edit area
        elif key == keys.Key_Up and event.modifiers() == (mods.ShiftModifier | mods.ControlModifier):
            self.win.text_area.setFocus()

        # [UP]  send signal to cycle through command history
        elif key == keys.Key_Up and not event.modifiers():
            # first save the current cursor position and treat the key press as normal
            pos = self.win.cmd_area.textCursor().position()
            self.win.cmd_area_keyPressEvent(event)

            # if the cursor position did not change, then cycle command history
            if self.win.cmd_area.textCursor().position() == pos:
                self.cmd_history_up(cmd)

        # [DOWN]  send signal to cycle through command history
        elif key == keys.Key_Down and not event.modifiers():
            # first save the current cursor position and treat the key press as normal
            pos = self.win.cmd_area.textCursor().position()
            self.win.cmd_area_keyPressEvent(event)

            # if the cursor position did not change, then cycle command history
            if self.win.cmd_area.textCursor().position() == pos:
                self.cmd_history_down(cmd)

        # If a non-special key is pressed, use default functionality of QPlainTextEdit.keyPressEvent()
        else:
            self.win.cmd_area_keyPressEvent(event)

        self.win.cmd_area.ensureCursorVisible()


    def cmd_history_up(self, cmd):
        history = self.win.cmd_history
        # if no historical command is selected, save the in-progress cmd and cycle to previous command
        if self.win.history_idx == -1 and history:
            self.win.in_progress_cmd = cmd
            self.win.history_idx = len(history) - 1
            self.win.cmd_area.setPlainText(history[self.win.history_idx])
            self.win.cmd_area.moveCursor(QTextCursor.End)

        # if we are already cycling through history, and not on the first item, scroll back one more item
        elif self.win.history_idx > 0 and history:
            self.win.history_idx -= 1
            self.win.cmd_area.setPlainText(history[self.win.history_idx])
            self.win.cmd_area.moveCursor(QTextCursor.End)


    def cmd_history_down(self, cmd):
        history = self.win.cmd_history
        # if no historical command is selected,do nothing
        if self.win.history_idx == -1:
            return
        # otherwise cycle to the next most recent command
        self.win.history_idx += 1
        # if we cycled past the most recent command, instead load the saved in-progress command
        if self.win.history_idx == len(history):
            self.win.history_idx = -1
            self.win.cmd_area.setPlainText(self.win.in_progress_cmd)
            self.win.cmd_area.moveCursor(QTextCursor.EndOfBlock)
        else:
            self.win.cmd_area.setPlainText(history[self.win.history_idx])
            self.win.cmd_area.moveCursor(QTextCursor.EndOfBlock)


    # checks if quotes, parens, and brackets are closed
    def check_unclosed_chars(self, cmd):
        inside_quote = ''
        open_paren = 0
        open_bracket = 0
        open_curly = 0
        escape = False

        for char in cmd:
            # skip any escaped characters
            if escape:
                escape = False
                continue

            if char == '\\':
                escape = True
                continue

            # wait for closing quote
            if inside_quote:
                if char == inside_quote:
                    inside_quote = ''
                continue

            if char in '\'"`':
                inside_quote = char

            elif char == '(':
                open_paren += 1
            elif char == ')':
                open_paren -= 1

            elif char == '[':
                open_bracket += 1
            elif char == ']':
                open_bracket -= 1

            elif char == '{':
                open_curly += 1
            elif char == '}':
                open_curly -= 1

            if open_paren < 0 or open_bracket < 0 or open_curly < 0:
                return False

        return inside_quote == '' and open_paren == 0 and open_bracket == 0 and open_curly == 0 and escape == False
