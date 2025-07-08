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

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        self.setPalette(palette)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Fast rendering with QTimer
        self._update_pending = False
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(16)  # 60fps
        self._update_timer.timeout.connect(self._do_update)
        self._update_timer.start()

        # Block selection variables
        self.selection_start = None  # (line, col)
        self.selection_end = None    # (line, col)
        self.is_selecting = False

        # Cursor variables
        self.cursor_line = 0
        self.cursor_col = 0
        self.cursor_visible = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(500)  # 0.5s blink
        self._cursor_timer.timeout.connect(self._toggle_cursor)
        self._cursor_timer.start()

        self.verticalScrollBar().setRange(0, 1)
        self.horizontalScrollBar().setRange(0, 1)

        self.search_text = ""
        self.search_matches = []
        self.search_index = -1
        
        # Line number settings
        self.show_line_numbers = False
        self.line_number_width = 0
        self.line_number_padding = 10  # Padding between line numbers and text
        
        # Timestamp settings
        self.show_timestamps = False
        self.timestamp_width = 0
        self.timestamp_padding = 4  # Padding between timestamp and text

    def _toggle_cursor(self):
        """Toggle cursor visibility for blinking effect"""
        self.cursor_visible = not self.cursor_visible
        self.viewport().update()

    def set_cursor(self, line, col):
        """Set cursor position"""
        self.cursor_line = line
        self.cursor_col = col
        self.viewport().update()

    def set_cursor_to_end(self):
        """Set cursor to the end of the last line"""
        if self.lines:
            self.cursor_line = len(self.lines) - 1
            self.cursor_col = len(self._line_text(self.lines[-1]))
        else:
            self.cursor_line = 0
            self.cursor_col = 0
        self.viewport().update()

    def append_text(self, text):
        """Add text to terminal with optional timestamp"""
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
        
        # Get current timestamp
        from datetime import datetime
        current_time = datetime.now()
        timestamp_str = current_time.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm format
        
        for i, line in enumerate(lines):
            if i > 0 or not self.lines:
                self.lines.append([])
                
            # Add timestamp to the beginning of each new line if enabled
            if self.show_timestamps and (i > 0 or not self.lines or len(self.lines) == 1):
                # Add timestamp with a different color
                timestamp_color = QColor(100, 100, 100)  # Gray timestamp
                timestamp_text = f"{timestamp_str} "
                self.lines[-1].append((timestamp_text, timestamp_color))
            
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
        
        # Update line number width if line numbers are enabled
        if self.show_line_numbers:
            # Only update if the number of lines changed significantly to avoid excessive calculations
            lines_count = len(self.lines)
            if not hasattr(self, '_last_line_count') or abs(lines_count - self._last_line_count) > 10:
                self._update_line_number_width()
                self._last_line_count = lines_count
        
        # Update timestamp width if timestamps are enabled
        if self.show_timestamps:
            self._update_timestamp_width()
        
        # Ensure the scroll offset remains stable after adding data to avoid view shifting
        visible_lines = max(1, self.viewport().height() // self.line_height)

        # If auto-scroll is disabled, adjust the scroll offset to maintain the current position when new content is added
        if not self.auto_scroll and self.scroll_offset > 0:
            # Calculate the number of newly added lines
            lines_after = len(self.lines)
            new_lines_added = lines_after - lines_before

            # If text was added to the existing last line (without a line break), no offset adjustment is needed
            # Only adjust the offset if new lines were added
            if new_lines_added > 0:
                self.scroll_offset += new_lines_added

            # If text was added to the existing last line (without a line break), no offset adjustment is needed
            # (This is special handling for data coming in one line at a time)
            if new_lines_added == 0 and len(self.lines) > 0:
                last_line_length_after = len(self._line_text(self.lines[-1]))
                if last_line_length_after > last_line_length_before:
                    # If the length of the last line has increased but is not actually visible on the screen
                    # This is to maintain the scroll position even if text is added to the same line
                    self.viewport().update()

        # Schedule an update
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

    def _schedule_update(self):
        if not self._update_pending:
            self._update_pending = True

    def _do_update(self):
        if self._update_pending:
            self.update_scrollbar()
            self.viewport().update()
            self._update_pending = False

    def parse_ansi_text(self, text):
        """Parse ANSI color sequences (color only)"""
        result = []
        ansi_escape = re.compile(r'\x1B\[[0-9;]*m')
        current_color = self.current_color
        pos = 0
        for match in ansi_escape.finditer(text):
            if pos < match.start():
                result.append((text[pos:match.start()], current_color))
            code_str = match.group()[2:-1]
            if code_str == '0' or code_str == '':
                current_color = self.default_color
            else:
                for code in code_str.split(';'):
                    if code.isdigit():
                        color_code = int(code)
                        if color_code in self.ansi_colors:
                            current_color = self.ansi_colors[color_code]
                        elif color_code == 0:
                            current_color = self.default_color
            pos = match.end()
        if pos < len(text):
            result.append((text[pos:], current_color))
        self.current_color = current_color
        return result

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setFont(self.font)
        painter.fillRect(self.viewport().rect(), QColor(30, 30, 30))
        
        if not self.lines:
            painter.end()
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
        
        # Calculate text start position (after line numbers and timestamps)
        text_start_x = 0
        if self.show_line_numbers:
            text_start_x += self.line_number_width
        if self.show_timestamps:
            text_start_x += self.timestamp_width
        
        if self.auto_scroll:
            start_line = max(0, total_lines - visible_lines)
            self.scroll_offset = 0
        else:
            max_offset = max(0, total_lines - visible_lines)
            if self.scroll_offset > max_offset:
                self.scroll_offset = max_offset
            start_line = max(0, total_lines - visible_lines - self.scroll_offset)
        end_line = min(total_lines, start_line + visible_lines)
        if start_line >= total_lines:
            painter.end()
            return

        # Draw line number background if enabled
        if self.show_line_numbers and self.line_number_width > 0:
            line_number_rect = viewport_rect.adjusted(0, 0, -(effective_width - self.line_number_width)-12, 0)
            painter.fillRect(line_number_rect, QColor(40, 40, 40))  # Slightly lighter background
            
            # Draw separator line
            painter.setPen(QColor(60, 60, 60))
            painter.drawLine(self.line_number_width - self.line_number_padding // 2, 0, 
                           self.line_number_width - self.line_number_padding // 2, effective_height)
        
        y = 5
        for line_idx in range(start_line, end_line):
            line_parts = self.lines[line_idx]
            x = text_start_x + 5 - h_scroll_offset
            y_line = y + self.font_metrics.ascent()
            
            # Draw line number
            if self.show_line_numbers:
                painter.setPen(QColor(120, 120, 120))  # Gray color for line numbers
                line_number = str(line_idx + 1)  # 1-based line numbering
                line_number_x = self.line_number_width - self.line_number_padding - self.font_metrics.horizontalAdvance(line_number)
                painter.drawText(line_number_x, y_line, line_number)
            
            # Selection highlight
            if self.selection_start and self.selection_end:
                sel_start, sel_end = sorted([self.selection_start, self.selection_end])
                if sel_start[0] <= line_idx <= sel_end[0]:
                    sel_col_start = sel_start[1] if line_idx == sel_start[0] else 0
                    sel_col_end = sel_end[1] if line_idx == sel_end[0] else self._line_length(line_parts)
                    x1 = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:sel_col_start])
                    x2 = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:sel_col_end])
                    x2 = min(x2, effective_width - 5)
                    # Only draw if within visible text area
                    if x2 > text_start_x and x1 < effective_width:
                        x1 = max(x1, text_start_x)
                        painter.fillRect(x1, y, x2 - x1, self.line_height, QColor(60, 120, 200, 120))
            
            # Search highlight
            if self.search_text:
                for idx, match in enumerate(self.search_matches):
                    if match[0] == line_idx:
                        start_px = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:match[1]])
                        end_px = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:match[2]])
                        # Only draw if within visible text area
                        if end_px > text_start_x and start_px < effective_width:
                            start_px = max(start_px, text_start_x)
                            # Use different color for current selected search result
                            if idx == self.search_index:
                                painter.fillRect(start_px, y, end_px - start_px, self.line_height, QColor(255, 120, 0, 180))  # Dark orange
                            else:
                                painter.fillRect(start_px, y, end_px - start_px, self.line_height, QColor(255, 200, 50, 120))  # Light yellow

            for text_part, color in line_parts:
                if text_part and x < effective_width - 5:
                    painter.setPen(color)
                    text_width = self.font_metrics.horizontalAdvance(text_part)
                    if x + text_width > effective_width - 5:
                        available_width = effective_width - 5 - x
                        if available_width > 0:
                            truncated_text = ""
                            current_width = 0
                            for char in text_part:
                                char_width = self.font_metrics.horizontalAdvance(char)
                                if current_width + char_width > available_width:
                                    break
                                truncated_text += char
                                current_width += char_width
                            if truncated_text:
                                painter.drawText(x, y_line, truncated_text)
                        break
                    else:
                        # Only draw if text is in visible area
                        if x + text_width > text_start_x:
                            painter.drawText(x, y_line, text_part)
                        x += text_width
            
            if (self.cursor_visible and 
                line_idx == self.cursor_line and 
                self.hasFocus()):
                cursor_x = text_start_x + 5 - h_scroll_offset + self.font_metrics.horizontalAdvance(
                    self._line_text(line_parts)[:self.cursor_col]
                )
                if cursor_x >= text_start_x and cursor_x < effective_width - 5:
                    painter.setPen(QColor(200, 255, 200))
                    painter.drawRect(cursor_x, y, 2, self.line_height)
            
            y += self.line_height
            if y > effective_height:
                break
        
        painter.end()

    def _line_text(self, line_parts):
        return ''.join(part for part, _ in line_parts)

    def _line_length(self, line_parts):
        return len(self._line_text(line_parts))

    def update_scrollbar(self):
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        if hasattr(self, 'font'):
            self.font_metrics = QFontMetrics(self.font)
            self.line_height = self.font_metrics.height()
            self.char_width = self.font_metrics.horizontalAdvance('M')
        
        if self.line_height <= 0:
            self.line_height = 20
        if self.char_width <= 0:
            self.char_width = 10
        
        viewport_height = self.viewport().height()
        viewport_width = self.viewport().width()
        
        if viewport_height <= 0 or viewport_width <= 0:
            return
        
        effective_height = viewport_height
        effective_width = viewport_width
        
        if self.horizontalScrollBar().isVisible():
            effective_height -= self.horizontalScrollBar().height()
        
        if self.verticalScrollBar().isVisible():
            effective_width -= self.verticalScrollBar().width()
        
        visible_lines = max(1, effective_height // self.line_height)
        total_lines = len(self.lines)
        
        # Vertical Scrollbar 업데이트
        self.verticalScrollBar().blockSignals(True)
        
        min_range = 10
        
        if total_lines > visible_lines:
            max_scroll = total_lines - visible_lines
            
            # Scroll offset should not exceed the valid range
            if self.scroll_offset > max_scroll:
                self.scroll_offset = max_scroll

            # If the scroll range is too small, adjust to the minimum value
            if max_scroll < min_range:
                self.verticalScrollBar().setRange(0, min_range)
                self.verticalScrollBar().setPageStep(min_range)
            else:
                self.verticalScrollBar().setRange(0, max_scroll)
                self.verticalScrollBar().setPageStep(visible_lines)
                
            self.verticalScrollBar().setSingleStep(1)
            
            # Adjust scroll position based on the auto_scroll state
            if self.auto_scroll:
                self.verticalScrollBar().setValue(max_scroll)
                self.scroll_offset = 0
            else:
                # Calculate scroll position - accurately maintain user-scrolled position
                scroll_value = max(0, max_scroll - self.scroll_offset)

                # Bug fix: Ensure the value does not exceed the range
                if scroll_value <= self.verticalScrollBar().maximum():
                    self.verticalScrollBar().setValue(scroll_value)
        else:
            # If there are no lines to display, return early
            self.verticalScrollBar().setRange(0, min_range)
            self.verticalScrollBar().setPageStep(min_range)
            self.verticalScrollBar().setValue(0)
            
            if self.scroll_offset != 0:
                self.scroll_offset = 0
                
            # If there are not many lines, enable auto-scrolling
            self.auto_scroll = True
            
        self.verticalScrollBar().blockSignals(False)
        
        # Horizontal Scrollbar 업데이트
        max_line_width = 0
        if self.lines:
            for line_parts in self.lines:
                line_width = sum(self.font_metrics.horizontalAdvance(text_part) for text_part, _ in line_parts)
                max_line_width = max(max_line_width, line_width)
        
        content_width = max_line_width + (self.char_width * 2) + 10
        
        self.horizontalScrollBar().blockSignals(True)
        if content_width > effective_width:
            max_h_scroll = content_width - effective_width
            self.horizontalScrollBar().setRange(0, max_h_scroll)
            self.horizontalScrollBar().setPageStep(int(effective_width * 0.8))
            self.horizontalScrollBar().setSingleStep(self.char_width)
        else:
            # Set a minimum range to always show the horizontal scrollbar
            self.horizontalScrollBar().setRange(0, 10)
            self.horizontalScrollBar().setPageStep(10)
            self.horizontalScrollBar().setValue(0)
        self.horizontalScrollBar().blockSignals(False)


    def _update_line_number_width(self):
        """Calculate the width needed for line numbers"""
        if not self.show_line_numbers:
            self.line_number_width = 0
            return
        
        # Calculate width based on maximum line count
        max_lines = max(len(self.lines), MAX_TERMINAL_LINES)
        line_count_str = str(max_lines)
        if len(self.lines) < 1000:
            self.line_number_width = self.font_metrics.horizontalAdvance(line_count_str) + self.line_number_padding
        else:
            # For more than 1000 lines, use a fixed width to avoid excessive width
            self.line_number_width = self.font_metrics.horizontalAdvance(line_count_str) + self.line_number_padding + 5

    def _update_timestamp_width(self):
        """Calculate the width needed for timestamps"""
        if not self.show_timestamps:
            self.timestamp_width = 0
            return
        
        # Use a sample timestamp to calculate width
        sample_timestamp = "12:34:56.789 "  # HH:MM:SS.mmm format without brackets
        # self.timestamp_width = self.font_metrics.horizontalAdvance(sample_timestamp) + self.timestamp_padding
        self.timestamp_width = self.timestamp_padding

    def set_show_timestamps(self, show):
        """Enable or disable timestamp display"""
        self.show_timestamps = show
        self._update_timestamp_width()
        self.update_scrollbar()
        self.viewport().update()

    def set_show_line_numbers(self, show):
        """Enable or disable line number display"""
        self.show_line_numbers = show
        self._update_line_number_width()
        self.update_scrollbar()
        self.viewport().update()

    def set_show_time(self, show):
        """Enable or disable time display"""
        self.show_time = show
        self.viewport().update()

    def wheelEvent(self, event):
        # Check the direction of the mouse wheel scroll
        delta = event.angleDelta().y()
        scroll_lines = 3  # Scroll speed adjustment

        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        max_scroll = max(0, total_lines - visible_lines)
        
        old_offset = self.scroll_offset
        old_auto_scroll = self.auto_scroll
        
        if delta > 0:  # Scroll up (mouse wheel forward)
            # When scrolling up, always disable auto-scrolling
            self.auto_scroll = False
            # Increase scroll offset (scroll up)
            self.scroll_offset = min(self.scroll_offset + scroll_lines, max_scroll)
        else:  # Scroll down (mouse wheel backward)
            # Decrease offset when scrolling down
            new_offset = max(0, self.scroll_offset - scroll_lines)
            self.scroll_offset = new_offset

            # Check if reached the bottom
            if new_offset <= 0:
                self.auto_scroll = True  # If reached the bottom, enable auto-scrolling
            else:
                self.auto_scroll = False  # If still in the middle of scrolling

        # Update scrollbar and viewport only if the state has changed
        if old_offset != self.scroll_offset or old_auto_scroll != self.auto_scroll:
            # Debug message: Print state after wheel event
            # print(f"Wheel: delta={delta}, offset={self.scroll_offset}, auto={self.auto_scroll}")
            
            self.update_scrollbar()
            self.viewport().update()
        
        event.accept()

    def scrollContentsBy(self, dx, dy):
        if dy != 0:  # Vertical scroll change
            visible_lines = max(1, self.viewport().height() // self.line_height)
            total_lines = len(self.lines)
            
            if total_lines > visible_lines:
                scroll_value = self.verticalScrollBar().value()
                max_value = self.verticalScrollBar().maximum()
                max_scroll = total_lines - visible_lines
                
                # Calculate offset based on the current scroll value
                old_offset = self.scroll_offset
                self.scroll_offset = max_scroll - scroll_value

                # Check if scrollbar is at the bottom (with 5 pixels tolerance)
                tolerance = 5
                if scroll_value >= max_value - tolerance:
                    if not self.auto_scroll:
                        self.auto_scroll = True  # If at the bottom, enable auto-scrolling
                else:
                    if self.auto_scroll:
                        self.auto_scroll = False  # If not, disable auto-scrolling

                # Debug message: Print scroll state
                # print(f"Scroll: value={scroll_value}/{max_value}, offset={self.scroll_offset}, auto={self.auto_scroll}")
        
        self.viewport().update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            line, col = self._pos_to_linecol(event.pos())
            self.selection_start = (line, col)
            self.selection_end = (line, col)
            self.is_selecting = True
            self.viewport().update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            line, col = self._pos_to_linecol(event.pos())
            self.selection_end = (line, col)
            self.viewport().update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_selecting = False
            self.viewport().update()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to select word"""
        if event.button() == Qt.LeftButton:
            line, col = self._pos_to_linecol(event.pos())
            
            # Get the text of the clicked line
            if line < len(self.lines):
                text = self._line_text(self.lines[line])
                
                # Find word boundaries
                start_col, end_col = self._find_word_boundaries(text, col)
                
                # Set selection
                self.selection_start = (line, start_col)
                self.selection_end = (line, end_col)
                self.is_selecting = False
                self.viewport().update()

    def _pos_to_linecol(self, pos):
        """Convert pixel position to line/column coordinates"""
        # 스크롤바 두께를 고려한 위치 계산
        effective_height = self.viewport().height()
        if self.horizontalScrollBar().isVisible():
            effective_height -= self.horizontalScrollBar().height()
        
        y = pos.y() - 5
        visible_lines = max(1, effective_height // self.line_height)
        total_lines = len(self.lines)
        start_line = max(0, total_lines - visible_lines - self.scroll_offset)
        line = y // self.line_height + start_line
        
        if line < 0:
            line = 0
        if line >= len(self.lines):
            line = len(self.lines) - 1 if self.lines else 0
        
        # Calculate text start position (after line numbers and timestamps)
        text_start_x = 0
        if self.show_line_numbers:
            text_start_x += self.line_number_width
        if self.show_timestamps:
            text_start_x += self.timestamp_width
        
        # Adjust x position to account for line numbers and timestamps
        x = pos.x() - 5 - text_start_x + self.horizontalScrollBar().value()
        
        # If click is in the line number or timestamp area, set column to 0
        if (self.show_line_numbers or self.show_timestamps) and pos.x() < text_start_x:
            return (line, 0)
        
        text = self._line_text(self.lines[line]) if self.lines else ""
        col = 0
        acc = 0
        
        for i, ch in enumerate(text):
            w = self.font_metrics.horizontalAdvance(ch)
            if acc + w // 2 >= x:
                col = i
                break
            acc += w
        else:
            col = len(text)
        
        return (line, col)

    def _find_word_boundaries(self, text, col):
        """Find the start and end of a word at the given column"""
        if not text or col >= len(text):
            return col, col
        
        # Word characters: letters, numbers, underscore
        import string
        word_chars = string.ascii_letters + string.digits + '_'
        
        # If clicked on non-word character, select just that character
        if text[col] not in word_chars:
            return col, col + 1
        
        # Find start of word
        start = col
        while start > 0 and text[start - 1] in word_chars:
            start -= 1
        
        # Find end of word
        end = col
        while end < len(text) and text[end] in word_chars:
            end += 1
        
        return start, end

    def copy_selection(self):
        """Copy selected text to clipboard"""
        if not self.selection_start or not self.selection_end:
            return
    
        sel_start, sel_end = sorted([self.selection_start, self.selection_end])
        lines = []
    
        for i in range(sel_start[0], sel_end[0] + 1):
            if i >= len(self.lines):
                break
            line = self._line_text(self.lines[i])
            if i == sel_start[0] and i == sel_end[0]:
                # Selection is within one line
                lines.append(line[sel_start[1]:sel_end[1]])
            elif i == sel_start[0]:
                # First line of selection
                lines.append(line[sel_start[1]:])
            elif i == sel_end[0]:
                # Last line of selection
                lines.append(line[:sel_end[1]])
            else:
                # Middle lines of selection
                lines.append(line)
    
        text = '\n'.join(lines)
        if text:
            QGuiApplication.clipboard().setText(text)
            print(f"Copied {len(text)} characters to clipboard")

    def clear(self):
        """Clear the terminal"""
        self.lines = []
        self.cursor_line = 0
        self.cursor_col = 0
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.scroll_offset = 0
        self.auto_scroll = True
        self.update_scrollbar()
        self.viewport().update()

    def set_font(self, font):
        """Set the terminal font"""
        self.font = font
        self.font_metrics = QFontMetrics(self.font)
        self.line_height = self.font_metrics.height()
        self.char_width = self.font_metrics.horizontalAdvance('M')
        
        # Update line number width if line numbers are enabled
        if self.show_line_numbers:
            self._update_line_number_width()
        
        # Update timestamp width if timestamps are enabled
        if self.show_timestamps:
            self._update_timestamp_width()
            
        self.update_scrollbar()
        self.viewport().update()

    def set_auto_scroll(self, enabled):
        """Enable or disable auto scroll"""
        self.auto_scroll = enabled

    def start_search(self, text, case_sensitive=False):
        """Start text search"""
        self.search_text = text
        self.search_matches = []
        self.search_index = -1
        
        if not text:
            self.viewport().update()
            return
        
        # Search through all lines
        for line_idx, line_parts in enumerate(self.lines):
            line_text = self._line_text(line_parts)
            search_text = text if case_sensitive else text.lower()
            line_search_text = line_text if case_sensitive else line_text.lower()
            
            start = 0
            while True:
                pos = line_search_text.find(search_text, start)
                if pos == -1:
                    break
                self.search_matches.append((line_idx, pos, pos + len(text)))
                start = pos + 1
        
        if self.search_matches:
            self.search_index = 0
        
        self.viewport().update()

    def clear_search(self):
        """Clear search highlights"""
        self.search_text = ""
        self.search_matches = []
        self.search_index = -1
        self.viewport().update()

    def next_match(self):
        """Go to next search match"""
        if self.search_matches:
            self.search_index = (self.search_index + 1) % len(self.search_matches)
            self.viewport().update()

    def prev_match(self):
        """Go to previous search match"""
        if self.search_matches:
            self.search_index = (self.search_index - 1) % len(self.search_matches)
            self.viewport().update()

    def remove_last_char(self):
        """Remove the last character from the last line"""
        if not self.lines:
            return
        if self.lines[-1]:
            last_text, last_color = self.lines[-1][-1]
            if len(last_text) > 1:
                # Shorten the last text part
                self.lines[-1][-1] = (last_text[:-1], last_color)
            else:
                # Remove the last text part completely
                self.lines[-1].pop()
                if not self.lines[-1] and len(self.lines) > 1:
                    # Remove empty line if it's not the only line
                    self.lines.pop()
        else:
            # Current line is empty, remove previous line
            if len(self.lines) > 1:
                self.lines.pop()
        self._schedule_update()
