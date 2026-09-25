import sys
import math
import csv
import serial
import serial.tools.list_ports
from datetime import datetime
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QPushButton, QComboBox, QLabel, QFileDialog,
    QHBoxLayout, QVBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView

import pyqtgraph as pg


# =========================
# BIKE METER GAUGE (SMOOTH NEEDLE + MIN/MAX)
# =========================
class CircularGauge(QWidget):
    def __init__(self, title, min_v, max_v, unit, color):
        super().__init__()
        self.title = title
        self.min_v = min_v
        self.max_v = max_v
        self.unit = unit
        self.color = QColor(color)
        self.value = 0
        self.display_value = 0  # smooth animation
        self.setMinimumSize(210, 180)

        # smooth animation timer
        self.anim = QTimer(self)
        self.anim.timeout.connect(self.animate)
        self.anim.start(30)

    def setValue(self, v):
        self.value = v

    def animate(self):
        # ease toward target value
        self.display_value += (self.value - self.display_value) * 0.15
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        center = rect.center()
        radius = min(rect.width(), rect.height()) // 2 + 10

        p.fillRect(rect, QColor(18, 18, 25))

        # base arc
        p.setPen(QPen(QColor(70, 70, 80), 8))
        p.drawArc(rect.adjusted(20, 20, -20, -10), 180 * 16, 180 * 16)

        # colored zones
        zones = [
            (0.0, 0.6, QColor(0, 220, 120)),
            (0.6, 0.85, QColor(255, 200, 0)),
            (0.85, 1.0, QColor(255, 60, 60)),
        ]
        for z0, z1, c in zones:
            p.setPen(QPen(c, 8))
            start = int(180 * 16 * z0)
            span = int(180 * 16 * (z1 - z0))
            p.drawArc(rect.adjusted(20, 20, -20, -10), 180 * 16 + start, span)

        # ratio
        ratio = (self.display_value - self.min_v) / (self.max_v - self.min_v)
        ratio = max(0, min(1, ratio))

        # needle
        angle = math.radians(180 + 180 * ratio)
        nx = center.x() + math.cos(angle) * (radius - 35)
        ny = center.y() + math.sin(angle) * (radius - 35)
        p.setPen(QPen(self.color, 3))
        p.drawLine(QPointF(center.x(), center.y()), QPointF(nx, ny))

        p.setBrush(self.color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, 5, 5)

        # ticks
        p.setPen(QPen(QColor(120, 120, 140), 2))
        for i in range(0, 11):
            ang = math.radians(180 + (180 / 10) * i)
            x1 = center.x() + math.cos(ang) * (radius - 20)
            y1 = center.y() + math.sin(ang) * (radius - 20)
            x2 = center.x() + math.cos(ang) * (radius - 5)
            y2 = center.y() + math.sin(ang) * (radius - 5)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # digital value
        p.setPen(Qt.GlobalColor.white)
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        p.drawText(rect.adjusted(0, 40, 0, 0), Qt.AlignmentFlag.AlignCenter,
                   f"{self.display_value:.1f} {self.unit}")

        # min/max labels
        p.setPen(QColor(160, 160, 180))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(10, rect.height() - 10, str(self.min_v))
        p.drawText(rect.width() - 35, rect.height() - 10, str(self.max_v))

        # title
        p.setPen(self.color)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(12, 20, self.title)


