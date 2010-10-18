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

import gedit
import gobject
import gtk
import pango
import re
import traceback
import gconf

class IntelligentTextCompletionPlugin(gedit.Plugin):

    def __init__(self):
        gedit.Plugin.__init__(self)
    
    def create_configure_dialog(self):
        return options_singleton().create_configure_dialog()
    
    def _connect_view(self, view, window):
        """Connect to view's editing signals."""
        callback = self._on_view_key_press_event
        id = view.connect("key-press-event", callback, window)
        view.set_data(self.__class__.__name__, (id))

    def _on_window_tab_added(self, window, tab):
        """Connect to signals of the document and view in tab."""
        name = self.__class__.__name__
        view = tab.get_view()
        handler_id = view.get_data(name)
        if handler_id is None:
            self._connect_view(view, window)

    def _on_window_tab_removed(self, window, tab):
        pass

    def activate(self, window):
        """Activate plugin."""
        callback = self._on_window_tab_added
        id_1 = window.connect("tab-added", callback)
        callback = self._on_window_tab_removed
        id_2 = window.connect("tab-removed", callback)
        window.set_data(self.__class__.__name__, (id_1, id_2))
        views = window.get_views()
        for view in views:
            self._connect_view(view, window)

    def deactivate(self, window):
        """Deactivate plugin."""
        widgets = [window]
        widgets.extend(window.get_views())
        widgets.extend(window.get_documents())
        name = self.__class__.__name__
        for widget in widgets:
            for handler_id in widget.get_data(name):
                widget.disconnect(handler_id)
            widget.set_data(name, None)

    def _on_view_key_press_event(self, view, event, window):
        window = gedit.app_get_default().get_active_window()
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
        window = gedit.app_get_default().get_active_window()
        doc = window.get_active_document()
        # get cursor
        cursor = doc.get_iter_at_mark(doc.get_insert())
        # get typed string
        typed_string = unicode(event.string)
        # get previous char
        prev_char = None
        if not cursor.get_line_offset() == 0:
            prev_char_pos = cursor.copy()
            prev_char_pos.set_line_offset(cursor.get_line_offset() - 1)
            prev_char = doc.get_text(prev_char_pos, cursor)
        # get next char
        next_char = None
        if not cursor.ends_line():
            next_char_pos = cursor.copy()
            next_char_pos.set_line_offset(cursor.get_line_offset() + 1)
            next_char = doc.get_text(cursor, next_char_pos)
        # get line before cursor
        line_start = cursor.copy()
        line_start.set_line_offset(0)
        preceding_line = doc.get_text(line_start, cursor)
        # get line after cursor
        line_end = cursor.copy()
        if not cursor.ends_line():
            line_end.forward_to_line_end()
        line_after = doc.get_text(cursor, line_end)
        # get whitespace in front of line
        whitespace_pos = 0
        whitespace = ""
        while len(preceding_line) > whitespace_pos and preceding_line[whitespace_pos] in ignore_whitespace:
            whitespace += preceding_line[whitespace_pos]
            whitespace_pos += 1
        # get options
        options = options_singleton()
        
        # Do not complete text after pasting text.
        if len(typed_string) > 1:
            return False
        typed_char = typed_string
        
        # do not complete if text is selected
        bounds = doc.get_selection_bounds()
        if len(bounds):
            return False
        ################### auto-close brackets and quotes ###################
        if options.closeBracketsAndQuotes:
            open_close = {
                '"': '"',
                "'": "'",
                '(': ')',
                '{': '}',
                '[': ']',
            }
            for check_char, add_char in open_close.items():
                # if character user is adding is the same as the one that
                # is auto-generated, remove the auto generated char
                if typed_char == add_char:
                    if not cursor.ends_line():
                        if next_char == add_char:
                            doc.delete(cursor, next_char_pos)
                            continue
                # typed_char equals char we're looking for
                if typed_char == check_char:
                    # check for unlogical adding
                    if check_char == add_char:
                        # uneven number of add_char's in front
                        if len(re.findall(check_char, preceding_line)) % 2 == 1:
                            continue
                        # uneven number of add_char's in back
                        if len(re.findall(check_char, line_after)) % 2 == 1:
                            continue
                    # don't add add_char if it is used around text
                    non_text_left =  ' \t\n\r,=+*/:;.?!$&@%~<>\\(){}[]-"\''
                    non_text_right = ' \t\n\r,=+*/:;.?!$&@%~<>\\)}]'
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
                if event.keyval == gtk.keysyms.BackSpace:
                    if prev_char == check_char and next_char == add_char:
                        doc.delete(cursor, next_char_pos)
        
        ################### auto-complete XML tags ###################
        if options.completeXML:
            if prev_char == "<" and typed_char == "/":
                start = doc.get_start_iter()
                preceding_document = doc.get_text(start, cursor)
                # analyse previous XML code
                closing_tag = get_closing_xml_tag(preceding_document)
                # insert code
                if closing_tag:
                    return self._insert_at_cursor(typed_char + closing_tag + ">")
                else:
                    return False # do nothing
        
        ################### detect lists ###################
        if options.detectLists:
            if event.keyval == gtk.keysyms.Return:
                # constants
                list_bullets = ['* ', '- ', '$ ', '> ', '+ ']
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
        if event.keyval == gtk.keysyms.Return:
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
            if event.keyval == gtk.keysyms.Return:
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
                            ending_text = doc.get_text(cursor, end).strip()
                            doc.delete(cursor, end)
                            
                            add_middle = typed_char + whitespace + get_tab_string(view)
                            add_end = ending_text + typed_char + whitespace
                        else:
                            add_middle = typed_char + whitespace + get_tab_string(view)
                            add_end = ""
                        return self._insert_at_cursor(add_middle, add_end)
                    
        
    def _insert_at_cursor(self, middle, end = ""):
        window = gedit.app_get_default().get_active_window()
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
def options_singleton():
    if Options.singleton is None:
        Options.singleton = Options()
    return Options.singleton
    
