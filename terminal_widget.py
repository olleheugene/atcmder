from PySide6.QtWidgets import QAbstractScrollArea, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPalette
from PySide6.QtCore import Qt, QTimer
import re

class TerminalWidget(QAbstractScrollArea):
    def __init__(self, parent=None, font_family="Monaco", font_size=14):
        super().__init__(parent)
        self.font = QFont(font_family, font_size)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.font_metrics = QFontMetrics(self.font)
        self.line_height = self.font_metrics.height()
        self.char_width = self.font_metrics.horizontalAdvance('M')

        # Store terminal data
        self.lines = []
        self.max_lines = 10000  # Maximum line count limit (performance guarantee)
        self.scroll_offset = 0

        # Rendering cache (per line)
        self._render_cache = {}

        # ANSI color mapping
        self.ansi_colors = {
            30: QColor(0, 0, 0),        # Black
            31: QColor(205, 49, 49),    # Red
            32: QColor(13, 188, 121),   # Green
            33: QColor(229, 229, 16),   # Yellow
            34: QColor(36, 114, 200),   # Blue
            35: QColor(188, 63, 188),   # Magenta
            36: QColor(17, 168, 205),   # Cyan
            37: QColor(229, 229, 229),  # White
            90: QColor(102, 102, 102),  # Bright Black
            91: QColor(241, 76, 76),    # Bright Red
            92: QColor(35, 209, 139),   # Bright Green
            93: QColor(245, 245, 67),   # Bright Yellow
            94: QColor(59, 142, 234),   # Bright Blue
            95: QColor(214, 112, 214),  # Bright Magenta
            96: QColor(41, 184, 219),   # Bright Cyan
            97: QColor(255, 255, 255),  # Bright White
        }
        self.default_color = QColor(200, 200, 200)
        self.current_color = self.default_color

        # Scrollbar policy
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Background color settings
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        self.setPalette(palette)

        # Batch update timer
        self.pending_text = ""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.flush_pending_text)
        self.update_timer.setSingleShot(True)

        self._max_line_width = 0  # Maximum line width cache

    def append_text(self, text):
        """Append text - batch processing"""
        self.pending_text += text
        self.update_timer.start(16)  # Process after 16ms (60fps)

    def flush_pending_text(self):
        """Process buffered text"""
        if self.pending_text:
            self._real_append_text(self.pending_text)
            self.pending_text = ""
            # Call callback to update cursor position after flush
            if hasattr(self, "_cursor_update_callback"):
                self._cursor_update_callback()

    def set_cursor_update_callback(self, callback):
        """Register callback to update cursor position after flush_pending_text"""
        self._cursor_update_callback = callback

    def _real_append_text(self, text):
        """Process actual text appending"""
        if not text:
            return

        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')

        for i, line in enumerate(lines):
            if i > 0:
                self.lines.append([])
            idx = 0
            while idx < len(line):
                if line[idx] == '\b':
                    self.remove_last_char()
                    idx += 1
                else:
                    ansi_match = re.match(r'\x1B\[[0-?]*[ -/]*[@-~]', line[idx:])
                    if ansi_match:
                        ansi_seq = ansi_match.group()
                        parsed = self.parse_ansi_text(ansi_seq)
                        if not self.lines:
                            self.lines.append([])
                        self.lines[-1].extend(parsed)
                        idx += len(ansi_seq)
                    elif line[idx] == '\t':
                        if not self.lines:
                            self.lines.append([])
                        idx += 1
                    else:
                        if not self.lines:
                            self.lines.append([])
                        self.lines[-1].append((line[idx], self.current_color))
                        idx += 1
            if i == 0 and not self.lines:
                self.lines.append([])

        if text.endswith('\n') and self.lines and self.lines[-1]:
            self.lines.append([])

        # Maximum line count limit (performance guarantee)
        if len(self.lines) > self.max_lines:
            del self.lines[:len(self.lines) - self.max_lines]
            self._recalculate_max_line_width()

        # Invalidate cache
        self._render_cache.clear()

        self.scroll_offset = 0
        self.update_scrollbar()
        self.viewport().update()

    def parse_ansi_text(self, text):
        """Parse ANSI sequences and return text with color information"""
        result = []
        ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
        current_color = self.current_color
        pos = 0
        
        for match in ansi_escape.finditer(text):
            # Regular text part
            if pos < match.start():
                text_part = text[pos:match.start()]
                if text_part:
                    result.append((text_part, current_color))

            # Parse ANSI codes
            ansi_code = match.group()
            if ansi_code.endswith('m'):
                try:
                    code_str = ansi_code[2:-1]  # take the numeric part from \x1B[...m
                    if code_str == '0' or code_str == '':  # Reset
                        current_color = self.default_color
                    elif ';' in code_str:  # Error code handling
                        codes = code_str.split(';')
                        for code in codes:
                            if code.isdigit():
                                color_code = int(code)
                                if color_code in self.ansi_colors:
                                    current_color = self.ansi_colors[color_code]
                                elif color_code == 0:
                                    current_color = self.default_color
                    elif code_str.isdigit():
                        color_code = int(code_str)
                        if color_code in self.ansi_colors:
                            current_color = self.ansi_colors[color_code]
                        elif color_code == 0:
                            current_color = self.default_color
                except ValueError:
                    pass
            
            pos = match.end()
        
        # 남은 텍스트
        if pos < len(text):
            remaining_text = text[pos:]
            if remaining_text:
                result.append((remaining_text, current_color))
        
        # 현재 색상 업데이트
        self.current_color = current_color
        
        return result

    def clear(self):
        """화면 클리어"""
        self.lines = []
        self.scroll_offset = 0
        self.current_color = self.default_color
        self.update_scrollbar()
        self.viewport().update()

    def update_scrollbar(self):
        """스크롤바 업데이트 - 개선된 버전"""
        if self.line_height <= 0:
            self.line_height = 20
        
        viewport_height = self.viewport().height()
        viewport_width = self.viewport().width()
        
        if viewport_height <= 0 or viewport_width <= 0:
            return
        
        visible_lines = max(1, viewport_height // self.line_height)
        total_lines = len(self.lines)
        
        # 세로 스크롤바
        self.verticalScrollBar().blockSignals(True)
        if total_lines > visible_lines:
            max_scroll = total_lines - visible_lines
            self.verticalScrollBar().setRange(0, max_scroll)
            self.verticalScrollBar().setPageStep(visible_lines)
            self.verticalScrollBar().setSingleStep(1)
            
            # 스크롤 위치 설정 (최신 내용이 보이도록)
            scroll_value = max_scroll - self.scroll_offset
            self.verticalScrollBar().setValue(scroll_value)
        else:
            self.verticalScrollBar().setRange(0, 0)
            self.verticalScrollBar().setValue(0)
        self.verticalScrollBar().blockSignals(False)
        
        # 가로 스크롤바
        content_width = self._max_line_width + 20  # 캐시 사용!
        self.horizontalScrollBar().blockSignals(True)
        if content_width > viewport_width:
            max_h_scroll = content_width - viewport_width
            self.horizontalScrollBar().setRange(0, max_h_scroll)
            self.horizontalScrollBar().setPageStep(viewport_width)
            self.horizontalScrollBar().setSingleStep(20)
        else:
            self.horizontalScrollBar().setRange(0, 0)
            self.horizontalScrollBar().setValue(0)
        self.horizontalScrollBar().blockSignals(False)

    def paintEvent(self, event):
        """부분 렌더링: 화면에 보이는 라인만 그리기 (성능 최적화)"""
        painter = QPainter(self.viewport())
        painter.setFont(self.font)
        painter.fillRect(self.viewport().rect(), QColor(30, 30, 30))

        if not self.lines:
            painter.end()
            return

        viewport_rect = self.viewport().rect()
        visible_lines = max(1, viewport_rect.height() // self.line_height)
        total_lines = len(self.lines)
        start_line = max(0, total_lines - visible_lines - self.scroll_offset)
        end_line = min(total_lines, start_line + visible_lines)

        h_scroll_offset = self.horizontalScrollBar().value()
        y = 5

        for line_idx in range(start_line, end_line):
            last_x = 5 - h_scroll_offset  # 마지막으로 그린 글자의 x좌표
            if line_idx < len(self.lines):
                line_parts = self.lines[line_idx]
                x = last_x
                for text_part, color in line_parts:
                    if text_part:
                        text_width = self.font_metrics.horizontalAdvance(text_part)
                        # 화면에 보이는 부분만 drawText
                        if x + text_width > 0 and x < viewport_rect.width():
                            painter.setPen(color)
                            painter.drawText(x, y + self.font_metrics.ascent(), text_part)
                        x += text_width
                last_x = x  # 마지막 글자 뒤 x좌표 저장

            # 커서 그리기: 마지막으로 그린 글자 바로 뒤에!
            if getattr(self, "cursor_visible", False) and line_idx == getattr(self, "cursor_line", -1):
                painter.setPen(QColor(255, 255, 255))
                painter.setBrush(QColor(255, 255, 255))
                painter.drawRect(last_x, y, 2, self.line_height)
            y += self.line_height

        painter.end()

    def resizeEvent(self, event):
        """크기 변경 시 캐시 무효화 및 스크롤바 업데이트"""
        super().resizeEvent(event)
        self._render_cache.clear()
        self.update_scrollbar()

    def on_vertical_scroll(self, value):
        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        if total_lines > visible_lines:
            max_scroll = total_lines - visible_lines
            self.scroll_offset = max_scroll - value
            self.viewport().update()

    def on_horizontal_scroll(self, value):
        self._render_cache.clear()
        self.viewport().update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        scroll_lines = 3
        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        max_scroll = max(0, total_lines - visible_lines)
        if delta > 0:
            self.scroll_offset = min(self.scroll_offset + scroll_lines, max_scroll)
        else:
            self.scroll_offset = max(0, self.scroll_offset - scroll_lines)
        self.update_scrollbar()
        self.viewport().update()
        event.accept()

    def scrollContentsBy(self, dx, dy):
        if dy != 0:
            visible_lines = max(1, self.viewport().height() // self.line_height)
            total_lines = len(self.lines)
            if total_lines > visible_lines:
                scroll_value = self.verticalScrollBar().value()
                max_scroll = total_lines - visible_lines
                self.scroll_offset = max_scroll - scroll_value
        self.viewport().update()

    def keyPressEvent(self, event):
        """키 이벤트 - 스크롤 관련만 처리"""
        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        max_scroll = max(0, total_lines - visible_lines)
        
        if event.key() == Qt.Key.Key_PageUp:
            self.scroll_offset = min(self.scroll_offset + visible_lines, max_scroll)
            self.update_scrollbar()
            self.viewport().update()
        elif event.key() == Qt.Key.Key_PageDown:
            self.scroll_offset = max(0, self.scroll_offset - visible_lines)
            self.update_scrollbar()
            self.viewport().update()
        elif event.key() == Qt.Key.Key_Home and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.scroll_offset = max_scroll
            self.update_scrollbar()
            self.viewport().update()
        elif event.key() == Qt.Key.Key_End and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.scroll_offset = 0
            self.update_scrollbar()
            self.viewport().update()
        else:
            super().keyPressEvent(event)

    def handle_backspace(self):
        """백스페이스 처리 - 개선된 버전"""
        if self.current_input_buffer:
            # 버퍼에서 마지막 문자 제거
            deleted_char = self.current_input_buffer[-1]
            self.current_input_buffer = self.current_input_buffer[:-1]
            self.history_index = -1  # 편집 시 히스토리 인덱스 리셋
            
            # 화면에서 문자 지우기 - 더 명확한 백스페이스 시퀀스
            self.terminal_widget.append_text('\b')  # 백스페이스만 전송
            
            self.show_current_input()

    def remove_last_char(self):
        """현재 줄에서 마지막 문자(글자) 하나를 지움"""
        if not self.lines:
            return
        # 마지막 줄이 비어있지 않으면
        if self.lines[-1]:
            last_text, last_color = self.lines[-1][-1]
            if len(last_text) > 1:
                # 여러 글자면 마지막 글자만 제거
                self.lines[-1][-1] = (last_text[:-1], last_color)
            else:
                # 한 글자면 해당 부분 삭제
                self.lines[-1].pop()
                # 줄이 완전히 비었고 첫 줄이 아니면 줄도 삭제
                if not self.lines[-1] and len(self.lines) > 1:
                    self.lines.pop()
        else:
            # 현재 줄이 비어있으면 이전 줄로 이동해서 삭제
            if len(self.lines) > 1:
                self.lines.pop()
                self.remove_last_char()

    def _recalculate_max_line_width(self):
        """전체 라인에서 최대 너비 재계산 (드물게만 호출)"""
        self._max_line_width = 0
        for line_parts in self.lines:
            line_width = sum(self.font_metrics.horizontalAdvance(t) for t, _ in line_parts if t)
            if line_width > self._max_line_width:
                self._max_line_width = line_width

    def set_cursor_position(self, line_idx, col_idx):
        """커서 위치를 외부에서 지정할 수 있게 하는 메서드"""
        self.cursor_line = line_idx
        self.cursor_col = col_idx
        self.viewport().update()

    def show_cursor(self, show=True):
        self.cursor_visible = show
        self.viewport().update()