# =========================
# CARD CONTAINER (SHADOW)
# =========================
class Card(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background: #14141c;
                border-radius: 12px;
            }
        """)
        self.setGraphicsEffect(self.shadow())

    def shadow(self):
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        eff = QGraphicsDropShadowEffect()
        eff.setBlurRadius(18)
        eff.setXOffset(0)
        eff.setYOffset(4)
        eff.setColor(QColor(0, 0, 0, 150))
        return eff


# =========================
# RTC PANEL
# =========================
class RTCPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.time = "--:--:--"
        self.date = "----‑--‑--"
        self.setFixedHeight(120)
        self.setStyleSheet("background:#121218;border-radius:12px;")

    def setRTC(self, ts):
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            self.time = dt.strftime("%H:%M:%S")
            self.date = dt.strftime("%Y-%m-%d")
        except:
            self.time = "--:--:--"
            self.date = "----‑--‑--"
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(18, 18, 25))

        p.setPen(QColor(0, 255, 140))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(12, 30, "RTC TIME")

        p.setPen(Qt.GlobalColor.white)
        p.setFont(QFont("Consolas", 16))
        p.drawText(12, 65, self.time)
        p.setFont(QFont("Consolas", 11))
        p.drawText(12, 90, self.date)


# =========================
# MAP WIDGET (DARK TILE + TRACK)
# =========================
class MapWidget(QWebEngineView):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(360)
        self.setHtml(self._html(23.7, 90.4))

    def _html(self, lat, lon):
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>html, body, #map {{ height: 100%; margin: 0; }}</style>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map = L.map('map').setView([{lat}, {lon}], 16);
                L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                    maxZoom: 19
                }}).addTo(map);

                var marker = L.marker([{lat}, {lon}]).addTo(map);
                var path = L.polyline([[{lat}, {lon}]], {{color:'red'}}).addTo(map);

                window.updateMarker = function(lat, lon) {{
                    marker.setLatLng([lat, lon]);
                    path.addLatLng([lat, lon]);
                    map.setView([lat, lon]);
                }}
            </script>
        </body>
        </html>
        """

    def updatePosition(self, lat, lon):
        js = f"updateMarker({lat}, {lon});"
        self.page().runJavaScript(js)


