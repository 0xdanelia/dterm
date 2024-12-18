from ansi_to_html import parse_style_codes


# https://www.man7.org/linux/man-pages/man4/console_codes.4.html

# https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
# https://notes.burke.libbey.me/ansi-escape-codes/


ESC = '\x1b'
BELL = '\x07'
BACKSPACE = '\x08'


class AnsiParser:

    def __init__(self, style):
        # this maps a type of ansi code to a function to handle it
        self.sequence_type_functions = {
            'm': self.handle_color_codes,

            '?l': self.handle_private_modes,
            '?h': self.handle_private_modes,

            'OSC': self.handle_os_commands,
        }

        self.text = ''
        self.output = ''
        self.idx = 0
        self.style = style
        self.codes = []
        self.code_type = ''


    # this resets all parsing variables to prepare for a new parse
    def new(self, text):
        self.text = text #  .replace('\r\n', '\n')  # might be easier to just delete carriage returns that appear with a newline
        self.output = ''
        self.idx = 0
        self.codes = []
        self.code_type = ''


    # TODO: STDOUT/STDERR is read in chunks - need to detect + handle if the border of a chunk cuts off an ANSI sequence
    # find and handle all ansi codes in a string of text
    # return the result of handling each code within the text
    def parse_ansi(self):

        while self.idx < len(self.text):
            # read one character at a time
            char = self.text[self.idx]

            # TODO: in terminals, carriage return means "move cursor all the way left", then any printed characters will overwrite existing text
            # TODO:  echo -e '12345\rabc'  ->  abc45
            #if char == '\r':
            #    last_newline = self.output.rfind('\n')
            #    if last_newline == -1:
            #        self.output = ''
            #    else:
            #        self.output = self.output[:last_newline + 1]
            #    self.idx += 1
            #    continue

            if char == BACKSPACE:
                self.output = self.output[:-1]
                self.idx += 1
                continue

            # TODO: I currently use the bell to help organize tab-completion output, otherwise it can just be skipped here
            #if char == BELL:
            #   print('\a')
            #    self.idx += 1
            #    continue

            # ansi sequences begin with an ESC
            if char == ESC:
                self.parse_sequence()

                # parsing the sequence results in a sequence type, which is associated with handler function for that particular ansi code
                if self.code_type and self.code_type in self.sequence_type_functions.keys():
                    self.sequence_type_functions[self.code_type]()

                # reset current codes before parsing the next one
                self.codes = []
                self.code_type = ''

            # regular characters are just added to the output string as-is
            else:
                self.output += char

            self.idx += 1

        return self.output


    # each type of sequence begins with ESC
    # the second character in the sequence determines what kind of code it is
    def parse_sequence(self):
        # increment idx to skip over ESC character
        self.idx += 1

        if self.text[self.idx] == ']':
            self.parse_os_command()

        elif self.text[self.idx] != '[':
            self.parse_private_cursor_control()

        # all sequences from this point on begin with ESC [
        elif self.text[self.idx + 1] == '=':
            self.parse_screen_mode()

        elif self.text[self.idx + 1] == '?':
            self.parse_private_mode()

        else:
            self.parse_control_sequence()


    # ESC [ num letter
    # ESC [ num ; num letter
    # includes colors and styles
    def parse_control_sequence(self):
        self.idx += 1

        current_code = ''
        while self.idx < len(self.text):
            char = self.text[self.idx]

            # numbers are part of a code
            if char.isnumeric():
                current_code += char

            # ; separates multiple codes
            elif char == ';':
                self.codes.append(int(current_code))
                current_code = ''

            else:
                if current_code:
                    self.codes.append(int(current_code))
                self.code_type = char
                return

            self.idx += 1


    # ESC [= num h
    # ESC [= num l
    def parse_screen_mode(self):
        pass


    # ESC [? num h
    # ESC [? num l
    def parse_private_mode(self):
        self.idx += 2

        current_code = ''
        while self.idx < len(self.text):
            char = self.text[self.idx]

            # numbers are part of a code
            if char.isnumeric():
                current_code += char

            else:
                if current_code:
                    self.codes.append(int(current_code))
                self.code_type = '?' + char
                return

            self.idx += 1


    # ESC ] num ; text ESC \
    # ESC ] num ; text BEL
    def parse_os_command(self):
        self.idx += 1

        current_code = ''
        while self.idx < len(self.text):
            char = self.text[self.idx]

            # this code expects only one ; seperator
            # note that only the first code in this sequence is necessarily numeric
            if char == ';' and len(self.codes) == 0:
                self.codes.append(int(current_code))
                current_code = ''

            # this sequence ends when it encounters the BEL character or ESC \  (backslash)
            elif char in [BELL, '\\']:
                if current_code:
                    self.codes.append(current_code)
                self.code_type = 'OSC'
                return

            # all other characters are captured by this code
            else:
                current_code += char

            self.idx += 1


    # ESC M
    # ESC 7
    # ESC 8
    def parse_private_cursor_control(self):
        pass


    def handle_color_codes(self):
        parse_style_codes(self.codes, self.style)
        self.output += str(self.style)


    def handle_private_modes(self):
        pass


    def handle_os_commands(self):
        pass
