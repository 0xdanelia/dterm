import html
import re
import datetime
import os, sys
import subprocess

from PySide6.QtCore import Qt, QSize, QEvent, QObject, Slot
from PySide6.QtGui import QTextCursor, QFont, QColor, QScreen, QKeyEvent
from PySide6.QtWidgets import (QApplication, QMainWindow, QSizeGrip,
                               QWidget, QTextEdit, QPlainTextEdit, QPushButton, QLineEdit,
                               QVBoxLayout, QHBoxLayout, QLabel)

from ansi_to_html import HtmlStyle
from ansi_parser import AnsiParser


class MainWindow(QMainWindow):
    def __init__(self, key_handler):
        super().__init__()

        ### Window settings
        self.setWindowTitle('dterm')

        # set initial window size and open in center of screen
        self.setGeometry(0, 0, 1200, 1000)
        center = QScreen.availableGeometry(QApplication.primaryScreen()).center()
        geo = self.frameGeometry()
        geo.moveCenter(center)
        self.move(geo.topLeft())

        # TODO: consider implementing:
        #self.statusBar()
        #self.setMinimumSize()
        #self.setMaximumSize()

        self.font = QFont()
        self.font.setFamily('Courier New')
        self.font.setPointSize(12)

        ### Text editor area
        self.text_area = QPlainTextEdit()
        self.text_area.setFont(self.font)
        self.stdout_html_style = HtmlStyle()
        self.stdout_ansi_parser = AnsiParser(self.stdout_html_style)
        self.stderr_html_style = HtmlStyle()
        self.stderr_ansi_parser = AnsiParser(self.stderr_html_style)
        #self.default_text_color = QColor(248, 248, 255)  # GhostWhite
        #self.text_area.setTextColor(self.default_text_color)  # TODO: PlainTextEdit does not have this setTextColor option

        # TODO: making copies of existing keyPressEvent functions is probably a bad practice
        self.text_area_keyPressEvent = self.text_area.keyPressEvent  # this saves original functionality of keyPressEvent()
        self.text_area.keyPressEvent = key_handler.text_edit_key_pressed  # this overrides keyPressEvent() for special functionality

        ### Command line area
        self.cmd_area = QPlainTextEdit()
        self.cmd_area.setFont(self.font)
        self.cmd_area.setFixedHeight(90)  # displays 4 lines nicely at 12 point font
        #self.cmd_area.setLineWrapMode(QPlainTextEdit.NoWrap)

        # TODO: making copies of existing keyPressEvent functions is probably a bad practice
        self.cmd_area_keyPressEvent = self.cmd_area.keyPressEvent  # this saves original functionality of keyPressEvent()
        self.cmd_area.keyPressEvent = key_handler.command_line_key_pressed  # this overrides keyPressEvent() for special functionality

        # separate area for displaying PS1 rather than in the text area
        self.ps1_area = QPlainTextEdit()
        self.ps1_area.setReadOnly(True)
        self.ps1_area.setFixedHeight(30)
        self.ps1_area.setPlainText(os.environ.get('PS1'))

        ### Run button
        self.run_button = QPushButton('Run')
        self.run_button.setFixedWidth(100)
        self.run_button.setFixedHeight(40)

        ### Layouts
        self.cmd_layout = QHBoxLayout()
        self.cmd_layout.addWidget(self.cmd_area)
        self.cmd_layout.addWidget(self.run_button)

        self.window_layout = QVBoxLayout()
        self.window_layout.addWidget(self.text_area)
        #self.window_layout.addWidget(self.ps1_area)
        self.window_layout.addLayout(self.cmd_layout)

        self.window_layout.setContentsMargins(10, 10, 10, 10)
        self.window_layout.setSpacing(20)

        self.window_widget = QWidget()
        self.window_widget.setLayout(self.window_layout)
        self.setCentralWidget(self.window_widget)

        self.cmd_area.setFocus()

        ### Backend functionality
        self.cmd_history = []
        self.history_idx = -1
        self.in_progress_cmd = ''

        # flags to assist with parsing tab-completion output
        self.first_tab = False
        self.first_tab_first_line = True
        self.second_tab = False
        self.second_tab_first_line = True


    @Slot(str)
    def append_stdout_to_text_area(self, text):
        self.text_area.moveCursor(QTextCursor.End)

        # parse text for any ansi color codes and convert them to html styles
        self.stdout_ansi_parser.new(html.escape(text))
        parsed = self.stdout_ansi_parser.parse_ansi()

        # when expecting results from tab-completion, handle them differently than regular text
        if self.first_tab:
            self.handle_first_tab_completion(parsed)
            return
        elif self.second_tab:
            parsed = self.handle_second_tab_completion(parsed)

        html_text = str(self.stdout_html_style) + parsed.replace('\x07', '')

        # appendHtml() inserts a newline at the start of its output
        # to delete that newline, we need to keep track of the current EOF position and return to it after appending
        cursor = self.text_area.textCursor()
        pos = cursor.position()
        self.text_area.appendHtml(html_text)

        # return to the beginning of the new html and delete the inserted newline
        # TODO: this action is saved in the undo/redo history - see if it can be deleted from there
        cursor.setPosition(pos)
        self.text_area.setTextCursor(cursor)
        self.text_area.textCursor().deleteChar()

        self.text_area.moveCursor(QTextCursor.End)


    # TODO: tab completion is a mess, even though current iteration (seemingly) works (on my machine)
    # TODO: the biggest issue comes from the incomplete command being printed out twice - at both the start and end
    # TODO: the second biggest issue is that the output is a stream and it does not always arrive all at once, and it is laced with escape characters
    # TODO: should implement a more easy to understand solution that captures output and filters out these repeated commands and escape characters
    # TODO: maybe can get this working:  # https://unix.stackexchange.com/questions/25935/how-to-output-string-completions-to-stdout/31023#31023
    # if [TAB] is pressed once, auto-complete the current command as much as possible
    def handle_first_tab_completion(self, parsed):

        for text in parsed.split('\x07'):

            # tab completion output comes in two parts:
            # 1 - a repeat of the command, with some possible escape codes
            # 2 - the viable auto-complete text (if available), with some possible escape codes
            if self.first_tab_first_line:
                text = text.replace('\r', '')

                # once we see the repeated command, set flag to parse completion results next time
                if text == self.cmd_area.toPlainText():
                    self.first_tab_first_line = False

                # if we see a line at this point that begins with our command, then the completed command is already appeneded
                elif text.startswith(self.cmd_area.toPlainText()):
                    text = text.replace(self.cmd_area.toPlainText(), '')
                    self.cmd_area.textCursor().movePosition(QTextCursor.End)
                    self.cmd_area.insertPlainText(text)
                    self.first_tab = False
                    self.first_tab_first_line = True
                    return

            else:
                # after the repeated command is found and removed, any remaining text is a completion result
                if text:
                    # if we get completion results, append them to the current command
                    self.cmd_area.textCursor().movePosition(QTextCursor.End)
                    self.cmd_area.insertPlainText(text)
                    self.first_tab = False
                    self.first_tab_first_line = True
                    return


    def handle_second_tab_completion(self, text):
        cmd = self.cmd_area.toPlainText()
        text = text.replace('\x07', '').replace('\r', '')

        # there is a repeat of the command at the start and end of the completion results that we want to remove
        if self.second_tab_first_line:
            if text.startswith(cmd):
                text = text.replace(cmd, '', 1)
                self.second_tab_first_line = False

        if not self.second_tab_first_line and text.endswith(cmd):
            # replace once from the right
            text = ''.join(text.rsplit(cmd, 1))
            self.second_tab = False
            self.second_tab_first_line = True
        return text
