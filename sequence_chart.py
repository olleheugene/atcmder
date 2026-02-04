from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsLineItem, 
    QGraphicsTextItem, QGraphicsPathItem, QMainWindow, QFileDialog, QMessageBox, QPushButton
)
from PySide6.QtGui import (
    QPen, QColor, QPainter, QPainterPath, QFont, QFontMetrics, QAction, 
    QPdfWriter, QPageSize
)
from PySide6.QtCore import Qt, QRectF, QTimer
from datetime import datetime
import re

DISPLAY_TEXT_LEN = 70

class SequenceChartWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequence Chart")
        self.resize(700, 800)
        
        toolbar = self.addToolBar("Main")
        save_btn = QPushButton("Save as PDF")
        save_btn.clicked.connect(self.save_as_pdf)
        toolbar.addWidget(save_btn)
        
        self.hex_btn = QPushButton("HEX")
        self.hex_btn.setCheckable(True)
        self.hex_btn.clicked.connect(self.toggle_hex_mode)
        toolbar.addWidget(self.hex_btn)
        
        self.chart_widget = SequenceChartWidget()
        self.setCentralWidget(self.chart_widget)

    def add_message(self, direction, message, timestamp=None):
        self.chart_widget.add_message(direction, message, timestamp)

    def clear(self):
        self.chart_widget.clear()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            QTimer.singleShot(0, self.chart_widget.initial_layout)
        except Exception:
            pass

    def toggle_hex_mode(self, checked):
        self.chart_widget.set_hex_mode(checked)

    def save_as_pdf(self):
        timestamp = datetime.now().strftime("%m%d_%H%M%S")
        default_name = f"sequence_chart_{timestamp}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save as PDF", default_name, "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        # Save current colors to restore later
        restore_items = []
        for msg in self.chart_widget.messages:
            # Text
            text_item = msg['text_item']
            old_text_color = text_item.defaultTextColor()
            text_item.setDefaultTextColor(Qt.black)
            
            # Line
            line_item = msg['line_item']
            old_line_pen = line_item.pen()
            new_line_pen = QPen(Qt.black)
            new_line_pen.setWidth(old_line_pen.width())
            line_item.setPen(new_line_pen)

            # Arrow
            arrow_item = msg['arrow_item']
            old_arrow_pen = arrow_item.pen()
            old_arrow_brush = arrow_item.brush()
            
            new_arrow_pen = QPen(Qt.black)
            new_arrow_pen.setWidth(old_arrow_pen.width())
            arrow_item.setPen(new_arrow_pen)
            arrow_item.setBrush(Qt.black)
            
            restore_items.append({
                'text_item': text_item,
                'old_text_color': old_text_color,
                'line_item': line_item,
                'old_line_pen': old_line_pen,
                'arrow_item': arrow_item,
                'old_arrow_pen': old_arrow_pen,
                'old_arrow_brush': old_arrow_brush,
            })

        try:
            writer = QPdfWriter(file_path)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setResolution(300)
            writer.setCreator("AT Commander")
            writer.setTitle("Sequence Chart")
            
            painter = QPainter(writer)
            
            scene = self.chart_widget.scene
            scene_rect = scene.sceneRect()
            
            layout = writer.pageLayout()
            page_rect = layout.paintRectPixels(writer.resolution())
            
            margin = 20
            available_width = page_rect.width() - 2 * margin
            available_height = page_rect.height() - 2 * margin
            
            scale = available_width / scene_rect.width()
            scene_page_height = available_height / scale
            
            y_pos = 0
            while y_pos < scene_rect.height():
                if y_pos > 0:
                    writer.newPage()
                
                source_rect = QRectF(
                    scene_rect.x(), scene_rect.y() + y_pos, 
                    scene_rect.width(), min(scene_page_height, scene_rect.height() - y_pos)
                )
                target_height = source_rect.height() * scale
                target_rect = QRectF(margin, margin, available_width, target_height)
                
                scene.render(painter, target_rect, source_rect)
                y_pos += scene_page_height
                
            painter.end()
            QMessageBox.information(self, "Success", f"Saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save PDF: {e}")
        finally:
            # Restore colors
            for item in restore_items:
                item['text_item'].setDefaultTextColor(item['old_text_color'])
                item['line_item'].setPen(item['old_line_pen'])
                item['arrow_item'].setPen(item['old_arrow_pen'])
                item['arrow_item'].setBrush(item['old_arrow_brush'])

class SequenceChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.layout.addWidget(self.view)
        
        self.host_x = 100
        self.device_x = 300
        self.current_y = 50
        self.step_y = 40

        self.host_line = None
        self.device_line = None

        self.messages = []
        self.hex_mode = False

        self.setup_chart()
        self.recalculate_layout()
        self.auto_scroll = True
        try:
            self.view.verticalScrollBar().valueChanged.connect(self._on_vscroll)
        except Exception:
            pass
            
    def set_hex_mode(self, enabled):
        self.hex_mode = enabled
        self.recalculate_layout()

    def _to_hex(self, text):
        return ' '.join(f"{ord(c):02X}" for c in text)
        
    def setup_chart(self):
        # Draw initial vertical lines
        pen = QPen(Qt.black)
        pen.setWidth(2)
        
        # Host Line
        self.host_line = self.scene.addLine(self.host_x, 20, self.host_x, 1000, pen)
        self.host_label = self.scene.addText("Host (PC)")
        self.host_label.setPos(self.host_x - self.host_label.boundingRect().width() / 2, 0)
        self.device_line = self.scene.addLine(self.device_x, 20, self.device_x, 1000, pen)
        self.device_label = self.scene.addText("Device")
        self.device_label.setPos(self.device_x - self.device_label.boundingRect().width() / 2, 0)
        self.scene.setSceneRect(0, 0, 800, 1100)
        
    def add_message(self, direction, message, timestamp=None):
        # Extend vertical lines if needed
        if self.current_y > self.host_line.line().y2() - 50:
            new_y2 = self.current_y + 500
            self.host_line.setLine(self.host_x, 20, self.host_x, new_y2)
            self.device_line.setLine(self.device_x, 20, self.device_x, new_y2)
            self.scene.setSceneRect(0, 0, self.scene.sceneRect().width(), new_y2 + 50)

        # Add timestamps
        if timestamp:
            current_time = timestamp
        else:
            current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Time on left of Host
        time_text_left = self.scene.addText(current_time)
        time_text_left.setDefaultTextColor(Qt.gray)
        font = time_text_left.font()
        font.setPointSize(8)
        time_text_left.setFont(font)
        time_text_left.setPos(self.host_x - 75, self.current_y - 10)
        
        # Time on right of Device
        time_text_right = self.scene.addText(current_time)
        time_text_right.setDefaultTextColor(Qt.gray)
        time_text_right.setFont(font)
        time_text_right.setPos(self.device_x + 5, self.current_y - 10)

        pen = QPen(Qt.black)
        pen.setWidth(1)
        
        if direction == "TX": # Host -> Device
            start_x = self.host_x
            end_x = self.device_x
            color = QColor("lightgreen")
        else: # Device -> Host
            start_x = self.device_x
            end_x = self.host_x
            color = QColor("white")
            
        pen.setColor(color)
        
        # Draw arrow line
        line = self.scene.addLine(start_x, self.current_y, end_x, self.current_y, pen)
        
        # Draw arrow head
        arrow_path = QPainterPath()
        arrow_size = 10
        if direction == "TX":
            arrow_path.moveTo(end_x, self.current_y)
            arrow_path.lineTo(end_x - arrow_size, self.current_y - arrow_size / 3)
            arrow_path.lineTo(end_x - arrow_size, self.current_y + arrow_size / 3)
            arrow_path.closeSubpath()
        else:
            arrow_path.moveTo(end_x, self.current_y)
            arrow_path.lineTo(end_x + arrow_size, self.current_y - arrow_size / 3)
            arrow_path.lineTo(end_x + arrow_size, self.current_y + arrow_size / 3)
            arrow_path.closeSubpath()
            
        arrow_item = self.scene.addPath(arrow_path, pen, color)
        
        # Draw text
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        full_msg = ansi_escape.sub('', message).strip()
        
        target_text = full_msg
        if self.hex_mode:
            target_text = self._to_hex(full_msg)

        display_msg = target_text
        if len(target_text) > DISPLAY_TEXT_LEN:
            display_msg = target_text[:DISPLAY_TEXT_LEN] + "..."

        text_item = self.scene.addText(display_msg)
        text_item.setDefaultTextColor(color)
        font = text_item.font()
        font.setPointSize(11)
        text_item.setFont(font)
        text_item.setToolTip(target_text)

        fm = QFontMetrics(text_item.font())
        text_width = fm.horizontalAdvance(display_msg)
        center_x = (self.host_x + self.device_x) / 2.0
        text_item.setPos(center_x - text_width / 2.0, self.current_y - 20)

        msg = {
            'direction': direction,
            'y': self.current_y,
            'line_item': line,
            'arrow_item': arrow_item,
            'text_item': text_item,
            'time_left': time_text_left,
            'time_right': time_text_right,
            'color': color,
            'full_text': full_msg,
        }
        self.messages.append(msg)

        self.current_y += self.step_y
        
        current_gap = abs(self.device_x - self.host_x)
        if text_width + 100 > current_gap:
            self.recalculate_layout()

        # Auto scroll to bottom only when enabled (user hasn't scrolled away)
        if self.auto_scroll:
            try:
                sb = self.view.verticalScrollBar()
                sb.setValue(sb.maximum())
                self.view.ensureVisible((self.host_x + self.device_x) / 2.0, self.current_y, 1, 1)
                self.view.viewport().update()
            except Exception:
                self.view.ensureVisible(0, self.current_y, 1, 1)

    def clear(self):
        self.scene.clear()
        self.current_y = 50
        self.setup_chart()
        self.scene.setSceneRect(0, 0, 500, 1000)
        self.view.verticalScrollBar().setValue(0)
        self.current_y = 50
        self.setup_chart()

    def update_positions(self):
        """Update positions of all items based on current host_x and device_x."""

        host_y2 = self.host_line.line().y2()
        self.host_line.setLine(self.host_x, 20, self.host_x, host_y2)
        self.device_line.setLine(self.device_x, 20, self.device_x, host_y2)

        if hasattr(self, 'host_label') and self.host_label:
            self.host_label.setPos(self.host_x - self.host_label.boundingRect().width() / 2, 0)
        if hasattr(self, 'device_label') and self.device_label:
            self.device_label.setPos(self.device_x - self.device_label.boundingRect().width() / 2, 0)

        self.scene.setSceneRect(0, 0, max(self.view.viewport().width(), self.device_x + 200), max(1100, host_y2 + 50))

        self._update_message_positions()

    def _update_message_positions(self):
        fm_cache = {}
        for msg in self.messages:
            y = msg['y']
            direction = msg['direction']
            color = msg.get('color', QColor('white'))
            if direction == 'TX':
                start_x = self.host_x
                end_x = self.device_x
            else:
                start_x = self.device_x
                end_x = self.host_x

            line_item = msg['line_item']
            line_item.setLine(start_x, y, end_x, y)
            # Update arrow path
            arrow_path = QPainterPath()
            arrow_size = 10
            if direction == 'TX':
                arrow_path.moveTo(end_x, y)
                arrow_path.lineTo(end_x - arrow_size, y - arrow_size / 3)
                arrow_path.lineTo(end_x - arrow_size, y + arrow_size / 3)
                arrow_path.closeSubpath()
            else:
                arrow_path.moveTo(end_x, y)
                arrow_path.lineTo(end_x + arrow_size, y - arrow_size / 3)
                arrow_path.lineTo(end_x + arrow_size, y + arrow_size / 3)
                arrow_path.closeSubpath()
            msg['arrow_item'].setPath(arrow_path)
            # Update timestamps
            if msg.get('time_left'):
                msg['time_left'].setPos(self.host_x - 75, y - 10)
            if msg.get('time_right'):
                msg['time_right'].setPos(self.device_x + 5, y - 10)
            # Update text position and elide if needed
            text_item = msg['text_item']
            full_text = msg.get('full_text', text_item.toPlainText())
            
            target_text = full_text
            if self.hex_mode:
                target_text = self._to_hex(full_text)
            
            display_text = target_text
            if len(target_text) > DISPLAY_TEXT_LEN:
                display_text = target_text[:DISPLAY_TEXT_LEN] + "...              "
            
            if text_item.toPlainText() != display_text:
                text_item.setPlainText(display_text)
                text_item.setToolTip(target_text)
                
            font = text_item.font() 
            key = (font.toString())
            if key not in fm_cache:
                fm_cache[key] = QFontMetrics(font)
            fm = fm_cache[key]
            
            tw = fm.horizontalAdvance(display_text)
            center_x = (self.host_x + self.device_x) / 2.0
            text_item.setPos(center_x - tw / 2.0, y - 20)

    def resizeEvent(self, event):
        self.recalculate_layout()
        super().resizeEvent(event)

    def initial_layout(self):
        self.recalculate_layout()
        try:
            self.view.viewport().update()
        except Exception:
            pass

    def recalculate_layout(self):
        view_w = self.view.viewport().width()
        if view_w <= 0:
            view_w = self.width()
        if view_w <= 0:
            view_w = 600
            
        max_text_w = 0
        default_fm = QFontMetrics(QFont())
        for msg in self.messages:
            full_text = msg.get('full_text', '')
            
            target_text = full_text
            if self.hex_mode:
                target_text = self._to_hex(full_text)
            
            text = target_text
            if len(target_text) > DISPLAY_TEXT_LEN:
                text = target_text[:DISPLAY_TEXT_LEN] + "..."

            if 'text_item' in msg:
                fm = QFontMetrics(msg['text_item'].font())
                w = fm.horizontalAdvance(text)
            else:
                w = default_fm.horizontalAdvance(text)
            if w > max_text_w:
                max_text_w = w
        
        target_gap = max(200, max_text_w + 100)
        min_margin = 50
        
        if target_gap + 2 * min_margin <= view_w:
            center_x = view_w / 2
            self.host_x = center_x - target_gap / 2
            self.device_x = center_x + target_gap / 2
        else:
            self.host_x = min_margin
            self.device_x = min_margin + target_gap
        
        self.update_positions()

    def _on_vscroll(self, value):
        """Called when the user scrolls the view. If scrollbar is at bottom, enable auto-scroll; otherwise disable it."""
        sb = self.view.verticalScrollBar()
        try:
            if value >= sb.maximum():
                self.auto_scroll = True
            else:
                self.auto_scroll = False
        except Exception:
            self.auto_scroll = False
