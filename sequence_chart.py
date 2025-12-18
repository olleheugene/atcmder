from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsLineItem, QGraphicsTextItem, QGraphicsPathItem, QMainWindow
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath, QFont
from PySide6.QtCore import Qt, QRectF
from datetime import datetime

class SequenceChartWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequence Chart")
        self.resize(600, 800)
        self.chart_widget = SequenceChartWidget()
        self.setCentralWidget(self.chart_widget)

    def add_message(self, direction, message, timestamp=None):
        self.chart_widget.add_message(direction, message, timestamp)

    def clear(self):
        self.chart_widget.clear()

class SequenceChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.layout.addWidget(self.view)
        
        self.host_x = 100
        self.device_x = 400
        self.current_y = 50
        self.step_y = 40
        
        self.host_line = None
        self.device_line = None
        
        self.setup_chart()
        
    def setup_chart(self):
        # Draw initial vertical lines
        pen = QPen(Qt.black)
        pen.setWidth(2)
        
        # Host Line
        self.host_line = self.scene.addLine(self.host_x, 20, self.host_x, 1000, pen)
        host_label = self.scene.addText("Host (PC)")
        host_label.setPos(self.host_x - host_label.boundingRect().width() / 2, 0)
        
        # Device Line
        self.device_line = self.scene.addLine(self.device_x, 20, self.device_x, 1000, pen)
        device_label = self.scene.addText("Device")
        device_label.setPos(self.device_x - device_label.boundingRect().width() / 2, 0)
        
    def add_message(self, direction, message, timestamp=None):
        # Extend vertical lines if needed
        if self.current_y > self.host_line.line().y2() - 50:
            new_y2 = self.current_y + 500
            self.host_line.setLine(self.host_x, 20, self.host_x, new_y2)
            self.device_line.setLine(self.device_x, 20, self.device_x, new_y2)
            self.scene.setSceneRect(0, 0, 500, new_y2 + 50)

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
        time_text_left.setPos(self.host_x - 85, self.current_y - 10)
        
        # Time on right of Device
        time_text_right = self.scene.addText(current_time)
        time_text_right.setDefaultTextColor(Qt.gray)
        time_text_right.setFont(font)
        time_text_right.setPos(self.device_x + 10, self.current_y - 10)

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
        # Truncate message if too long
        display_msg = message.strip()
        if len(display_msg) > 40:
            display_msg = display_msg[:37] + "..."
            
        text_item = self.scene.addText(display_msg)
        text_item.setDefaultTextColor(color)
        
        # Center text on the line
        text_width = text_item.boundingRect().width()
        center_x = (self.host_x + self.device_x) / 2
        text_item.setPos(center_x - text_width / 2, self.current_y - 20)
        
        self.current_y += self.step_y
        
        # Auto scroll to bottom
        self.view.ensureVisible(0, self.current_y, 1, 1)

    def clear(self):
        self.scene.clear()
        self.current_y = 50
        self.setup_chart()
        self.scene.setSceneRect(0, 0, 500, 1000)
        self.view.verticalScrollBar().setValue(0)
        self.current_y = 50
        self.setup_chart()
