from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2 import QtCore
from PIL import Image, PpmImagePlugin
from pdf2image import convert_from_path
import sys
import os
import img2pdf
import configparser


def repleceFileDialog() -> bool:
    qm = QMessageBox()
    ret = qm.question(
        None, '', "Zastąpić pdf?", qm.No | qm.Yes)
    if ret == qm.No:
        return True
    return False


def get_concat_v(im1, im2):
    dst = Image.new('RGB', (im1.width, im1.height + im2.height))
    dst.paste(im1, (0, 0))
    dst.paste(im2, (0, im1.height))
    return dst


class Worker(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, image1, image2, outputPath, statusBarPointer):
        super().__init__()
        self.front_side = image1
        self.back_side = image2
        self.status = statusBarPointer
        self.out = outputPath

    @QtCore.Slot()
    def work(self):
        self.status.showMessage('Przycinanie...')
        width, height = self.front_side.size
        im1 = self.front_side.crop((0, 0, width//2, height//2))
        im2 = self.front_side.crop((width//2, 0, width, height//2))
        im3 = self.front_side.crop((0, height//2, width//2, height))
        im4 = self.front_side.crop((width//2, height//2, width, height))
        im_front = [im1, im2, im3, im4]

        width, height = self.back_side.size
        im1b = self.back_side.crop((0, 0, width//2, height//2))
        im2b = self.back_side.crop((width//2, 0, width, height//2))
        im3b = self.back_side.crop((0, height//2, width//2, height))
        im4b = self.back_side.crop((width//2, height//2, width, height))
        im_back = [im1b, im2b, im3b, im4b]

        self.status.showMessage('Łączenie...')

        config = configparser.ConfigParser()
        try:
            config.read('settings.ini')
            quality = int(config['DEFAULT']['quality'])
        except KeyError:
            quality = 90

        if quality < 10 or quality > 100:
            quality = 90

        for i in range(4):
            self.status.showMessage('Łączenie ' + str(i*25) + '%...')
            tmp = get_concat_v(im_front[i], im_back[i])
            tmp.save(str(i)+'.jpg', quality=quality)

        self.status.showMessage('Zapisywanie...')
        # specify paper size (A4)
        a4inpt = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
        layout_fun = img2pdf.get_layout_fun(a4inpt)
        for i in range(4):
            with open(self.out + str(i)+'.pdf', "wb") as f:
                f.write(img2pdf.convert(str(i)+'.jpg', layout_fun=layout_fun))

        self.status.showMessage('Czyszczenie...')
        for i in range(4):
            os.remove(str(i)+'.jpg')

        self.status.showMessage('Zrobione.')
        self.finished.emit()


class LoadingButton(QPushButton):
    @QtCore.Slot()
    def start(self):
        if hasattr(self, "_movie"):
            self._movie.start()

    @QtCore.Slot()
    def stop(self):
        if hasattr(self, "_movie"):
            self._movie.stop()
            self.setIcon(QIcon())

    def setGif(self, filename):
        if not hasattr(self, "_movie"):
            self._movie = QMovie(self)
            self._movie.setFileName(filename)
            self._movie.frameChanged.connect(self.on_frameChanged)
            if self._movie.loopCount() != -1:
                self._movie.finished.connect(self.start)
        # self.stop()

    @QtCore.Slot(int)
    def on_frameChanged(self, frameNumber):
        self.setIcon(QIcon(self._movie.currentPixmap()))


class FileMonitor(QtCore.QObject):
    image_signal = QtCore.Signal(PpmImagePlugin.PpmImageFile)

    def __init__(self, path):
        super().__init__()
        self.path = path

    @QtCore.Slot()
    def monitor_images(self):
        config = configparser.ConfigParser()
        try:
            config.read('settings.ini')
            dpi = config['DEFAULT']['DPI']
        except KeyError:
            dpi = 300
        img = convert_from_path(self.path, dpi=dpi, poppler_path=r'.\poppler\Library\bin')
        img = img[0]
        self.image_signal.emit(img)


class DragDropLabel(QLabel):
    item_dropped = False
    image = None
    image_ready = False

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        lines = []
        for url in event.mimeData().urls():
            lines.append(url)
        if len(lines) > 1:
            self.parent().multiDropEvent(lines)
            return
        # if self.item_dropped:
        #     if repleceFileDialog():
        #         return

        self.setText('Ładowanie ' + lines[0].fileName() + '...')
        self.item_dropped = True

        self.file_monitor = FileMonitor(lines[0].toLocalFile())
        thread = QtCore.QThread(parent=self)
        self.file_monitor.image_signal.connect(self.image_callback)
        self.file_monitor.moveToThread(thread)
        thread.started.connect(self.file_monitor.monitor_images)
        thread.start()

    @ QtCore.Slot(PpmImagePlugin.PpmImageFile)
    def image_callback(self, img):
        self.image = img
        self.image_ready = True
        basewidth = 400
        wpercent = (basewidth/float(img.size[0]))
        hsize = int((float(img.size[1])*float(wpercent)))
        img = img.resize((basewidth, hsize), Image.ANTIALIAS)
        im2 = img.convert("RGBA")
        data = im2.tobytes("raw", "BGRA")

        qim = QImage(data, img.width, img.height, QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(qim)
        self.setPixmap(pixmap)


class MainWidget(QWidget):
    def __init__(self, statusBarPointer):
        super().__init__()
        self.statusBarPointer = statusBarPointer
        self.label_left = DragDropLabel('przeciągnij i upuść\nprzednią stronę')
        self.label_left.setStyleSheet("border: 1px solid black;")
        self.label_left.setAlignment(Qt.AlignCenter)
        self.label_left.setMinimumHeight(50)

        self.label_right = DragDropLabel('przeciągnij i upuść\ntylną stronę')
        self.label_right.setStyleSheet("border: 1px solid black;")
        self.label_right.setAlignment(Qt.AlignCenter)
        self.label_right.setMinimumHeight(50)

        self.button = LoadingButton('Generuj')
        self.button.setGif("loading.gif")
        self.button.setMinimumHeight(50)
        self.button.clicked.connect(self.prepareWork)

        layout = QGridLayout()
        layout.addWidget(self.label_left, 0, 0)
        layout.addWidget(self.label_right, 0, 1)
        layout.addWidget(self.button, 1, 0, 1, 2)

        self.setLayout(layout)

    def prepareWork(self):
        if not self.label_left.item_dropped or not self.label_right.item_dropped:
            self.statusBarPointer.showMessage(
                'Najpierw przeciągnij i upuść pdfy')
            return
        self.sender().start()
        self.sender().setText("Pracuję...")
        self.button.setEnabled(False)

        out_path = self.saveFileDialog()
        if out_path == None:
            self.buttonActivate()
            return

        self.startWrok(out_path)

    def startWrok(self, outputPath):
        if not self.label_left.image_ready or not self.label_right.image_ready:
            QtCore.QTimer.singleShot(100, lambda: self.startWrok(outputPath))
            return
        self.work_thread = Worker(
            self.label_left.image, self.label_right.image, outputPath, self.statusBarPointer)
        thread = QtCore.QThread(parent=self)
        self.work_thread.finished.connect(self.buttonActivate)
        self.work_thread.moveToThread(thread)
        thread.started.connect(self.work_thread.work)

        thread.start()

    def buttonActivate(self):
        self.button.setEnabled(True)
        self.button.setText("Generuj")
        self.button.stop()

    def multiDropEvent(self, paths: list):
        # if self.label_left.item_dropped or self.label_right.item_dropped:
        #     if repleceFileDialog():
        #         return
        self.file_monitor = FileMonitor(paths[0].toLocalFile())
        thread = QtCore.QThread(parent=self)
        self.file_monitor.image_signal.connect(self.label_left.image_callback)
        self.file_monitor.moveToThread(thread)
        thread.started.connect(self.file_monitor.monitor_images)
        thread.start()
        self.label_left.setText('Ładowanie ' + paths[0].fileName() + '...')
        self.label_left.item_dropped = True

        self.file_monitor2 = FileMonitor(paths[1].toLocalFile())
        thread = QtCore.QThread(parent=self)
        self.file_monitor2.image_signal.connect(
            self.label_right.image_callback)
        self.file_monitor2.moveToThread(thread)
        thread.started.connect(self.file_monitor2.monitor_images)
        thread.start()
        self.label_right.setText('Ładowanie ' + paths[1].fileName() + '...')
        self.label_right.item_dropped = True

    def saveFileDialog(self):
        default_dir = os.path.expanduser("~/Desktop")
        default_filename = os.path.join(default_dir, "dokument.pdf")
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(
            self, "Zapisz pliki", default_filename, "PDF", options=options)
        if fileName:
            try:
                fileName, _ = fileName.split('.')
            except ValueError:
                pass
            for i in range(4):
                if os.path.isfile(fileName + str(i) + '.pdf'):
                    self.statusBarPointer.showMessage(
                        'Przerwano! Plik "' + os.path.basename(fileName) + str(i) + '.pdf" już istnieje.')
                    return None
            return fileName
        else:
            return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDFmerger")

        statusBar = QStatusBar()
        self.setStatusBar(statusBar)

        mainWidget = MainWidget(statusBar)
        self.setCentralWidget(mainWidget)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(700, 520)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
