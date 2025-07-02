# streamer.py
import subprocess
import threading

class Streamer:
    def __init__(self, output_path="output.mp4"):
        self.current_process = None
        self.output_path = output_path
        self.lock = threading.Lock()

    def start_stream(self, source_path):
        """Start streaming from a single input source (no crossfade)."""
        self.stop_stream()

        cmd = [
            "ffmpeg",
            "-re",  # real-time input (for smoother playback)
            "-i", source_path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-f", "flv",  # or 'mp4' for file output
            self.output_path
        ]

        with self.lock:
            self.current_process = subprocess.Popen(cmd)
            
    def stop_stream(self):
        with self.lock:
            if self.current_process:
                self.current_process.terminate()
                self.current_process.wait()
                self.current_process = None

    def crossfade_stream(self, old_path, new_path, duration=2):
        self.stop_stream()

        cmd = [
            "ffmpeg",
            "-y",
            "-i", old_path,
            "-i", new_path,
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={duration}:offset=3[v];"
            f"[0:a][1:a]acrossfade=d={duration}[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-t", "10",  # optional: limit total output duration
            self.output_path
        ]

        with self.lock:
            self.current_process = subprocess.Popen(cmd)
