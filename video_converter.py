import sys
import os
import subprocess
import shutil
import re
import json
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QFileDialog, QComboBox, QProgressBar, 
                            QMessageBox, QGroupBox, QRadioButton, QListWidget, QCheckBox,
                            QMenu, QAction, QTextEdit, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QUrl
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QFont

class FFmpegConverter(QThread):
    progress_update = pyqtSignal(int, float)  # Progress percentage and ETA in seconds
    conversion_complete = pyqtSignal(str)
    conversion_error = pyqtSignal(str)
    
    def __init__(self, input_file, output_file, preset="medium", format="mp4", use_nvenc=False):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.preset = preset
        self.format = format
        self.duration = 0
        self.start_time = 0
        self.use_nvenc = use_nvenc
        self.full_output = []  # Store the full output for debugging
        
    def run(self):
        try:
            # Clear previous output
            self.full_output = []
            
            # Check if FFmpeg is installed
            if not self._is_ffmpeg_installed():
                self.conversion_error.emit("FFmpeg is not installed. Please install FFmpeg first.")
                return
            
            # Get video duration
            self.duration = self._get_video_duration()
            if self.duration <= 0:
                self.conversion_error.emit("Could not determine video duration.")
                return
                
            # Check NVENC availability if requested
            if self.use_nvenc and not self._is_nvenc_available():
                self.conversion_error.emit("NVENC hardware encoding is not available. Using software encoding instead.")
                self.use_nvenc = False
                
            # Build FFmpeg command
            cmd = [
                "ffmpeg",
                "-i", self.input_file,
            ]
            
            # Add encoding parameters based on whether NVENC is used
            if self.use_nvenc:
                cmd.extend([
                    "-c:v", "h264_nvenc",
                    "-preset", self._get_nvenc_preset(self.preset),
                    "-b:v", "0",  # Use variable bitrate
                    "-c:a", "aac",
                ])
            else:
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", self.preset,
                    "-c:a", "aac",
                ])
            
            # Add output file (with overwrite flag)
            cmd.extend([
                "-y",  # Overwrite output file if it exists
                self.output_file
            ])
            
            # Print command for debugging
            print(f"Running FFmpeg command: {' '.join(cmd)}")
            
            # Record the start time
            self.start_time = time.time()
            
            # Run the FFmpeg command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Collect full output for error analysis
            
            # Monitor the process
            for line in process.stdout:
                # Save output for error analysis
                self.full_output.append(line)
                
                if "time=" in line:
                    try:
                        # Extract time information to estimate progress
                        time_str = line.split("time=")[1].split()[0]
                        h, m, s = time_str.split(':')
                        current_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                        
                        # Calculate progress percentage
                        progress = min(int(current_seconds / self.duration * 100), 99)
                        
                        # Calculate ETA
                        elapsed_time = time.time() - self.start_time
                        if progress > 0:
                            total_estimated_time = elapsed_time * 100 / progress
                            eta = total_estimated_time - elapsed_time
                        else:
                            eta = 0
                        
                        self.progress_update.emit(progress, eta)
                    except (IndexError, ValueError, ZeroDivisionError):
                        pass
            
            # Wait for the process to complete
            process.wait()
            
            # Check if conversion was successful
            if process.returncode == 0:
                self.progress_update.emit(100, 0)  # 100% progress, 0 seconds remaining
                self.conversion_complete.emit(self.output_file)
            else:
                # Look for NVENC-specific errors in the output
                output_text = "".join(self.full_output)
                if self.use_nvenc and any(error in output_text for error in [
                    "NVENC", "GPU", "Error initializing", "CUDA", "can't initialize"
                ]):
                    error_msg = "NVIDIA encoder error. Try disabling hardware acceleration or update your GPU drivers."
                    print(f"NVENC error detected in output: {output_text}")
                    self.conversion_error.emit(error_msg)
                else:
                    self.conversion_error.emit(f"Conversion failed with error code {process.returncode}")
                
        except Exception as e:
            self.conversion_error.emit(f"Error during conversion: {str(e)}")
    
    def _is_nvenc_available(self):
        """Check if NVENC hardware encoding is available"""
        try:
            print("Checking NVENC availability...")
            
            # Method 1: Check if h264_nvenc encoder is listed
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-encoders"
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            has_nvenc_listed = "h264_nvenc" in result.stdout
            
            print(f"NVENC in encoders list: {has_nvenc_listed}")
            
            if not has_nvenc_listed:
                print("NVENC encoder not found in FFmpeg encoders list")
                return False
            
            # Method 2: Print GPU information for debugging
            try:
                nvidia_info_cmd = ["nvidia-smi"]
                nvidia_result = subprocess.run(
                    nvidia_info_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )
                print("NVIDIA GPU info:")
                print(nvidia_result.stdout)
            except Exception as e:
                print(f"nvidia-smi not available: {str(e)}")
                
            # Method 3: Try a simple test encode with very strict parameters
            # This is designed to succeed even on older GPUs
            test_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f", "lavfi",
                "-i", "color=c=black:s=32x32:r=1:d=1",
                "-c:v", "h264_nvenc",
                "-preset", "p1", # fastest preset
                "-profile:v", "baseline",
                "-b:v", "250k",
                "-f", "null",
                "-"
            ]
            
            print(f"Running NVENC test: {' '.join(test_cmd)}")
            
            test_result = subprocess.run(
                test_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                timeout=10
            )
            
            test_success = test_result.returncode == 0
            print(f"NVENC test result: {'Success' if test_success else 'Failed'}")
            if not test_success:
                print("NVENC test output:")
                print(test_result.stderr)
                
            return test_success
            
        except Exception as e:
            print(f"Error checking NVENC availability: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
            
    def _get_nvenc_preset(self, standard_preset):
        """Map standard x264 presets to NVENC equivalents"""
        # NVENC has different preset names
        nvenc_presets = {
            "veryfast": "p1",   # Fastest/lowest quality
            "medium": "p4",     # Balanced
            "veryslow": "p7"    # Slowest/highest quality
        }
        return nvenc_presets.get(standard_preset, "p4")  # Default to p4 (medium)
    
    def _get_video_duration(self):
        """Get the duration of the input video in seconds."""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                self.input_file
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            else:
                # Fallback method if ffprobe fails
                cmd = [
                    "ffmpeg",
                    "-i", self.input_file
                ]
                
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                
                # Parse the output to find duration
                duration_pattern = r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)"
                match = re.search(duration_pattern, result.stderr)
                
                if match:
                    h, m, s = match.groups()
                    return int(h) * 3600 + int(m) * 60 + float(s)
                    
            return 0
        except Exception:
            return 0
    
    def _is_ffmpeg_installed(self):
        """Check if FFmpeg is installed on the system."""
        try:
            subprocess.run(["ffmpeg", "-version"], 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE, 
                           check=False)
            return True
        except FileNotFoundError:
            return False

