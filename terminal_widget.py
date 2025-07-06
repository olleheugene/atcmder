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
        
        y = 5
        for line_idx in range(start_line, end_line):
            line_parts = self.lines[line_idx]
            x = 5 - h_scroll_offset
            y_line = y + self.font_metrics.ascent()
            
            # Selection highlight
            if self.selection_start and self.selection_end:
                sel_start, sel_end = sorted([self.selection_start, self.selection_end])
                if sel_start[0] <= line_idx <= sel_end[0]:
                    sel_col_start = sel_start[1] if line_idx == sel_start[0] else 0
                    sel_col_end = sel_end[1] if line_idx == sel_end[0] else self._line_length(line_parts)
                    x1 = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:sel_col_start])
                    x2 = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:sel_col_end])
                    x2 = min(x2, effective_width - 5)
                    painter.fillRect(x1, y, x2 - x1, self.line_height, QColor(60, 120, 200, 120))
            
            # Search highlight
            if self.search_text:
                for idx, match in enumerate(self.search_matches):
                    if match[0] == line_idx:
                        start_px = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:match[1]])
                        end_px = x + self.font_metrics.horizontalAdvance(self._line_text(line_parts)[:match[2]])
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
                        painter.drawText(x, y_line, text_part)
                        x += text_width
            
            if (self.cursor_visible and 
                line_idx == self.cursor_line and 
                self.hasFocus()):
                cursor_x = 5 - h_scroll_offset + self.font_metrics.horizontalAdvance(
                    self._line_text(line_parts)[:self.cursor_col]
                )
                if cursor_x < effective_width - 5:
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

    def _pos_to_linecol(self, pos):
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
        
        x = pos.x() - 5 + self.horizontalScrollBar().value()
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
        self.font = font
        self.font_metrics = QFontMetrics(self.font)
        self.line_height = self.font_metrics.height()
        self.char_width = self.font_metrics.horizontalAdvance('M')
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
            self.cursor_col = self._line_length(self.lines[-1])
        
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
            self.scroll_offset = 0
            self.update_scrollbar()
            self.viewport().update()

    def toggle_auto_scroll(self):
        """Toggle auto-scrolling on or off."""
        self.set_auto_scroll(not self.auto_scroll)

    def is_auto_scroll_enabled(self):
        """Check if auto-scrolling is enabled."""
        return self.auto_scroll

    def scroll_to_bottom(self):
        """Scroll to the bottom of the terminal."""
        if self.lines:
            self.scroll_offset = len(self.lines)
            self.update_scrollbar()
            self.viewport().update()

    def start_search(self, text, case_sensitive=False):
        """Start a search and highlight all matches."""
        self.search_text = text
        self.search_matches = []
        self.search_index = -1
        if text:
            for i, line in enumerate(self.lines):
                line_text = self._line_text(line)
                if not case_sensitive:
                    line_text_cmp = line_text.lower()
                    text_cmp = text.lower()
                else:
                    line_text_cmp = line_text
                    text_cmp = text
                idx = line_text_cmp.find(text_cmp)
                while idx != -1:
                    self.search_matches.append((i, idx, idx + len(text)))
                    idx = line_text_cmp.find(text_cmp, idx + 1)
        self.viewport().update()

    def clear_search(self):
        self.search_text = ""
        self.search_matches = []
        self.search_index = -1
        self.viewport().update()

    def next_match(self):
        if not self.search_matches:
            return
        self.search_index = (self.search_index + 1) % len(self.search_matches)
        line, start, end = self.search_matches[self.search_index]
        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        # 검색된 줄이 화면 중앙에 오도록 정확히 스크롤 조정
        target_offset = total_lines - visible_lines - (line - visible_lines // 2)
        self.scroll_offset = max(0, min(target_offset, total_lines - visible_lines))
        self.auto_scroll = False  # 검색 이동 시 자동 스크롤 해제
        self.update_scrollbar()
        self.viewport().update()

    def prev_match(self):
        if not self.search_matches:
            return
        self.search_index = (self.search_index - 1) % len(self.search_matches)
        line, start, end = self.search_matches[self.search_index]
        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        target_offset = total_lines - visible_lines - (line - visible_lines // 2)
        self.scroll_offset = max(0, min(target_offset, total_lines - visible_lines))
        self.auto_scroll = False
        self.update_scrollbar()
        self.viewport().update()