# =========================
# MAIN DASHBOARD
# =========================
class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SCADA V2 - WATER + GPS + RTC SYSTEM")
        self.showFullScreen()

        self.setStyleSheet("""
            QMainWindow { background: #0d0d12; }
            QLabel { color: white; }
            QPushButton {
                background: #1f1f2a; color: white; padding: 8px 14px;
                border-radius: 8px; font-weight: bold;
            }
            QPushButton:hover { background: #2a2a3a; }
            QComboBox {
                background: #1f1f2a; color: white; padding: 6px;
                border-radius: 6px;
            }
        """)

        self.serial = None
        self.connected = False
        self.log = []

        # history buffers
        self.tds_hist = deque(maxlen=200)
        self.ec_hist = deque(maxlen=200)
        self.temp_hist = deque(maxlen=200)
        self.ph_hist = deque(maxlen=200)

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout()
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)
        central.setLayout(root)

        # Gauges
        gauges = QHBoxLayout()
        for g in [
            CircularGauge("TDS", 0, 2000, "ppm", "#00aaff"),
            CircularGauge("EC", 0, 5, "mS/cm", "#00ff88"),
            CircularGauge("TEMP", 0, 60, "°C", "#ffaa00"),
            CircularGauge("pH", 0, 14, "pH", "#aa00ff")
        ]:
            card = Card()
            lay = QVBoxLayout(card)
            lay.addWidget(g)
            gauges.addWidget(card)
        self.tds, self.ec, self.temp, self.ph = [gauges.itemAt(i).widget().layout().itemAt(0).widget() for i in range(4)]
        root.addLayout(gauges)

        # Map + RTC
        mid = QHBoxLayout()
        self.map = MapWidget()
        map_card = Card()
        map_layout = QVBoxLayout(map_card)
        map_layout.addWidget(self.map)

        self.rtc = RTCPanel()
        rtc_card = Card()
        rtc_layout = QVBoxLayout(rtc_card)
        rtc_layout.addWidget(self.rtc)

        mid.addWidget(map_card, 3)
        mid.addWidget(rtc_card, 1)
        root.addLayout(mid)

        # GPS Info
        self.gpsInfo = QLabel("Lat: -- | Lon: -- | Speed: -- km/h | Sats: --")
        self.gpsInfo.setStyleSheet("background:#121218;padding:8px;border-radius:8px;")
        root.addWidget(self.gpsInfo)

        # Charts
        self.plot = pg.PlotWidget()
        self.plot.setBackground('#121218')
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.addLegend()

        self.curve_tds = self.plot.plot(pen=pg.mkPen('#00aaff', width=2), name="TDS")
        self.curve_ec = self.plot.plot(pen=pg.mkPen('#00ff88', width=2), name="EC")
        self.curve_temp = self.plot.plot(pen=pg.mkPen('#ffaa00', width=2), name="TEMP")
        self.curve_ph = self.plot.plot(pen=pg.mkPen('#aa00ff', width=2), name="pH")

        chart_card = Card()
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.addWidget(self.plot)
        root.addWidget(chart_card)

        # Bottom Controls
        bottom = QHBoxLayout()
        self.port = QComboBox()
        self.refresh_ports()

        self.btn = QPushButton("CONNECT ESP32")
        self.btn.clicked.connect(self.toggle)

        self.export = QPushButton("EXPORT CSV")
        self.export.clicked.connect(self.save_csv)

        self.status = QLabel("DISCONNECTED")
        self.status.setStyleSheet("color:red;font-size:14px;")

        bottom.addWidget(self.port)
        bottom.addWidget(self.btn)
        bottom.addWidget(self.export)
        bottom.addWidget(self.status)
        root.addLayout(bottom)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all)
        self.timer.start(1000)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

    def refresh_ports(self):
        self.port.clear()
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            self.port.addItem("NO COM PORT FOUND")
            return
        for p in ports:
            self.port.addItem(f"{p.device} - {p.description}")

    def toggle(self):
        if not self.connected:
            try:
                text = self.port.currentText()
                if "NO COM" in text:
                    self.status.setText("NO DEVICE")
                    return
                port = text.split(" - ")[0].strip()
                self.serial = serial.Serial(port, 115200, timeout=1)
                self.connected = True
                self.status.setText("CONNECTED")
                self.status.setStyleSheet("color:lime")
                self.btn.setText("DISCONNECT")
            except Exception as e:
                self.status.setText("FAILED")
                print("ERROR:", e)
        else:
            if self.serial:
                self.serial.close()
            self.connected = False
            self.status.setText("DISCONNECTED")
            self.status.setStyleSheet("color:red")
            self.btn.setText("CONNECT ESP32")

    def update_all(self):
        tds = ec = temp = ph = 0
        ts = ""
        lat = lon = speed = 0.0
        sats = 0

        if self.connected and self.serial:
            try:
                line = self.serial.readline().decode(errors='ignore').strip()
                if not line or line.count(",") < 3:
                    return

                data = line.split(",")
                if len(data) >= 9:
                    tds = float(data[0]); ec = float(data[1])
                    temp = float(data[2]); ph = float(data[3])
                    ts = data[4]
                    lat = float(data[5]); lon = float(data[6])
                    speed = float(data[7]); sats = int(float(data[8]))
                elif len(data) == 4:
                    tds, ec, temp, ph = map(float, data)
                else:
                    return
            except Exception as e:
                print("Parse error:", e)
                return

        self.tds.setValue(tds)
        self.ec.setValue(ec)
        self.temp.setValue(temp)
        self.ph.setValue(ph)

        if ts:
            self.rtc.setRTC(ts)
        if lat != 0.0 or lon != 0.0:
            self.map.updatePosition(lat, lon)

        self.gpsInfo.setText(f"Lat: {lat:.6f} | Lon: {lon:.6f} | Speed: {speed:.2f} km/h | Sats: {sats}")

        self.tds_hist.append(tds)
        self.ec_hist.append(ec)
        self.temp_hist.append(temp)
        self.ph_hist.append(ph)

        x = list(range(len(self.tds_hist)))
        self.curve_tds.setData(x, list(self.tds_hist))
        self.curve_ec.setData(x, list(self.ec_hist))
        self.curve_temp.setData(x, list(self.temp_hist))
        self.curve_ph.setData(x, list(self.ph_hist))

        self.log.append([datetime.now(), tds, ec, temp, ph, ts, lat, lon, speed, sats])

    def save_csv(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV (*.csv)")
        if file:
            with open(file, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Time", "TDS", "EC", "TEMP", "pH", "RTC", "Lat", "Lon", "Speed", "Sats"])
                w.writerows(self.log)
            self.status.setText("CSV SAVED")


# =========================
# RUN
# =========================
app = QApplication(sys.argv)
win = Dashboard()
win.show()
sys.exit(app.exec())