class DragDropListWidget(QListWidget):
    files_dropped = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            file_paths = []
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    # Check if it's a video file by extension
                    ext = os.path.splitext(path)[1].lower()
                    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv']:
                        file_paths.append(path)
            
            if file_paths:
                self.files_dropped.emit(file_paths)
            
            event.acceptProposedAction()
    
    def contextMenuEvent(self, event):
        context_menu = QMenu(self)
        remove_action = QAction("Remove selected", self)
        remove_action.triggered.connect(self.remove_selected_items)
        context_menu.addAction(remove_action)
        
        clear_action = QAction("Clear all", self)
        clear_action.triggered.connect(self.clear)
        context_menu.addAction(clear_action)
        
        context_menu.exec_(event.globalPos())
    
    def remove_selected_items(self):
        selected_items = self.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            row = self.row(item)
            self.takeItem(row)

class VideoInfoExtractor:
    @staticmethod
    def get_video_info(file_path):
        """Get information about the video file using ffprobe"""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                return None
                
            info = json.loads(result.stdout)
            
            # Extract relevant information
            video_info = {
                "filename": os.path.basename(file_path),
                "filesize": "",
                "duration": "",
                "resolution": "",
                "video_codec": "",
                "audio_codec": "",
                "bitrate": ""
            }
            
            # Format information
            if "format" in info:
                format_info = info["format"]
                
                # File size
                if "size" in format_info:
                    size_bytes = int(format_info["size"])
                    if size_bytes > 1024*1024*1024:  # GB
                        video_info["filesize"] = f"{size_bytes/(1024*1024*1024):.2f} GB"
                    else:  # MB
                        video_info["filesize"] = f"{size_bytes/(1024*1024):.2f} MB"
                
                # Duration
                if "duration" in format_info:
                    seconds = float(format_info["duration"])
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = seconds % 60
                    video_info["duration"] = f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
                
                # Bitrate
                if "bit_rate" in format_info:
                    bitrate = int(format_info["bit_rate"]) / 1000
                    video_info["bitrate"] = f"{bitrate:.0f} Kbps"
            
            # Stream information
            if "streams" in info:
                for stream in info["streams"]:
                    # Video stream
                    if stream.get("codec_type") == "video":
                        # Resolution
                        if "width" in stream and "height" in stream:
                            video_info["resolution"] = f"{stream['width']}x{stream['height']}"
                        
                        # Video codec
                        if "codec_name" in stream:
                            video_info["video_codec"] = stream["codec_name"]
                    
                    # Audio stream
                    elif stream.get("codec_type") == "audio":
                        # Audio codec
                        if "codec_name" in stream:
                            video_info["audio_codec"] = stream["codec_name"]
            
            return video_info
        except Exception as e:
            print(f"Error getting video info: {str(e)}")
            return None

class VideoConverterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.converter_threads = []
        self.input_files = []
        self.processing_all = False
        self.last_conversion_output = ""
        
        # Check for FFmpeg availability at startup
        self.check_ffmpeg_availability()
        
        # Check for NVENC availability
        self.check_nvenc_availability()
        
    def check_ffmpeg_availability(self):
        """Check if FFmpeg is installed and show warning if not"""
        if not self._is_ffmpeg_installed():
            self.show_ffmpeg_not_found_message()
            
    def _is_ffmpeg_installed(self):
        """Check if FFmpeg is installed on the system."""
        try:
            subprocess.run(["ffmpeg", "-version"], 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE, 
                           check=False)
            return True
        except FileNotFoundError:
            return False
            
    def show_ffmpeg_not_found_message(self):
        """Show a detailed message about FFmpeg installation"""
        ffmpeg_url = "https://ffmpeg.org/download.html"
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("FFmpeg Not Found")
        msg.setText("FFmpeg is required but not found on your system")
        
        detailed_text = (
            "This application requires FFmpeg to convert video files.\n\n"
            "Please install FFmpeg and ensure it's in your system PATH:\n\n"
            "Windows:\n"
            "1. Download FFmpeg from https://ffmpeg.org/download.html\n"
            "2. Extract the files to a folder (e.g., C:\\ffmpeg)\n"
            "3. Add the bin folder to your PATH environment variable\n\n"
            "macOS:\n"
            "Install via Homebrew: brew install ffmpeg\n\n"
            "Linux:\n"
            "Ubuntu/Debian: sudo apt install ffmpeg\n"
            "Fedora: sudo dnf install ffmpeg\n"
        )
        
        msg.setDetailedText(detailed_text)
        
        # Add buttons
        msg.setStandardButtons(QMessageBox.Ok)
        download_button = msg.addButton("Download FFmpeg", QMessageBox.ActionRole)
        
        # Show the message box
        result = msg.exec_()
        
        # Handle button clicks
        if msg.clickedButton() == download_button:
            import webbrowser
            webbrowser.open(ffmpeg_url)
    
    def check_nvenc_availability(self):
        """Check if NVENC is available and update the UI"""
        try:
            print("\n--- NVENC Detection Started ---")
            # Create a temporary converter to check NVENC
            temp_converter = FFmpegConverter("", "", use_nvenc=True)
            has_nvenc = temp_converter._is_nvenc_available()
            
            # Update checkbox text with availability status
            if has_nvenc:
                self.nvenc_checkbox.setText("Use NVIDIA NVENC hardware acceleration ✓")
                self.nvenc_checkbox.setEnabled(True)
                self.nvenc_checkbox.setChecked(True)  # Enable by default if available
                print("NVENC detected and enabled")
            else:
                self.nvenc_checkbox.setText("Use NVIDIA NVENC hardware acceleration ✗")
                self.nvenc_checkbox.setToolTip("NVIDIA GPU encoder not detected or not working.\nEnsure your GPU supports NVENC and drivers are up to date.")
                # Keep it enabled so user can try anyway
                self.nvenc_checkbox.setEnabled(True)
                self.nvenc_checkbox.setChecked(False)
                print("NVENC not detected, checkbox disabled")
                
            print("--- NVENC Detection Completed ---\n")
                
        except Exception as e:
            print(f"Error checking NVENC: {str(e)}")
            import traceback
            traceback.print_exc()
            self.nvenc_checkbox.setText("Use NVIDIA NVENC hardware acceleration (status unknown)")
            self.nvenc_checkbox.setEnabled(True)
            self.nvenc_checkbox.setChecked(False)
            
    def init_ui(self):
        self.setWindowTitle("Video Converter")
        self.setGeometry(100, 100, 800, 600)
        
        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top horizontal layout
        top_layout = QHBoxLayout()
        
        # File selection section
        file_group = QGroupBox("File Selection")
        file_layout = QVBoxLayout()
        
        file_btn_layout = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_btn = QPushButton("Select Video File(s)")
        self.file_btn.clicked.connect(self.select_input_files)
        file_btn_layout.addWidget(self.file_label)
        file_btn_layout.addWidget(self.file_btn)
        
        # Use custom drag-drop list widget
        self.file_list = DragDropListWidget()
        self.file_list.files_dropped.connect(self.add_dropped_files)
        self.file_list.itemSelectionChanged.connect(self.update_remove_button)
        self.file_list.itemClicked.connect(self.show_video_info)
        
        # Remove button
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected_files)
        self.remove_btn.setEnabled(False)
        
        # Clear button
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_all_files)
        self.clear_btn.setEnabled(False)
        
        # File buttons layout
        file_actions_layout = QHBoxLayout()
        file_actions_layout.addWidget(self.remove_btn)
        file_actions_layout.addWidget(self.clear_btn)
        
        # Drop zone label
        drop_label = QLabel("Drag and drop video files here")
        drop_label.setAlignment(Qt.AlignCenter)
        
        file_layout.addLayout(file_btn_layout)
        file_layout.addWidget(drop_label)
        file_layout.addWidget(self.file_list)
        file_layout.addLayout(file_actions_layout)
        file_group.setLayout(file_layout)
        
        # Video info section
        info_group = QGroupBox("Video Information")
        info_layout = QVBoxLayout()
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMinimumHeight(100)
        info_layout.addWidget(self.info_text)
        
        info_group.setLayout(info_layout)
        
        # Add file selection and info to top layout
        top_layout.addWidget(file_group, 2)
        top_layout.addWidget(info_group, 1)
        
        # Add top layout to main layout
        main_layout.addLayout(top_layout)
        
        # Output directory selection
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()
        
        output_dir_layout = QHBoxLayout()
        self.output_dir_label = QLabel("Default: Same as input file")
        self.output_dir_btn = QPushButton("Select Output Folder")
        self.output_dir_btn.clicked.connect(self.select_output_dir)
        output_dir_layout.addWidget(self.output_dir_label)
        output_dir_layout.addWidget(self.output_dir_btn)
        
        # Format selection
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Output Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp4", "mkv", "avi", "mov", "webm"])
        format_layout.addWidget(self.format_combo)
        
        # Quality preset selection
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Quality Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Fast (Low Quality)", "Medium Quality", "Slow (High Quality)"])
        self.preset_combo.setCurrentText("Medium Quality")
        preset_layout.addWidget(self.preset_combo)
        
        # Batch conversion checkbox
        batch_layout = QHBoxLayout()
        self.batch_checkbox = QCheckBox("Process all files sequentially")
        self.batch_checkbox.setChecked(True)
        batch_layout.addWidget(self.batch_checkbox)
        
        # NVENC hardware acceleration checkbox
        nvenc_layout = QHBoxLayout()
        self.nvenc_checkbox = QCheckBox("Use NVIDIA NVENC hardware acceleration (checking...)")
        self.nvenc_checkbox.setChecked(False)
        self.nvenc_checkbox.setToolTip("Uses NVIDIA GPU for faster encoding. Requires compatible NVIDIA graphics card.")
        
        # Add test NVENC button
        self.test_nvenc_btn = QPushButton("Test NVENC")
        self.test_nvenc_btn.clicked.connect(self.test_nvenc_manually)
        self.test_nvenc_btn.setToolTip("Test if NVIDIA hardware encoding is working properly")
        
        # Add view logs button
        self.view_logs_btn = QPushButton("View Logs")
        self.view_logs_btn.clicked.connect(self.show_conversion_logs)
        self.view_logs_btn.setEnabled(False)
        
        nvenc_layout.addWidget(self.nvenc_checkbox)
        nvenc_layout.addWidget(self.test_nvenc_btn)
        nvenc_layout.addWidget(self.view_logs_btn)
        
        output_layout.addLayout(output_dir_layout)
        output_layout.addLayout(format_layout)
        output_layout.addLayout(preset_layout)
        output_layout.addLayout(batch_layout)
        output_layout.addLayout(nvenc_layout)
        output_group.setLayout(output_layout)
        
        # Conversion controls
        controls_layout = QHBoxLayout()
        self.convert_btn = QPushButton("Start Conversion")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.convert_btn.setFixedHeight(50)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setFixedHeight(50)
        self.cancel_btn.setEnabled(False)
        
        controls_layout.addWidget(self.convert_btn)
        controls_layout.addWidget(self.cancel_btn)
        
        # Progress bar
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        # Current file progress and ETA
        progress_info_layout = QHBoxLayout()
        self.current_file_label = QLabel("")
        self.eta_label = QLabel("")
        progress_info_layout.addWidget(self.current_file_label)
        progress_info_layout.addWidget(self.eta_label, 0, Qt.AlignRight)
        progress_layout.addLayout(progress_info_layout)
        
        # Add all components to main layout
        main_layout.addWidget(output_group)
        main_layout.addLayout(controls_layout)
        main_layout.addLayout(progress_layout)
        
        # Initialize variables
        self.output_directory = None
        
    def select_input_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv);;All Files (*)"
        )
        
        if files:
            self.input_files = files
            self.file_list.clear()
            for file in files:
                self.file_list.addItem(os.path.basename(file))
            self.file_label.setText(f"{len(files)} file(s) selected")
            self.update_remove_button()
            
    def select_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            ""
        )
        
        if directory:
            self.output_directory = directory
            self.output_dir_label.setText(f"Output: {directory}")
    
    def start_conversion(self):
        if not self.input_files:
            QMessageBox.warning(self, "Warning", "Please select at least one input file.")
            return
            
        # Check if FFmpeg is installed
        if not self._is_ffmpeg_installed():
            self.show_ffmpeg_not_found_message()
            return
            
        # Get selected options
        selected_preset_display = self.preset_combo.currentText()
        # Map the user-friendly preset names to FFmpeg preset values
        preset_mapping = {
            "Fast (Low Quality)": "veryfast",
            "Medium Quality": "medium",
            "Slow (High Quality)": "veryslow"
        }
        selected_preset = preset_mapping[selected_preset_display]
        selected_format = self.format_combo.currentText()
        self.processing_all = self.batch_checkbox.isChecked()
        use_nvenc = self.nvenc_checkbox.isChecked()
        
        # Warn about NVENC if it wasn't detected but is being used
        if use_nvenc and "✗" in self.nvenc_checkbox.text():
            response = QMessageBox.question(
                self,
                "NVENC Not Detected",
                "NVIDIA hardware encoding was not detected but is enabled.\n\n"
                "Conversion might fail. Continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if response == QMessageBox.No:
                return
                
        # Print debug information
        print(f"\n--- Starting Conversion ---")
        print(f"Preset: {selected_preset}")
        print(f"Format: {selected_format}")
        print(f"Using NVENC: {use_nvenc}")
        
        # Update UI
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.file_btn.setEnabled(False)
        self.output_dir_btn.setEnabled(False)
        self.format_combo.setEnabled(False)
        self.preset_combo.setEnabled(False)
        self.batch_checkbox.setEnabled(False)
        self.nvenc_checkbox.setEnabled(False)
        
        # Clear any existing converter threads
        self.converter_threads = []
        
        # Create converter threads for all files
        for input_file in self.input_files:
            # Determine output file path
            if self.output_directory:
                output_filename = os.path.splitext(os.path.basename(input_file))[0] + f".{selected_format}"
                output_file = os.path.join(self.output_directory, output_filename)
            else:
                output_file = os.path.splitext(input_file)[0] + f".{selected_format}"
            
            # Create converter thread
            converter = FFmpegConverter(
                input_file=input_file,
                output_file=output_file,
                preset=selected_preset,
                format=selected_format,
                use_nvenc=use_nvenc
            )
            
            # Connect signals
            converter.progress_update.connect(self.update_progress)
            converter.conversion_complete.connect(self.conversion_completed)
            converter.conversion_error.connect(self.conversion_failed)
            
            # Add to thread list
            self.converter_threads.append(converter)
        
        # Start the first conversion
        if self.converter_threads:
            current_thread = self.converter_threads[0]
            current_file = os.path.basename(current_thread.input_file)
            self.current_file_label.setText(f"Processing: {current_file} (1/{len(self.converter_threads)})")
            self.status_label.setText("Converting...")
            self.eta_label.setText("Calculating...")
            self.progress_bar.setValue(0)
            current_thread.start()
    
    def cancel_conversion(self):
        # Terminate all running conversions
        for thread in self.converter_threads:
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        
        self.converter_threads = []
        self.reset_ui()
        self.status_label.setText("Conversion cancelled")
        self.progress_bar.setValue(0)
        self.current_file_label.setText("")
        self.eta_label.setText("")
    
    def reset_ui(self):
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.file_btn.setEnabled(True)
        self.output_dir_btn.setEnabled(True)
        self.format_combo.setEnabled(True)
        self.preset_combo.setEnabled(True)
        self.batch_checkbox.setEnabled(True)
        self.nvenc_checkbox.setEnabled(True)
    
    def update_progress(self, value, eta_seconds):
        """Update progress bar and ETA display"""
        self.progress_bar.setValue(value)
        
        # Format the ETA
        if eta_seconds > 0:
            if eta_seconds < 60:
                eta_text = f"ETA: {int(eta_seconds)}s"
            elif eta_seconds < 3600:
                minutes = int(eta_seconds // 60)
                seconds = int(eta_seconds % 60)
                eta_text = f"ETA: {minutes}m {seconds}s"
            else:
                hours = int(eta_seconds // 3600)
                minutes = int((eta_seconds % 3600) // 60)
                eta_text = f"ETA: {hours}h {minutes}m"
            
            self.eta_label.setText(eta_text)
        else:
            self.eta_label.setText("Almost done...")
    
    def conversion_completed(self, output_file):
        self.progress_bar.setValue(100)
        self.eta_label.setText("")
        
        # Remove completed thread
        if self.converter_threads:
            completed_thread = self.converter_threads.pop(0)
            completed_file = os.path.basename(completed_thread.input_file)
            
            # Update status
            self.status_label.setText(f"Completed: {completed_file}")
            
            # If batch processing and more files to process
            if self.processing_all and self.converter_threads:
                next_thread = self.converter_threads[0]
                next_file = os.path.basename(next_thread.input_file)
                self.current_file_label.setText(
                    f"Processing: {next_file} ({len(self.input_files) - len(self.converter_threads)}/{len(self.input_files)})"
                )
                self.progress_bar.setValue(0)
                self.eta_label.setText("Calculating...")
                next_thread.start()
            else:
                # All conversions completed or not batch processing
                if not self.converter_threads or not self.processing_all:
                    self.reset_ui()
                    if len(self.input_files) > 1:
                        QMessageBox.information(
                            self, 
                            "Success", 
                            f"All conversions completed successfully!"
                        )
                    else:
                        QMessageBox.information(
                            self, 
                            "Success", 
                            f"Conversion complete!\nOutput file: {output_file}"
                        )
                    self.current_file_label.setText("")
                    self.status_label.setText("Ready")
    
    def conversion_failed(self, error_message):
        # Remove failed thread
        if self.converter_threads:
            failed_thread = self.converter_threads.pop(0)
            failed_file = os.path.basename(failed_thread.input_file)
            
            # Save conversion output for logs
            if hasattr(failed_thread, 'full_output'):
                self.last_conversion_output = "".join(failed_thread.full_output)
                self.view_logs_btn.setEnabled(True)
            
            # Update UI
            self.status_label.setText(f"Error: {error_message}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"Conversion failed for {failed_file}: {error_message}"
            )
            
            # If batch processing and more files to process
            if self.processing_all and self.converter_threads:
                next_thread = self.converter_threads[0]
                next_file = os.path.basename(next_thread.input_file)
                self.current_file_label.setText(
                    f"Processing: {next_file} ({len(self.input_files) - len(self.converter_threads)}/{len(self.input_files)})"
                )
                self.progress_bar.setValue(0)
                self.eta_label.setText("Calculating...")
                next_thread.start()
            else:
                # All conversions completed or not batch processing
                self.reset_ui()
                self.current_file_label.setText("")
                self.eta_label.setText("")

    def update_remove_button(self):
        self.remove_btn.setEnabled(len(self.file_list.selectedItems()) > 0)
        self.clear_btn.setEnabled(self.file_list.count() > 0)
        
    def remove_selected_files(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
            
        selected_names = [item.text() for item in selected_items]
        
        # Remove from input_files list
        self.input_files = [
            f for f in self.input_files 
            if os.path.basename(f) not in selected_names
        ]
        
        # Update UI
        self.file_list.remove_selected_items()
        self.file_label.setText(f"{len(self.input_files)} file(s) selected")
        self.update_remove_button()
        
    def clear_all_files(self):
        self.input_files = []
        self.file_list.clear()
        self.file_label.setText("No file selected")
        self.update_remove_button()
            
    def add_dropped_files(self, file_paths):
        """Add files from drag and drop operation"""
        if not file_paths:
            return
            
        # Update input files list
        if not self.input_files:
            self.input_files = file_paths
        else:
            # Add only new files
            for path in file_paths:
                if path not in self.input_files:
                    self.input_files.append(path)
        
        # Update UI
        self.file_list.clear()
        for file in self.input_files:
            self.file_list.addItem(os.path.basename(file))
        
        self.file_label.setText(f"{len(self.input_files)} file(s) selected")
        self.update_remove_button()

    def show_video_info(self, item):
        """Display information about the selected video file"""
        # Check if FFmpeg is installed
        if not self._is_ffmpeg_installed():
            self.info_text.setHtml("<p style='color:red'>FFmpeg is not installed. Cannot retrieve video information.</p>")
            return
            
        filename = item.text()
        
        # Find the full file path
        file_path = None
        for path in self.input_files:
            if os.path.basename(path) == filename:
                file_path = path
                break
                
        if not file_path:
            return
            
        # Get video information
        info = VideoInfoExtractor.get_video_info(file_path)
        
        if not info:
            self.info_text.setText("Could not retrieve video information")
            return
            
        # Format and display the information
        info_text = f"""
        <b>File:</b> {info['filename']}
        <b>Size:</b> {info['filesize']}
        <b>Duration:</b> {info['duration']}
        <b>Resolution:</b> {info['resolution']}
        <b>Video Codec:</b> {info['video_codec']}
        <b>Audio Codec:</b> {info['audio_codec']}
        <b>Bitrate:</b> {info['bitrate']}
        """
        
        self.info_text.setHtml(info_text)

    def show_conversion_logs(self):
        """Show detailed conversion logs in a dialog"""
        if not self.last_conversion_output:
            QMessageBox.information(self, "Logs", "No conversion logs available.")
            return
            
        log_dialog = QDialog(self)
        log_dialog.setWindowTitle("Conversion Logs")
        log_dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(log_dialog)
        
        # Add text edit for logs
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setPlainText(self.last_conversion_output)
        log_text.setFont(QFont("Courier New", 9))  # Use monospace font
        layout.addWidget(log_text)
        
        # Add close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(log_dialog.close)
        layout.addWidget(close_btn)
        
        log_dialog.exec_()

    def test_nvenc_manually(self):
        """Manually test NVENC functionality and display results to user"""
        self.status_label.setText("Testing NVENC hardware encoding...")
        self.test_nvenc_btn.setEnabled(False)
        
        # Create a simple test thread
        class NvencTestThread(QThread):
            test_complete = pyqtSignal(bool, str)
            
            def run(self):
                try:
                    # Try much more lenient test parameters
                    test_cmd = [
                        "ffmpeg",
                        "-hide_banner",
                        "-y",
                        "-f", "lavfi",
                        "-i", "color=c=black:s=32x32:r=1:d=1",
                        "-c:v", "h264_nvenc",  # Use NVENC
                        "-gpu", "any",  # Try any GPU
                        "-preset", "p1",  # Fastest preset
                        "-profile:v", "baseline", # Simplest profile
                        "-b:v", "100k",  # Very low bitrate
                        "-t", "1",  # 1 second duration
                        "-f", "null",
                        "-"
                    ]
                    
                    # Run the test
                    result = subprocess.run(
                        test_cmd,
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True,
                        timeout=10
                    )
                    
                    # Collect results
                    success = result.returncode == 0
                    details = result.stderr if not success else "NVENC test successful!"
                    
                    # Check for specific error messages
                    if not success:
                        if "No NVENC capable devices found" in details:
                            details = "No NVENC capable devices found. Your GPU may not support NVENC or drivers may be missing."
                        elif "Generic error in an external library" in details:
                            details = "Generic NVENC error. Try updating your NVIDIA drivers to the latest version."
                        elif "Cannot load nvenc" in details:
                            details = "Cannot load NVENC library. Ensure you have the latest NVIDIA drivers installed."
                        elif "is not a NVENC capable device" in details:
                            details = "Your GPU doesn't support NVENC encoding. Check GPU compatibility."
                        
                    self.test_complete.emit(success, details)
                    
                except Exception as e:
                    self.test_complete.emit(False, f"Error testing NVENC: {str(e)}")
        
        # Create and run the test thread
        self.nvenc_test_thread = NvencTestThread()
        self.nvenc_test_thread.test_complete.connect(self.nvenc_test_completed)
        self.nvenc_test_thread.start()
    
    def nvenc_test_completed(self, success, details):
        """Handle NVENC test results"""
        self.test_nvenc_btn.setEnabled(True)
        
        if success:
            self.status_label.setText("NVENC is working correctly.")
            self.nvenc_checkbox.setText("Use NVIDIA NVENC hardware acceleration ✓")
            self.nvenc_checkbox.setChecked(True)
            QMessageBox.information(self, "NVENC Test", "NVENC hardware encoding is working correctly!")
        else:
            self.status_label.setText("NVENC test failed.")
            self.nvenc_checkbox.setText("Use NVIDIA NVENC hardware acceleration ✗")
            
            # Show detailed error message
            error_dialog = QMessageBox(self)
            error_dialog.setWindowTitle("NVENC Test Failed")
            error_dialog.setIcon(QMessageBox.Warning)
            error_dialog.setText("NVIDIA hardware encoding test failed.")
            error_dialog.setDetailedText(details)
            error_dialog.setStandardButtons(QMessageBox.Ok)
            
            # Add help button that links to NVIDIA drivers
            help_button = error_dialog.addButton("Get Drivers", QMessageBox.ActionRole)
            
            result = error_dialog.exec_()
            
            # Handle help button click
            if error_dialog.clickedButton() == help_button:
                import webbrowser
                webbrowser.open("https://www.nvidia.com/Download/index.aspx")
                
        # Save the test output for logs
        self.last_conversion_output = details
        self.view_logs_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoConverterApp()
    window.show()
    sys.exit(app.exec_()) 