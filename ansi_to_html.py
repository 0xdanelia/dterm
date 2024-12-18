import html

# https://www.man7.org/linux/man-pages/man4/console_codes.4.html

# https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
# https://notes.burke.libbey.me/ansi-escape-codes/


# echo -e "default\e[31mred\e[32mgreen\e[33myellow\e[34mblue\e[35mmagenta\e[36mcyan\e[30mblack\e[37mwhite\e[0mdefault"
# echo -e "default\e[91mred\e[92mgreen\e[93myellow\e[94mblue\e[95mmagenta\e[96mcyan\e[90mblack\e[97mwhite\e[0mdefault"
# echo -e "\e[38;2;50;100;150m\e[48;2;250;200;150mhello world"

class HtmlStyle:
    def __init__(self):
        self.background_color = 'transparent'
        self.text_color = 'GhostWhite'
        self.is_bold = False
        self.is_italic = False

        self.code_map = {
            # TODO: base settings should be configurable - the defaults should probably detect dark/light desktop themes and adjust themselves
            0: lambda: self.set_default(),
            1: lambda: self.set_is_bold('bold'),
            3: lambda: self.set_is_italic('italic'),

            30: lambda: self.set_text_color('black'),
            31: lambda: self.set_text_color('Crimson'),
            32: lambda: self.set_text_color('LimeGreen'),
            33: lambda: self.set_text_color('LemonChiffon'),  # yellow
            34: lambda: self.set_text_color('DeepSkyBlue'),
            35: lambda: self.set_text_color('Orchid'),  # magenta
            36: lambda: self.set_text_color('Aqua'),  # cyan
            37: lambda: self.set_text_color('GhostWhite'),
            39: lambda: self.set_text_color('GhostWhite'),  # default

            40: lambda: self.set_background_color('black'),
            41: lambda: self.set_background_color('Crimson'),
            42: lambda: self.set_background_color('LimeGreen'),
            43: lambda: self.set_background_color('LemonChiffon'),
            44: lambda: self.set_background_color('DeepSkyBlue'),
            45: lambda: self.set_background_color('Orchid'),
            46: lambda: self.set_background_color('Aqua'),
            47: lambda: self.set_background_color('GhostWhite'),
            49: lambda: self.set_background_color('transparent'),  # default

            90: lambda: self.set_text_color('LightSlateGray'),
            91: lambda: self.set_text_color('LightCoral'),
            92: lambda: self.set_text_color('LightGreen'),
            93: lambda: self.set_text_color('LightYellow'),
            94: lambda: self.set_text_color('LightSkyBlue'),
            95: lambda: self.set_text_color('LightPink'),
            96: lambda: self.set_text_color('LightCyan'),
            97: lambda: self.set_text_color('LightGray'),

            100: lambda: self.set_background_color('LightSlateGray'),
            101: lambda: self.set_background_color('LightCoral'),
            102: lambda: self.set_background_color('LightGreen'),
            103: lambda: self.set_background_color('LightYellow'),
            104: lambda: self.set_background_color('LightSkyBlue'),
            105: lambda: self.set_background_color('LightPink'),
            106: lambda: self.set_background_color('LightCyan'),
            107: lambda: self.set_background_color('LightGray'),

            # these are used in combination with other codes to construct colors
            38: lambda rgb : self.set_text_color(rgb),
            48: lambda rgb : self.set_background_color(rgb),
        }

    def __str__(self):
        if self.is_bold:
            bold = 'bold'
        else:
            bold = 'normal'

        if self.is_italic:
            italic = 'italic'
        else:
            italic = 'normal'

        return f'<span style="white-space:pre;color:{self.text_color};background-color:{self.background_color};font-weight:{bold};font-style:{italic}">'

    def set_default(self):
        self.background_color = 'transparent'
        self.text_color = 'GhostWhite'
        self.is_bold = False
        self.is_italic = False

    def set_background_color(self, color):  self.background_color = color
    def set_text_color(self, color):        self.text_color = color
    def set_is_bold(self, is_bold):         self.is_bold = is_bold
    def set_is_italic(self, is_italic):     self.is_italic = is_italic

    def map_code(self, code):
        code_func = self.code_map.get(code)
        if code_func:
            code_func()

    def map_256_color(self, codes):
        # TODO: 256 color mapping
        pass

    def map_rgb_color(self, codes):
        self.code_map.get(codes[0])(f'rgb({codes[2]},{codes[3]},{codes[4]})')


def parse_style_codes(codes, style):
    # TODO: is it valid to chain style codes together in the same escape sequence?
    #       ex:  \x1b[38;5;{id};48;5;{id}m   <- is this valid for setting both foreground and background colors via 256 color?

    # \x1b[38;5;{id}m  \x1b[48;5;{id}m    256 Color  foreground/background
    if len(codes) == 3 and codes[1] == 5:
        style.map_256_color(codes)
        return

    # \x1b[38;2;{r};{g};{b}m  \x1b[48;2;{r};{g};{b}m    true color RGB foreground/background
    if len(codes) == 5 and codes[1] == 2:
        style.map_rgb_color(codes)
        return

    for code in codes:
        style.map_code(code)
