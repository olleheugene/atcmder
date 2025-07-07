from PySide6.QtWidgets import QAbstractScrollArea, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPalette, QGuiApplication
from PySide6.QtCore import Qt, QTimer
import re

MAX_TERMINAL_LINES = 9999

class TerminalWidget(QAbstractScrollArea):
    def __init__(self, parent=None, font_family="Monaco", font_size=14):
        super().__init__(parent)
        self.font = QFont(font_family, font_size)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.font_metrics = QFontMetrics(self.font)
        self.line_height = self.font_metrics.height()
        self.char_width = self.font_metrics.horizontalAdvance('M')
        self.lines = []
        self.scroll_offset = 0
        self.auto_scroll = True 
        
        # Line number settings
        self.show_line_numbers = False
        self.line_number_width = 0
        self.line_number_padding = 10  # Padding between line numbers and text
    
        # Selection attributes
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
    
        # Cursor attributes
        self.cursor_line = 0
        self.cursor_col = 0
        self.cursor_visible = True
    
        # ANSI color cache
        self.ansi_colors = {
            30: QColor(0, 0, 0), 31: QColor(205, 49, 49), 32: QColor(13, 188, 121),
            33: QColor(229, 229, 16), 34: QColor(36, 114, 200), 35: QColor(188, 63, 188),
            36: QColor(17, 168, 205), 37: QColor(229, 229, 229), 90: QColor(102, 102, 102),
            91: QColor(241, 76, 76), 92: QColor(35, 209, 139), 93: QColor(245, 245, 67),
            94: QColor(59, 142, 234), 95: QColor(214, 112, 214), 96: QColor(41, 184, 219),
            97: QColor(255, 255, 255),
        }
        self.default_color = QColor(200, 200, 200)
        self.current_color = self.default_color

        # Fast rendering with QTimer
        self._update_pending = False
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(16)  # 60fps
        self._update_timer.timeout.connect(self._do_update)
        self._update_timer.start()

        # Search functionality
        self.search_text = ""
        self.search_matches = []
        self.search_index = -1
        self.search_case_sensitive = False

        # Add flag to prevent output updates when manually scrolling
        self._output_frozen = False
        
        # Add flag to prevent recursion in scrollbar updates
        self._updating_scrollbar = False

        # Connect scrollbar signals
        self.verticalScrollBar().valueChanged.connect(self._on_vertical_scroll)

    def _line_text(self, line_parts):
        """Extract plain text from a line's parts (ignoring colors)"""
        if not line_parts:
            return ""
        return "".join(part for part, color in line_parts)

    def append_text(self, text):
        """Add text to terminal, handle ANSI clear screen and cursor home"""
        if not text:
            return

        # Enable a setting to ensure the scrollbar is always shown.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # Record the current line count (before adding text)
        lines_before = len(self.lines)
        last_line_length_before = len(self._line_text(self.lines[-1])) if self.lines else 0

        # Handle ANSI cursor home (ESC[H])
        cursor_home_pattern = re.compile(r'\x1B\[H')
        if cursor_home_pattern.search(text):
            # Move cursor to the top-left (0, 0)
            self.cursor_line = 0
            self.cursor_col = 0
            self.cursor_visible = True
            self.clear()
            self.viewport().update()
            text = text.replace('\x1b[H', '\n')

        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if i > 0 or not self.lines:
                self.lines.append([])
            parsed = self.parse_ansi_text(line)
            merged = []
            for part, color in parsed:
                if merged and merged[-1][1] == color:
                    merged[-1] = (merged[-1][0] + part, color)
                else:
                    merged.append((part, color))
            self.lines[-1].extend(merged)
        
        if len(self.lines) > MAX_TERMINAL_LINES:
            del self.lines[:len(self.lines) - MAX_TERMINAL_LINES]
        
        # Update line number width if needed
        if self.show_line_numbers:
            self._update_line_number_width()
        
        # If output is frozen (user is manually scrolling), don't update the view
        if self._output_frozen:
            # Still update scrollbar range but don't change position
            self.update_scrollbar()
            return
        
        # Ensure the scroll offset remains stable after adding data to avoid view shifting
        visible_lines = max(1, self.viewport().height() // self.line_height)

        # If auto-scroll is disabled, adjust the scroll offset to maintain the current position when new content is added
        if not self.auto_scroll and self.scroll_offset > 0:
            # Calculate the number of newly added lines
            lines_after = len(self.lines)
            new_lines_added = lines_after - lines_before

            # If text was added to the existing last line (without a line break), no offset adjustment is needed
            if new_lines_added > 0:
                self.scroll_offset += new_lines_added

        self.update_scrollbar()
        self._schedule_update()

        # If auto-scroll is enabled, move the cursor to the bottom and scroll
        if self.auto_scroll:
            # Reset scroll offset (scroll to bottom)
            self.scroll_offset = 0
            self.set_cursor_to_end()

            # Move the scrollbar to the bottom
            verticalBar = self.verticalScrollBar()
            if verticalBar:
                verticalBar.setValue(verticalBar.maximum())

    def parse_ansi_text(self, text):
        """Parse ANSI escape sequences for colors"""
        if not text:
            return [(text, self.current_color)]
        
        # Simple ANSI color parsing
        ansi_pattern = re.compile(r'\x1b\[(\d+)m')
        parts = []
        last_end = 0
        
        for match in ansi_pattern.finditer(text):
            # Add text before this ANSI code
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    parts.append((plain_text, self.current_color))
            
            # Process ANSI code
            code = int(match.group(1))
            if code == 0:  # Reset
                self.current_color = self.default_color
            elif code in self.ansi_colors:
                self.current_color = self.ansi_colors[code]
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            remaining_text = text[last_end:]
            if remaining_text:
                parts.append((remaining_text, self.current_color))
        
        # If no parts were created, return the whole text with current color
        if not parts:
            parts.append((text, self.current_color))
        
        return parts

    def _schedule_update(self):
        """Schedule a UI update"""
        if not self._update_pending:
            self._update_pending = True

    def _do_update(self):
        """Perform the actual UI update"""
        if self._update_pending:
            self._update_pending = False
            self.viewport().update()

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        try:
            painter.setFont(self.font)
            painter.fillRect(self.viewport().rect(), QColor(30, 30, 30))
            
            if not self.lines:
                return
            
            viewport_rect = self.viewport().rect()
            effective_width = viewport_rect.width()
            if self.verticalScrollBar().isVisible():
                effective_width -= self.verticalScrollBar().width()
            effective_height = viewport_rect.height()
            if self.horizontalScrollBar().isVisible():
                effective_height -= self.horizontalScrollBar().height()
            
            visible_lines = max(1, effective_height // self.line_height)
            h_scroll_offset = self.horizontalScrollBar().value()
            total_lines = len(self.lines)
            
            # Calculate text start position (after line numbers)
            text_start_x = self.line_number_width if self.show_line_numbers else 0
            
            if self.auto_scroll:
                start_line = max(0, total_lines - visible_lines + self.scroll_offset)
            else:
                start_line = self.scroll_offset
            
            end_line = min(total_lines, start_line + visible_lines + 1)
            
            # Draw line number background if enabled
            if self.show_line_numbers and self.line_number_width > 0:
                line_number_rect = viewport_rect.adjusted(0, 0, -(effective_width - self.line_number_width), 0)
                painter.fillRect(line_number_rect, QColor(40, 40, 40))  # Slightly lighter background
                
                # Draw separator line
                painter.setPen(QColor(60, 60, 60))
                painter.drawLine(self.line_number_width - self.line_number_padding // 2, 0, 
                               self.line_number_width - self.line_number_padding // 2, effective_height)
        
            # Draw search highlights first (behind text)
            if self.search_matches:
                for match_idx, (match_line, match_start, match_end) in enumerate(self.search_matches):
                    if match_line >= start_line and match_line < end_line:
                        y = (match_line - start_line) * self.line_height
                        x_start = text_start_x + match_start * self.char_width - h_scroll_offset
                        x_end = text_start_x + match_end * self.char_width - h_scroll_offset
                        
                        # Only draw if visible in text area
                        if x_end > text_start_x and x_start < effective_width:
                            # Clip to visible area
                            x_start = max(x_start, text_start_x)
                            x_end = min(x_end, effective_width)
                            
                            # Use different color for current match
                            if match_idx == self.search_index:
                                highlight_color = QColor(255, 255, 0, 100)  # Yellow for current match
                            else:
                                highlight_color = QColor(255, 255, 255, 60)  # White for other matches
                            
                            painter.fillRect(x_start, y, x_end - x_start, self.line_height, highlight_color)
            
            for line_idx in range(start_line, end_line):
                if line_idx >= len(self.lines):
                    break
                
                y = (line_idx - start_line) * self.line_height + self.line_height
                
                # Draw line number
                if self.show_line_numbers:
                    painter.setPen(QColor(120, 120, 120))  # Gray color for line numbers
                    line_number = str(line_idx + 1)  # 1-based line numbering
                    line_number_x = self.line_number_width - self.line_number_padding - self.font_metrics.horizontalAdvance(line_number)
                    painter.drawText(line_number_x, y, line_number)
                
                # Draw text content
                x = text_start_x - h_scroll_offset
                line_parts = self.lines[line_idx]
                
                for part, color in line_parts:
                    if not part:
                        continue
                    painter.setPen(color)
                    if x + self.font_metrics.horizontalAdvance(part) > text_start_x:  # Only draw if visible
                        visible_part = part
                        if x < text_start_x:
                            # Clip text that starts before the text area
                            chars_to_skip = max(0, (text_start_x - x) // self.char_width)
                            if chars_to_skip < len(part):
                                visible_part = part[chars_to_skip:]
                                x = text_start_x
                        
                        painter.drawText(x, y, visible_part)
                    x += self.font_metrics.horizontalAdvance(part)
            
            # Draw selection if active
            if hasattr(self, 'selection_start') and hasattr(self, 'selection_end') and self.selection_start and self.selection_end:
                self._draw_selection(painter, start_line, end_line, text_start_x, h_scroll_offset)
            
            # Draw cursor
            if hasattr(self, 'cursor_visible') and hasattr(self, 'cursor_line') and hasattr(self, 'cursor_col'):
                if self.cursor_visible and self.cursor_line >= start_line and self.cursor_line < end_line:
                    cursor_y = (self.cursor_line - start_line) * self.line_height + self.line_height
                    cursor_x = text_start_x + self.cursor_col * self.char_width - h_scroll_offset
                    if cursor_x >= text_start_x:  # Only draw if cursor is in text area
                        painter.setPen(QColor(255, 255, 255))
                        painter.drawLine(cursor_x, cursor_y - self.line_height + 2, cursor_x, cursor_y - 2)

        except Exception as e:
            print(f"Error in paintEvent: {e}")
        finally:
            # Ensure painter is properly ended
            if painter.isActive():
                painter.end()

    def _draw_selection(self, painter, start_line, end_line, text_start_x, h_scroll_offset):
        """Draw text selection highlight"""
        if not self.selection_start or not self.selection_end:
            return
        
        try:
            sel_start, sel_end = sorted([self.selection_start, self.selection_end])
            selection_color = QColor(0, 120, 215, 100)  # Blue selection
            
            for line_idx in range(max(sel_start[0], start_line), min(sel_end[0] + 1, end_line)):
                if line_idx >= len(self.lines):
                    break
                
                y = (line_idx - start_line) * self.line_height
                
                # Calculate selection bounds for this line
                if line_idx == sel_start[0] and line_idx == sel_end[0]:
                    # Selection is within one line
                    start_col = sel_start[1]
                    end_col = sel_end[1]
                elif line_idx == sel_start[0]:
                    # First line of selection
                    start_col = sel_start[1]
                    end_col = len(self._line_text(self.lines[line_idx]))
                elif line_idx == sel_end[0]:
                    # Last line of selection
                    start_col = 0
                    end_col = sel_end[1]
                else:
                    # Middle lines of selection
                    start_col = 0
                    end_col = len(self._line_text(self.lines[line_idx]))
                
                x_start = text_start_x + start_col * self.char_width - h_scroll_offset
                x_end = text_start_x + end_col * self.char_width - h_scroll_offset
                
                # Only draw if visible
                if x_end > text_start_x and x_start < self.viewport().width():
                    x_start = max(x_start, text_start_x)
                    x_end = min(x_end, self.viewport().width())
                    painter.fillRect(x_start, y, x_end - x_start, self.line_height, selection_color)
        
        except Exception as e:
            print(f"Error in _draw_selection: {e}")

    def update_scrollbar(self):
        """Update scrollbar ranges and positions"""
        if self._updating_scrollbar:
            return
        
        self._updating_scrollbar = True
        
        try:
            if not self.lines:
                self.verticalScrollBar().setRange(0, 1)
                self.horizontalScrollBar().setRange(0, 1)
                return
            
            viewport_rect = self.viewport().rect()
            effective_height = viewport_rect.height()
            if self.horizontalScrollBar().isVisible():
                effective_height -= self.horizontalScrollBar().height()
            
            visible_lines = max(1, effective_height // self.line_height)
            total_lines = len(self.lines)
            
            # Set vertical scrollbar range
            if total_lines > visible_lines:
                max_scroll = total_lines - visible_lines
                self.verticalScrollBar().setRange(0, max_scroll)
                
                # Calculate scrollbar position based on current scroll_offset
                if self.auto_scroll:
                    # Auto-scroll mode: position from bottom
                    scrollbar_value = max_scroll - self.scroll_offset
                else:
                    # Manual mode: position from top
                    scrollbar_value = self.scroll_offset
                
                # Clamp the value to valid range
                scrollbar_value = max(0, min(scrollbar_value, max_scroll))
                self.verticalScrollBar().setValue(scrollbar_value)
            else:
                self.verticalScrollBar().setRange(0, 1)
                self.verticalScrollBar().setValue(0)
            
            # Calculate horizontal scroll considering line numbers
            max_line_width = 0
            for line_parts in self.lines:
                line_width = sum(self.font_metrics.horizontalAdvance(part) for part, _ in line_parts)
                max_line_width = max(max_line_width, line_width)
            
            effective_width = viewport_rect.width()
            if self.verticalScrollBar().isVisible():
                effective_width -= self.verticalScrollBar().width()
            
            # Subtract line number width from effective width
            text_area_width = effective_width - (self.line_number_width if self.show_line_numbers else 0)
            
            if max_line_width > text_area_width:
                self.horizontalScrollBar().setRange(0, max_line_width - text_area_width)
            else:
                self.horizontalScrollBar().setRange(0, 1)
                self.horizontalScrollBar().setValue(0)
                
        finally:
            self._updating_scrollbar = False

    def _update_line_number_width(self):
        """Calculate the width needed for line numbers"""
        if not self.show_line_numbers:
            self.line_number_width = 0
            return
        
        # Calculate width based on maximum line count
        max_lines = max(len(self.lines), MAX_TERMINAL_LINES)
        line_count_str = str(max_lines)
        self.line_number_width = self.font_metrics.horizontalAdvance(line_count_str) + self.line_number_padding

    def set_show_line_numbers(self, show):
        """Enable or disable line number display"""
        self.show_line_numbers = show
        self._update_line_number_width()
        self.update_scrollbar()
        self.viewport().update()

    def wheelEvent(self, event):
        """Handle mouse wheel scrolling"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + wheel for font size change
            delta = event.angleDelta().y()
            if delta > 0:
                self.font_size = min(self.font_size + 1, 72)
            else:
                self.font_size = max(self.font_size - 1, 6)
            
            new_font = QFont(self.font.family(), self.font_size)
            new_font.setStyleHint(QFont.StyleHint.Monospace)
            self.set_font(new_font)
        else:
            # Normal scrolling - use scrollbar
            delta = event.angleDelta().y()
            scroll_lines = max(1, abs(delta) // 120)  # Standard wheel delta is 120
            
            current_value = self.verticalScrollBar().value()
            max_value = self.verticalScrollBar().maximum()
            
            if delta > 0:
                # Scroll up - freeze output
                new_value = max(0, current_value - scroll_lines)
                if new_value < max_value:  # Not at bottom
                    self._output_frozen = True
                    self.auto_scroll = False
            else:
                # Scroll down
                new_value = min(max_value, current_value + scroll_lines)
                # If scrolled to bottom, unfreeze
                if new_value >= max_value:
                    self._output_frozen = False
                    self.auto_scroll = True
        
            # Set scrollbar value (this will trigger _on_vertical_scroll)
            self.verticalScrollBar().setValue(new_value)
        
        event.accept()

    def _on_vertical_scroll(self, value):
        """Handle vertical scrollbar value changes"""
        if self._updating_scrollbar:
            return
            
        viewport_height = self.viewport().height()
        if self.horizontalScrollBar().isVisible():
            viewport_height -= self.horizontalScrollBar().height()
        
        visible_lines = max(1, viewport_height // self.line_height)
        total_lines = len(self.lines)
        
        if total_lines <= visible_lines:
            return
        
        scrollbar_max = self.verticalScrollBar().maximum()
        
        # Check if we're at the bottom
        at_bottom = value >= scrollbar_max
        
        # If we were frozen and now at bottom, unfreeze
        if self._output_frozen and at_bottom:
            self._output_frozen = False
            self.auto_scroll = True
        # If we move away from bottom, freeze output and disable auto-scroll
        elif not self._output_frozen and not at_bottom:
            self._output_frozen = True
            self.auto_scroll = False
        
        # Calculate scroll offset based on scrollbar position
        if self.auto_scroll and not self._output_frozen:
            # In auto-scroll mode, scrollbar works from bottom
            self.scroll_offset = scrollbar_max - value
        else:
            # In manual mode, scrollbar works from top
            self.scroll_offset = value
        
        self.viewport().update()

    def scrollContentsBy(self, dx, dy):
        """Handle scroll events - simplified version"""
        # This method is called by Qt's scroll system
        # We handle scrolling in _on_vertical_scroll instead
        self.viewport().update()

    def copy_selection(self):
        if not self.selection_start or not self.selection_end:
            return
        sel_start, sel_end = sorted([self.selection_start, self.selection_end])
        lines = []
        for i in range(sel_start[0], sel_end[0] + 1):
            line = self._line_text(self.lines[i])
            if i == sel_start[0] and i == sel_end[0]:
                lines.append(line[sel_start[1]:sel_end[1]])
            elif i == sel_start[0]:
                lines.append(line[sel_start[1]:])
            elif i == sel_end[0]:
                lines.append(line[:sel_end[1]])
            else:
                lines.append(line)
        text = '\n'.join(lines)
        QGuiApplication.clipboard().setText(text)

    def remove_last_char(self):
        """Remove the last character from the last line"""
        if not self.lines:
            return
        if self.lines[-1]:
            last_text, last_color = self.lines[-1][-1]
            if len(last_text) > 1:
                self.lines[-1][-1] = (last_text[:-1], last_color)
            else:
                self.lines[-1].pop()
                if not self.lines[-1] and len(self.lines) > 1:
                    self.lines.pop()
        else:
            if len(self.lines) > 1:
                self.lines.pop()
                self.remove_last_char()
        self._schedule_update()

    def clear(self):
        """Clear the terminal screen."""
        self.lines.clear()
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.scroll_offset = 0
        self._schedule_update()

    def _toggle_cursor(self):
        self.cursor_visible = not self.cursor_visible
        self.viewport().update()

    def set_font(self, font):
        """Update font and recalculate line number width"""
        self.font = font
        self.font_metrics = QFontMetrics(self.font)
        self.line_height = self.font_metrics.height()
        self.char_width = self.font_metrics.horizontalAdvance('M')
        
        # Update line number width with new font
        if self.show_line_numbers:
            self._update_line_number_width()
        
        self.update_scrollbar()
        self.viewport().update()

    def set_cursor(self, line, col):
        self.cursor_line = line
        self.cursor_col = col
        self.cursor_visible = True
        self.viewport().update()

    def set_cursor_to_end(self):
        """Move the cursor to the end of the last line."""
        if not self.lines:
            self.cursor_line = 0
            self.cursor_col = 0
        else:
            self.cursor_line = len(self.lines) - 1
            self.cursor_col = len(self._line_text(self.lines[-1]))  # _line_length 대신 len(_line_text()) 사용
    
        # Always keep the cursor visible when moving it to the end
        self.cursor_visible = True

        # Only move scrollbar to bottom if auto_scroll is enabled
        # This allows input even when scrolled up, while keeping the view fixed
        if self.auto_scroll and len(self.lines) > 0:
            # Move scrollbar to bottom
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
            # Reset scroll offset
            self.scroll_offset = 0

        # Update viewport
        self.viewport().update()

    def set_auto_scroll(self, enabled):
        """Method to set the auto-scroll state"""
        self.auto_scroll = enabled
        if enabled:
            self._output_frozen = False
            self.scroll_offset = 0
            self.update_scrollbar()
            self.viewport().update()
        else:
            self._output_frozen = True

    def toggle_auto_scroll(self):
        """Toggle auto-scrolling on or off."""
        self.set_auto_scroll(not self.auto_scroll)

    def is_auto_scroll_enabled(self):
        """Check if auto-scrolling is enabled."""
        return self.auto_scroll

    def scroll_to_bottom(self):
        """Scroll to the bottom of the terminal and resume output"""
        if self.lines:
            self._output_frozen = False
            self.auto_scroll = True
            self.scroll_offset = 0
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
            self.viewport().update()

    def start_search(self, text, case_sensitive=False):
        """Start searching for text in the terminal"""
        self.search_text = text
        self.search_case_sensitive = case_sensitive
        self.search_matches = []
        self.search_index = -1
        
        if not text:
            self.viewport().update()
            return
        
        # Find all matches
        for line_idx, line_parts in enumerate(self.lines):
            line_text = self._line_text(line_parts)
            search_line = line_text if case_sensitive else line_text.lower()
            search_term = text if case_sensitive else text.lower()
            
            start = 0
            while True:
                pos = search_line.find(search_term, start)
                if pos == -1:
                    break
                self.search_matches.append((line_idx, pos, pos + len(text)))
                start = pos + 1
    
        # Move to first match if any found
        if self.search_matches:
            self.search_index = 0
            self._scroll_to_match()
    
        self.viewport().update()

    def next_match(self):
        """Move to the next search match"""
        if not self.search_matches:
            return
    
        self.search_index = (self.search_index + 1) % len(self.search_matches)
        self._scroll_to_match()
        self.viewport().update()

    def prev_match(self):
        """Move to the previous search match"""
        if not self.search_matches:
            return
    
        self.search_index = (self.search_index - 1) % len(self.search_matches)
        self._scroll_to_match()
        self.viewport().update()

    def _scroll_to_match(self):
        """Scroll to center the current match in the viewport"""
        if not self.search_matches or self.search_index < 0:
            return

        match_line, _, _ = self.search_matches[self.search_index]

        # Calculate viewport dimensions
        viewport_height = self.viewport().height()
        if self.horizontalScrollBar().isVisible():
            viewport_height -= self.horizontalScrollBar().height()

        visible_lines = max(1, viewport_height // self.line_height)
        total_lines = len(self.lines)

        # Calculate target scroll position to center the match
        target_center_line = match_line
        target_start_line = max(0, target_center_line - visible_lines // 2)

        # Temporarily disable auto-scroll for search
        was_auto_scroll = self.auto_scroll
        self.auto_scroll = False
        
        # Set scroll offset to show the match in center
        self.scroll_offset = target_start_line
        
        # Update scrollbar
        self.update_scrollbar()
        
        # Restore auto-scroll state if we were at bottom
        if was_auto_scroll and target_start_line + visible_lines >= total_lines:
            self.auto_scroll = True

        # Force viewport update
        self.viewport().update()

    def clear_search(self):
        """Clear search results and highlights"""
        self.search_text = ""
        self.search_matches = []
        self.search_index = -1
        self.search_case_sensitive = False
        self.viewport().update()
