# Copyright (C) 2010 - Jens Nyman (nymanjens.nj@gmail.com)
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.

from gi.repository import Gtk, GObject, Gedit, PeasGtk
import re
import traceback
import gconf

class IntelligentTextCompletionPlugin(GObject.Object, Gedit.WindowActivatable, PeasGtk.Configurable):
    window = GObject.property(type=Gedit.Window)

    def __init__(self):
        GObject.Object.__init__(self)
        self._instances = {}

    def do_create_configure_widget(self):
        return IntelligentTextCompletionOptions.get_instance().create_configure_dialog()

    def _connect_view(self, view, window):
        """Connect to view's editing signals."""
        callback = self._on_view_key_press_event
        id = view.connect("key-press-event", callback, window)
        view.intelligent_text_completion_id = id

    def _on_window_tab_added(self, window, tab):
        """Connect to signals of the document and view in tab."""
        view = tab.get_view()
        handler_id = getattr(view, 'intelligent_text_completion_id', None)
        if handler_id is None:
            self._connect_view(view, window)

    def _on_window_tab_removed(self, window, tab):
        pass

    def do_activate(self):
        """Activate plugin."""
        window = self.window
        callback = self._on_window_tab_added
        id_1 = window.connect("tab-added", callback)
        callback = self._on_window_tab_removed
        id_2 = window.connect("tab-removed", callback)
        window.intelligent_text_completion_id = (id_1, id_2)
        views = window.get_views()
        for view in views:
            self._connect_view(view, window)

    def do_deactivate(self):
        """Deactivate plugin."""
        window = self.window
        widgets = [window]
        widgets.extend(window.get_views())
        widgets.extend(window.get_documents())
        for widget in widgets:
            for handler_id in getattr(widget, 'intelligent_text_completion_id', []):
                widget.disconnect(handler_id)
            widget.intelligent_text_completion_id = None

    def _on_view_key_press_event(self, view, event, window):
        doc = window.get_active_document()
        try:
            return self._handle_event(view, event, window)
        except:
            err = "Exception\n"
            err += traceback.format_exc()
            doc.set_text(err)

    ############ plugin core functions ############
    def _handle_event(self, view, event, window):
        """Key press event"""
        ### get vars ###
        # constants
        ignore_whitespace = '\t '
        # get document
        doc = window.get_active_document()
        # get cursor
        cursor = doc.get_iter_at_mark(doc.get_insert())
        # get typed string
        typed_string = unicode(event.string, 'UTF-8')
        # get previous char
        prev_char = None
        if not cursor.get_line_offset() == 0:
            prev_char_pos = cursor.copy()
            prev_char_pos.set_line_offset(cursor.get_line_offset() - 1)
            prev_char = doc.get_text(prev_char_pos, cursor, False)
        # get next char
        next_char = None
        if not cursor.ends_line():
            next_char_pos = cursor.copy()
            next_char_pos.set_line_offset(cursor.get_line_offset() + 1)
            next_char = doc.get_text(cursor, next_char_pos, False)
        # get line before cursor
        line_start = cursor.copy()
        line_start.set_line_offset(0)
        preceding_line = doc.get_text(line_start, cursor, False)
        # get line after cursor
        line_end = cursor.copy()
        if not cursor.ends_line():
            line_end.forward_to_line_end()
        line_after = doc.get_text(cursor, line_end, False)
        # get whitespace in front of line
        whitespace_pos = 0
        whitespace = ""
        while len(preceding_line) > whitespace_pos and preceding_line[whitespace_pos] in ignore_whitespace:
            whitespace += preceding_line[whitespace_pos]
            whitespace_pos += 1
        # get options
        options = IntelligentTextCompletionOptions.get_instance()

        # Do not complete text after pasting text.
        if len(typed_string) > 1:
            return False
        typed_char = typed_string

        # GLOBALS
        open_close = {
            '"': '"',
            "'": "'",
            '(': ')',
            '{': '}',
            '[': ']',
        }

        ################### selected text ###################
        bounds = doc.get_selection_bounds()
        if len(bounds) > 0:
            # auto-close brackets and quotes
            if options.closeBracketsAndQuotes:
                for open, close in open_close.items():
                    if typed_char == open:
                        # get bounds data
                        off1 = bounds[0].get_offset()
                        off2 = bounds[1].get_offset()
                        # add open char
                        doc.place_cursor(bounds[0])
                        doc.insert_at_cursor(open)
                        # refresh cursor and move it
                        cursor = doc.get_iter_at_mark(doc.get_insert())
                        cursor.set_offset(cursor.get_offset() + (off2 - off1))
                        doc.place_cursor(cursor)
                        # add close char
                        doc.insert_at_cursor(close)
                        return True
            return False

        ################### auto-close brackets and quotes ###################
        if options.closeBracketsAndQuotes and prev_char != '\\':
            """ detect python comments """
            if typed_char == '"' and re.search('^[^"]*""$', preceding_line) and cursor.ends_line():
                return self._insert_at_cursor(typed_char + ' ', ' """')

            for check_char, add_char in open_close.items():
                # if character user is adding is the same as the one that
                # is auto-generated, remove the auto generated char
                if typed_char == add_char:
                    if not cursor.ends_line():
                        if next_char == add_char:
                            if check_char != add_char:
                                # don't remove ) when it's probably not auto-generated
                                preceding_check_chars = len(re.findall('\%s' % check_char, preceding_line))
                                preceding_add_chars = len(re.findall('\%s' % add_char, preceding_line))
                                following_check_chars = len(re.findall('\%s' % check_char, line_after))
                                following_add_chars = len(re.findall('\%s' % add_char, line_after))
                                if preceding_check_chars - preceding_add_chars > following_add_chars:
                                    continue
                                # don't remove ) when the line becomes complex
                                if following_check_chars > 0:
                                    continue
                            doc.delete(cursor, next_char_pos)
                            return False
                # typed_char equals char we're looking for
                if typed_char == check_char:
                    # check for unlogical adding
                    if check_char == add_char:
                        # uneven number of check_char's in front
                        if len(re.findall(check_char, preceding_line)) % 2 == 1:
                            continue
                        # uneven number of check_char's in back
                        if len(re.findall(check_char, line_after)) % 2 == 1:
                            continue
                    # don't add add_char if it is used around text
                    non_text_left =  ' \t\n\r,=+*:;.?!$&@%~<(){}[]-"\''
                    non_text_right = ' \t\n\r,=+*:;.?&@%~>)}]'
                    if not next_char and not check_char == "'":
                        # if we're just typing with nothing on the right,
                        # adding is OK as long as it isn't a "'".
                        pass
                    elif (not prev_char or prev_char in non_text_left) and (not next_char or next_char in non_text_right):
                        # this char is surrounded by nothing or non-text, therefore, we can add autotext
                        pass
                    elif check_char != add_char and (not next_char or next_char in non_text_right):
                        # this opening char has non-text on the right, therefore, we can add autotext
                        pass
                    else:
                        continue
                    # insert add_char
                    return self._insert_at_cursor(typed_char, add_char)
                # check backspace
                if event.keyval == 65288: # backspace
                    if prev_char == check_char and next_char == add_char:
                        doc.delete(cursor, next_char_pos)

        ################### auto-complete XML tags ###################
        if options.completeXML:
            if prev_char == "<" and typed_char == "/":
                start = doc.get_start_iter()
                preceding_document = doc.get_text(start, cursor, False)
                # analyse previous XML code
                closing_tag = get_closing_xml_tag(preceding_document)
                # insert code
                if closing_tag:
                    return self._insert_at_cursor(typed_char + closing_tag + ">")
                else:
                    return False # do nothing

        ################### detect lists ###################
        if options.detectLists:
            if event.keyval == 65293: # return
                # constants
                list_bullets = ['* ', '- ', '$ ', '> ', '+ ', '~ ']
                # cycle through all bullets
                for bullet in list_bullets:
                    if len(preceding_line) >= whitespace_pos + len(bullet):
                        if preceding_line[whitespace_pos:whitespace_pos + len(bullet)] == bullet:
                            # endlist function by double enter
                            if preceding_line == whitespace + bullet and bullet != '* ':
                                start = cursor.copy()
                                start.set_line_offset(len(whitespace))
                                doc.delete(start, cursor)
                                return True
                            return self._insert_at_cursor(typed_char + whitespace + bullet)

        ################### detect java-like comment ###################
        if event.keyval == 65293: # return
            # constants
            comments = {
                '/**' : (' * ', ' */'),
                '/*'  : (' * ', ' */'),
            }
            # cycle through all types of comment
            for comment_start, (comment_middle, comment_end) in comments.items():
                if preceding_line[whitespace_pos:] == comment_start:
                    add_middle = typed_char + whitespace + comment_middle
                    add_end = typed_char + whitespace + comment_end
                    return self._insert_at_cursor(add_middle, add_end)

        ################### auto-indent after function/list ###################
        if options.autoindentAfterFunctionOrList:
            if event.keyval == 65293: # return
                indent_triggers = {
                    '(': ')',
                    '{': '}',
                    '[': ']',
                    ':': '',
                }
                for indent_trigger, ending_char in indent_triggers.items():
                    if prev_char == indent_trigger:
                        if line_after:
                            # text between begin and ending brackets should come
                            # in the middle row
                            if ending_char != '' and ending_char in line_after:
                                ending_pos = line_after.find(ending_char)
                            else:
                                ending_pos = len(line_after)
                            end = cursor.copy()
                            end.set_line_offset(end.get_line_offset() + ending_pos)
                            ending_text = doc.get_text(cursor, end, False).strip()
                            doc.delete(cursor, end)

                            add_middle = typed_char + whitespace + get_tab_string(view)
                            add_end = ending_text + typed_char + whitespace
                        else:
                            add_middle = typed_char + whitespace + get_tab_string(view)
                            add_end = ""
                        return self._insert_at_cursor(add_middle, add_end)


    def _insert_at_cursor(self, middle, end = ""):
        window = self.window
        doc = window.get_active_document()
        doc.insert_at_cursor(middle + end)
        # refresh cursor and move it to the middle
        cursor = doc.get_iter_at_mark(doc.get_insert())
        cursor.set_offset(cursor.get_offset() - len(end))
        doc.place_cursor(cursor)
        return True


