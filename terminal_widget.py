from PySide6.QtWidgets import QAbstractScrollArea, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPalette
from PySide6.QtCore import Qt, QTimer
import re

MAX_TERMINAL_LINES = 2000

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

        # ANSI 색상 캐싱
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

        # 빠른 렌더링을 위한 QTimer 사용
        self._update_pending = False
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(16)  # 60fps
        self._update_timer.timeout.connect(self._do_update)
        self._update_timer.start()

    def append_text(self, text):
        """텍스트 추가 (최적화: paintEvent 직접 호출하지 않고, update 예약)"""
        if not text:
            return
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
        # if text.endswith('\n'):
        #     self.lines.append([])
        # scrollback limit (한 번에 삭제)
        if len(self.lines) > MAX_TERMINAL_LINES:
            del self.lines[:len(self.lines) - MAX_TERMINAL_LINES]
        self.scroll_offset = 0
        self._schedule_update()

    def _schedule_update(self):
        """update 예약 (중복 호출 방지)"""
        if not self._update_pending:
            self._update_pending = True

    def _do_update(self):
        if self._update_pending:
            self.update_scrollbar()
            self.viewport().update()
            self._update_pending = False

    def parse_ansi_text(self, text):
        """ANSI 시퀀스 파싱 (색상만)"""
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
        """최적화된 paintEvent: 한 줄씩 drawText"""
        painter = QPainter(self.viewport())
        painter.setFont(self.font)
        painter.fillRect(self.viewport().rect(), QColor(30, 30, 30))
        if not self.lines:
            painter.end()
            return
        viewport_rect = self.viewport().rect()
        visible_lines = max(1, viewport_rect.height() // self.line_height)
        h_scroll_offset = self.horizontalScrollBar().value()
        total_lines = len(self.lines)
        start_line = max(0, total_lines - visible_lines - self.scroll_offset)
        end_line = min(total_lines, start_line + visible_lines)
        y = 5
        for line_idx in range(start_line, end_line):
            line_parts = self.lines[line_idx]
            x = 5 - h_scroll_offset
            y_line = y + self.font_metrics.ascent()
            for text_part, color in line_parts:
                if text_part:
                    painter.setPen(color)
                    painter.drawText(x, y_line, text_part)
                    x += self.font_metrics.horizontalAdvance(text_part)
            y += self.line_height
        painter.end()

    def update_scrollbar(self):
        """스크롤바 업데이트 (최적화)"""
        if self.line_height <= 0:
            self.line_height = 20
        viewport_height = self.viewport().height()
        viewport_width = self.viewport().width()
        if viewport_height <= 0 or viewport_width <= 0:
            return
        visible_lines = max(1, viewport_height // self.line_height)
        total_lines = len(self.lines)
        self.verticalScrollBar().blockSignals(True)
        if total_lines > visible_lines:
            max_scroll = total_lines - visible_lines
            self.verticalScrollBar().setRange(0, max_scroll)
            self.verticalScrollBar().setPageStep(visible_lines)
            self.verticalScrollBar().setSingleStep(1)
            scroll_value = max_scroll - self.scroll_offset
            self.verticalScrollBar().setValue(scroll_value)
        else:
            self.verticalScrollBar().setRange(0, 0)
            self.verticalScrollBar().setValue(0)
        self.verticalScrollBar().blockSignals(False)
        # 가로 스크롤바
        max_line_width = 0
        for line_parts in self.lines:
            line_width = sum(self.font_metrics.horizontalAdvance(text_part) for text_part, _ in line_parts)
            max_line_width = max(max_line_width, line_width)
        content_width = max_line_width + 20
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

    def wheelEvent(self, event):
        """휠 이벤트"""
        delta = event.angleDelta().y()
        scroll_lines = 3
        
        visible_lines = max(1, self.viewport().height() // self.line_height)
        total_lines = len(self.lines)
        max_scroll = max(0, total_lines - visible_lines)
        
        if delta > 0:  # 위로 스크롤
            self.scroll_offset = min(self.scroll_offset + scroll_lines, max_scroll)
        else:  # 아래로 스크롤
            self.scroll_offset = max(0, self.scroll_offset - scroll_lines)
        
        self.update_scrollbar()
        self.viewport().update()
        event.accept()

    def scrollContentsBy(self, dx, dy):
        """스크롤바 드래그 처리 - 가로/세로 모두 지원"""
        if dy != 0:  # 세로 스크롤
            visible_lines = max(1, self.viewport().height() // self.line_height)
            total_lines = len(self.lines)
            
            if total_lines > visible_lines:
                scroll_value = self.verticalScrollBar().value()
                max_scroll = total_lines - visible_lines
                
                # 스크롤 오프셋 계산
                self.scroll_offset = max_scroll - scroll_value
    
        # 가로 스크롤은 자동으로 처리됨 (horizontalScrollBar().value() 사용)
        
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