class Options(gobject.GObject):

    __gsignals__ = {
        'options-changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    singleton = None

    def __init__(self):

        gobject.GObject.__init__(self)
        self.__gconfDir = "/apps/gedit-2/plugins/intelligent_text_completion"

        # default values
        self.closeBracketsAndQuotes = True
        self.completeXML = True
        self.detectLists = True
        self.autoindentAfterFunctionOrList = True
    
        # create gconf directory if not set yet
        client = gconf.client_get_default()        
        if not client.dir_exists(self.__gconfDir):
            client.add_dir(self.__gconfDir,gconf.CLIENT_PRELOAD_NONE)

        # get the gconf keys, or stay with default if key not set
        try:
            self.closeBracketsAndQuotes = client.get_bool(self.__gconfDir+"/closeBracketsAndQuotes")
            self.completeXML = client.get_bool(self.__gconfDir+"/completeXML")
            self.detectLists = client.get_bool(self.__gconfDir+"/detectLists")
            self.autoindentAfterFunctionOrList = client.get_bool(self.__gconfDir+"/autoindentAfterFunctionOrList")
        except Exception, e: # catch, just in case
            print e
    def __del__(self):
        # write changes to gconf
        client = gconf.client_get_default()
        client.set_bool(self.__gconfDir+"/closeBracketsAndQuotes", self.closeBracketsAndQuotes)
        client.set_bool(self.__gconfDir+"/completeXML", self.completeXML)
        client.set_bool(self.__gconfDir+"/detectLists", self.detectLists)
        client.set_bool(self.__gconfDir+"/autoindentAfterFunctionOrList", self.autoindentAfterFunctionOrList)

    def create_configure_dialog(self):
        win = gtk.Window()
        win.connect("delete-event",lambda w,e: w.destroy())
        win.set_title("Preferences")
        win.set_position(gtk.WIN_POS_CENTER)
        vbox = gtk.VBox() 

        #--------------------------------  

        # disable tabs
        #notebook = gtk.Notebook()
        #notebook.set_border_width(6)
        #vbox.pack_start(notebook)

        vbox2 = gtk.VBox()
        vbox2.set_border_width(6) 

        box = gtk.HBox()
        closeBracketsAndQuotes = gtk.CheckButton("Auto-close brackets and quotes")
        closeBracketsAndQuotes.set_active(self.closeBracketsAndQuotes)
        box.pack_start(closeBracketsAndQuotes,False,False,6)
        vbox2.pack_start(box,False)
        
        box = gtk.HBox()
        completeXML = gtk.CheckButton("Auto-complete XML tags")
        completeXML.set_active(self.completeXML)
        box.pack_start(completeXML,False,False,6)
        vbox2.pack_start(box,False)

        box = gtk.HBox()
        detectLists = gtk.CheckButton("Detect lists")
        detectLists.set_active(self.detectLists)
        box.pack_start(detectLists,False,False,6)
        vbox2.pack_start(box,False)

        box = gtk.HBox()
        autoindentAfterFunctionOrList = gtk.CheckButton("Auto-indent after function or list")
        autoindentAfterFunctionOrList.set_active(self.autoindentAfterFunctionOrList)
        box.pack_start(autoindentAfterFunctionOrList,False,False,6)
        vbox2.pack_start(box,False)
        
        # disable tabs
        #notebook.append_page(vbox2,gtk.Label("General"))
        vbox.pack_start(vbox2, False)

        #--------------------------------       
        vbox2 = gtk.VBox()
        vbox2.set_border_width(6)

        button = {}

        def setValues(w):

            # set class attributes
            self.closeBracketsAndQuotes = closeBracketsAndQuotes.get_active()
            self.completeXML = completeXML.get_active()
            self.detectLists = detectLists.get_active()
            self.autoindentAfterFunctionOrList = autoindentAfterFunctionOrList.get_active()
                
            # write changes to gconf
            client = gconf.client_get_default()

            client.set_bool(self.__gconfDir+"/closeBracketsAndQuotes", self.closeBracketsAndQuotes)
            client.set_bool(self.__gconfDir+"/completeXML", self.completeXML)
            client.set_bool(self.__gconfDir+"/detectLists", self.detectLists)
            client.set_bool(self.__gconfDir+"/autoindentAfterFunctionOrList", self.autoindentAfterFunctionOrList)

            # commit changes and quit dialog
            self.emit("options-changed")
            win.destroy()

        box = gtk.HBox()
        b = gtk.Button(None,gtk.STOCK_OK)
        b.connect("clicked",setValues)
        box.pack_end(b,False)
        b = gtk.Button(None,gtk.STOCK_CANCEL)
        b.connect("clicked",lambda w,win: win.destroy(),win)
        box.pack_end(b,False)
        vbox.pack_start(box,False)

        win.add(vbox)
        win.show_all()        
        return win

gobject.type_register(Options)