##### regular functions #####

def get_tab_string(view):
    tab_width = view.get_tab_width()
    tab_spaces = view.get_insert_spaces_instead_of_tabs()
    tab_code = ""
    if tab_spaces:
        for x in range(tab_width):
            tab_code += " "
    else:
        tab_code = "\t"
    return tab_code

def get_closing_xml_tag(document):
    tags = re.findall(r'<.*?>', document)
    tags.reverse()
    closed = []
    for tag in tags:
        # ignore special tags like <!-- --> and <!doctype ...>
        if re.match(r'<!.*?>', tag):
            continue
        # ignore special tags like <?, <?=, <?php
        if re.match(r'<\?.*?>', tag):
            continue
        # neutral tag
        if re.match(r'<.*?/>', tag):
            continue
        # closing tag
        m = re.match(r'</ *([^ ]*).*?>', tag)
        if m:
            closed.append(m.group(1))
            continue
        # opening tag
        m = re.match(r'< *([^/][^ ]*).*?>', tag)
        if m:
            openedtag = m.group(1)
            while True:
                if len(closed) == 0:
                    return openedtag
                close_tag = closed.pop()
                if close_tag.lower() == openedtag.lower():
                    break
            continue
    return None



################## OPTIONS DIALOG ##################
class IntelligentTextCompletionOptions(object):

    ## settings
    closeBracketsAndQuotes = True
    completeXML = True
    detectLists = True
    autoindentAfterFunctionOrList = True

    ## buttons for settings
    _closeBracketsAndQuotesButton = None
    _completeXMLButton = None
    _detectListsButton = None
    _autoindentAfterFunctionOrListButton = None

    ## configuration client
    _GCONF_SETTINGS_DIR = "/apps/gedit-3/plugins/intelligent_text_completion"
    _gconf_client = None

    ## static singleton reference
    singleton = None

    def __init__(self):
        # create gconf directory if not set yet
        self._gconf_client = gconf.client_get_default()
        if not self._gconf_client.dir_exists(self._GCONF_SETTINGS_DIR):
            self._gconf_client.add_dir(self._GCONF_SETTINGS_DIR, gconf.CLIENT_PRELOAD_NONE)

        # load settings
        self.closeBracketsAndQuotes = self._load_setting("closeBracketsAndQuotes")
        self.completeXML = self._load_setting("completeXML")
        self.detectLists = self._load_setting("detectLists")
        self.autoindentAfterFunctionOrList = self._load_setting("autoindentAfterFunctionOrList")

    @classmethod
    def get_instance(cls):
        """ Get singleton instance """
        if cls.singleton is None:
            cls.singleton = cls()
        return cls.singleton

    def create_configure_dialog(self):
        """ Creates configure dialog using GTK """
        # make vertically stacking box
        vbox = Gtk.VBox()
        vbox.set_border_width(6)

        # add checkboxes
        self._closeBracketsAndQuotesButton = self._add_setting_checkbox(
            vbox=vbox,
            current_value=self.closeBracketsAndQuotes,
            helptext="Auto-close brackets and quotes",
        )
        self._completeXMLButton = self._add_setting_checkbox(
            vbox=vbox,
            current_value=self.completeXML,
            helptext="Auto-complete XML tags",
        )
        self._detectListsButton = self._add_setting_checkbox(
            vbox=vbox,
            current_value=self.detectLists,
            helptext="Detect lists",
        )
        self._autoindentAfterFunctionOrListButton = self._add_setting_checkbox(
            vbox=vbox,
            current_value=self.autoindentAfterFunctionOrList,
            helptext="Auto-indent after function or list",
        )
        return vbox

    def _add_setting_checkbox(self, vbox, current_value, helptext):
        box = Gtk.HBox()
        check_button = Gtk.CheckButton(helptext)
        check_button.set_active(current_value)
        box.pack_start(check_button,False,False,6)
        check_button.connect('toggled', self._on_check_button_toggled)
        vbox.pack_start(box, False, True, 0)
        return check_button

    def _on_check_button_toggled(self, *args):
        # set class attributes
        self.closeBracketsAndQuotes = self._closeBracketsAndQuotesButton.get_active()
        self.completeXML = self._completeXMLButton.get_active()
        self.detectLists = self._detectListsButton.get_active()
        self.autoindentAfterFunctionOrList = self._autoindentAfterFunctionOrListButton.get_active()

        # write changes to gconf
        self._save_setting("closeBracketsAndQuotes", self.closeBracketsAndQuotes)
        self._save_setting("completeXML", self.completeXML)
        self._save_setting("detectLists", self.detectLists)
        self._save_setting("autoindentAfterFunctionOrList", self.autoindentAfterFunctionOrList)

    def _save_setting(self, setting_name, value):
        self._gconf_client.set_bool("{}/{}".format(self._GCONF_SETTINGS_DIR, setting_name), value)

    def _load_setting(self, setting_name):
        try:
            return self._gconf_client.get_bool("{}/{}".format(self._GCONF_SETTINGS_DIR, setting_name))
        except Exception, e: # catch, just in case
            print e

