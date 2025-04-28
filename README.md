# Video Converter

A simple PyQt-based GUI application that allows users to convert video files to different formats using FFmpeg.

## Features

- Select one or multiple video files for conversion
- Choose output format (mp4, mkv, avi, mov, webm)
- Select quality presets (Fast/Low, Medium, Slow/High)
- NVIDIA NVENC hardware acceleration support for faster encoding
- Specify custom output directory
- Progress bar with estimated time remaining (ETA) for conversion
- Video information display (resolution, codec, duration, etc.)
- Error handling for missing files or FFmpeg installation
- Batch processing of multiple files sequentially
- Drag and drop support for adding video files

## Requirements

- Python 3.6+
- FFmpeg (must be installed and accessible in your system PATH)
- PyQt5
- NVIDIA GPU with NVENC support (optional, for hardware acceleration)

## Installation

1. Ensure FFmpeg is installed on your system:
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
   - **macOS**: Install via Homebrew: `brew install ffmpeg`
   - **Linux**: Install via package manager: `sudo apt install ffmpeg` (Ubuntu/Debian) or `sudo dnf install ffmpeg` (Fedora)

2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```
   python video_converter.py
   ```

2. Select one or more video files using the "Select Video File(s)" button or drag-and-drop
3. (Optional) Select an output directory
4. Choose the desired output format and quality preset:
   - **Fast (Low Quality)**: Quick conversion but lower quality output
   - **Medium Quality**: Balanced conversion speed and quality
   - **Slow (High Quality)**: Best quality output but takes longer to process
5. (Optional) Enable NVIDIA NVENC hardware acceleration for faster encoding if you have a compatible NVIDIA GPU
6. Click "Start Conversion" to begin the process
7. Monitor progress with the progress bar and ETA display
8. A notification will appear when the conversion is complete

## Hardware Acceleration

The application supports NVIDIA NVENC hardware acceleration for much faster video encoding:

- Requires an NVIDIA GPU with NVENC support (most GTX 960+ and RTX series)
- Automatically checks if NVENC is available on your system
- Falls back to software encoding if hardware encoding isn't available
- Can significantly reduce conversion time while maintaining quality

## Limitations

- Progress estimation and ETA are approximate
- Limited output format options
- Requires FFmpeg to be installed separately
- NVENC hardware acceleration only available on compatible NVIDIA GPUs

## License

MIT 