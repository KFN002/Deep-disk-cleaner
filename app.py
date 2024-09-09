import sys
import os
import shutil
import random
import string
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QLineEdit, QHBoxLayout, QProgressBar, QTextEdit
)
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker, QWaitCondition


def generate_random_text(size_in_mb):
    size_in_bytes = size_in_mb * 1024 * 1024
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size_in_bytes))


def check_disk_space(drive):
    total, used, free = shutil.disk_usage(drive[:-1])
    return total, used, free


def delete_directory(directory):
    if os.path.exists(directory):
        shutil.rmtree(directory)


class DiskFillerWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    completed = pyqtSignal()
    stopped = pyqtSignal()
    paused = pyqtSignal()

    def __init__(self, folder_path, target_size_mb, chunk_size_mb, drive_letter):
        super().__init__()
        self.folder_path = folder_path
        self.target_size_mb = target_size_mb
        self.chunk_size_mb = chunk_size_mb
        self.drive_letter = drive_letter
        self.stop_flag = False
        self.pause_flag = False
        self.mutex = QMutex()
        self.condition = QWaitCondition()

    def run(self):
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)

        data = generate_random_text(self.chunk_size_mb)
        total_written = 0
        file_count = 0

        while total_written < self.target_size_mb:
            with QMutexLocker(self.mutex):
                if self.stop_flag:
                    self.log.emit("Stopping process and deleting folder...")
                    delete_directory(self.folder_path)
                    self.stopped.emit()
                    return

                while self.pause_flag:
                    self.log.emit("Paused.")
                    self.condition.wait(self.mutex)

            file_name = os.path.join(self.folder_path, f'filler_{file_count}.txt')
            try:
                with open(file_name, 'w') as file:
                    file.write(data)
                total_written += self.chunk_size_mb
                file_count += 1
                self.log.emit(f'Created {file_name} of size {self.chunk_size_mb} MB. Total written: {total_written} MB.')
                self.progress.emit(min(total_written, self.target_size_mb))

                if check_disk_space(self.drive_letter + ':')[2] < 10 * 1024 * 1024:
                    self.log.emit("Disk space is low. Deleting filler folder...")
                    delete_directory(self.folder_path)
                    break
            except OSError as e:
                self.log.emit(f"Error writing file {file_name}: {e}")
                break

        self.log.emit("Process completed.")
        delete_directory(self.folder_path)
        self.completed.emit()

    def stop(self):
        with QMutexLocker(self.mutex):
            self.stop_flag = True

    def pause(self):
        with QMutexLocker(self.mutex):
            self.pause_flag = True

    def resume(self):
        with QMutexLocker(self.mutex):
            self.pause_flag = False
            self.condition.wakeAll()


class DiskFillerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        self.label = QLabel("Choose the disk to fill:")
        layout.addWidget(self.label)

        self.choose_button = QPushButton("Choose Disk")
        self.choose_button.clicked.connect(self.choose_disk)
        layout.addWidget(self.choose_button)

        self.space_info = QLabel("Available space: N/A")
        layout.addWidget(self.space_info)

        size_input_layout = QHBoxLayout()
        self.size_label = QLabel("Enter space to fill (MB):")
        size_input_layout.addWidget(self.size_label)

        self.size_input = QLineEdit()
        self.size_input.setEnabled(False)
        size_input_layout.addWidget(self.size_input)
        layout.addLayout(size_input_layout)

        chunk_size_input_layout = QHBoxLayout()
        self.chunk_size_label = QLabel("Enter chunk file size (MB):")
        chunk_size_input_layout.addWidget(self.chunk_size_label)

        self.chunk_size_input = QLineEdit()
        self.chunk_size_input.setEnabled(False)
        chunk_size_input_layout.addWidget(self.chunk_size_input)
        layout.addLayout(chunk_size_input_layout)

        self.fill_button = QPushButton("Start Deep Clean")
        self.fill_button.clicked.connect(self.start_deep_clean)
        layout.addWidget(self.fill_button)
        self.fill_button.setEnabled(False)

        self.stop_button = QPushButton("All-Stop")
        self.stop_button.clicked.connect(self.stop_process)
        layout.addWidget(self.stop_button)
        self.stop_button.setEnabled(False)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_process)
        layout.addWidget(self.pause_button)
        self.pause_button.setEnabled(False)

        self.continue_button = QPushButton("Continue")
        self.continue_button.clicked.connect(self.resume_process)
        layout.addWidget(self.continue_button)
        self.continue_button.setEnabled(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        self.setLayout(layout)
        self.setWindowTitle('Disk Filler')
        self.resize(900, 600)

        self.selected_drive = None
        self.worker = None

    def choose_disk(self):
        self.selected_drive = QFileDialog.getExistingDirectory(self, "Select Disk to Fill", "/")
        if self.selected_drive:
            drive_letter = os.path.splitdrive(self.selected_drive)[0]
            total, used, free = check_disk_space(drive_letter + ':')

            self.space_info.setText(f"Available space: {free // (1024 * 1024)} MB")
            self.label.setText(f"Selected Disk: {drive_letter}")

            self.size_input.setEnabled(True)
            self.chunk_size_input.setEnabled(True)
            self.fill_button.setEnabled(True)

    def start_deep_clean(self):
        if self.selected_drive:
            try:
                drive_letter = os.path.splitdrive(self.selected_drive)[0]
                folder_path = os.path.join(self.selected_drive, "filler")

                target_size_mb = int(self.size_input.text())
                chunk_size_mb = int(self.chunk_size_input.text())

                if target_size_mb <= 0 or chunk_size_mb <= 0:
                    raise ValueError("The space to fill and chunk size must be greater than zero.")

                self.progress_bar.setMaximum(target_size_mb)
                self.progress_bar.setValue(0)
                self.log_output.clear()

                self.worker = DiskFillerWorker(folder_path, target_size_mb, chunk_size_mb, drive_letter)
                self.worker.progress.connect(self.update_progress)
                self.worker.log.connect(self.add_log)
                self.worker.completed.connect(self.clean_up)
                self.worker.stopped.connect(self.stop_cleanup)
                self.worker.paused.connect(self.update_pause_status)

                self.worker.start()

                self.stop_button.setEnabled(True)
                self.pause_button.setEnabled(True)
                self.continue_button.setEnabled(False)
                self.fill_button.setEnabled(False)

            except ValueError:
                QMessageBox.warning(self, "Error", "Invalid input. Please enter valid numbers for the space to fill and chunk size.")
        else:
            QMessageBox.warning(self, "Error", "No disk selected.")

    def stop_process(self):
        if self.worker:
            self.worker.stop()

    def pause_process(self):
        if self.worker:
            self.worker.pause()
            self.pause_button.setEnabled(False)
            self.continue_button.setEnabled(True)

    def resume_process(self):
        if self.worker:
            self.worker.resume()
            self.pause_button.setEnabled(True)
            self.continue_button.setEnabled(False)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def add_log(self, message):
        self.log_output.append(message)

    def clean_up(self):
        QMessageBox.information(self, "Completed", "Disk fill process completed and files have been deleted.")
        self.reset_buttons()

    def stop_cleanup(self):
        QMessageBox.information(self, "Stopped", "Disk fill process was stopped and files have been deleted.")
        self.reset_buttons()

    def update_pause_status(self):
        self.pause_button.setEnabled(False)
        self.continue_button.setEnabled(True)

    def reset_buttons(self):
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.fill_button.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DiskFillerApp()
    window.show()
    sys.exit(app.exec_())
