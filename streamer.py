# streamer.py
import os
import subprocess
import threading
import signal
import time

FIFO_PATH = "/tmp/input_pipe"

class Streamer:
    def __init__(self, output_path="output.mp4"):
        self.output_path = output_path
        self.ffmpeg_proc = None
        self.injection_lock = threading.Lock()
        self._ensure_fifo()

    def _ensure_fifo(self):
        if os.path.exists(FIFO_PATH):
            os.remove(FIFO_PATH)
        os.mkfifo(FIFO_PATH)

    def start_stream(self):
        """Start persistent FFmpeg process that reads from the named pipe and writes to the output."""
        self._ensure_fifo()
        cmd = [
            "ffmpeg",
            "-re",
            "-i", FIFO_PATH,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-f", "flv",  # or 'mp4' or 'mpegts'
            self.output_path
        ]
        self.ffmpeg_proc = subprocess.Popen(cmd, preexec_fn=os.setsid)

    def stop_stream(self):
        if self.ffmpeg_proc:
            os.killpg(os.getpgid(self.ffmpeg_proc.pid), signal.SIGTERM)
            self.ffmpeg_proc.wait()
            self.ffmpeg_proc = None

    def crossfade_stream(self, old_url, new_url, fade_duration=2):
        """
        Crossfade from old stream to new one, then continue streaming only the new one.
        Writes the result into the named pipe.
        """
        def crossfade_then_stream():
            with self.injection_lock:
                # Phase 1: crossfade transition segment
                crossfade_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", old_url,
                    "-i", new_url,
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset=1[v];"
                    f"[0:a][1:a]acrossfade=d={fade_duration}[a]",
                    "-map", "[v]",
                    "-map", "[a]",
                    "-t", str(fade_duration + 2),
                    "-f", "mpegts",
                    "-codec:v", "mpeg1video",
                    "-codec:a", "mp2",
                    "pipe:1"
                ]

                with open(FIFO_PATH, "wb", buffering=0) as fifo:
                    subprocess.run(crossfade_cmd, stdout=fifo)

                # Phase 2: stream from new source indefinitely
                continue_cmd = [
                    "ffmpeg",
                    "-re",
                    "-i", new_url,
                    "-f", "mpegts",
                    "-codec:v", "mpeg1video",
                    "-codec:a", "mp2",
                    "pipe:1"
                ]

                with open(FIFO_PATH, "wb", buffering=0) as fifo:
                    subprocess.run(continue_cmd, stdout=fifo)

        threading.Thread(target=crossfade_then_stream, daemon=True).start()

    def inject_source(self, source_url):
        """
        Inject a single RTMP or file source directly into the stream, without crossfade.
        Useful for initial stream or instant switches.
        """
        def run_injection():
            with self.injection_lock:
                inject_cmd = [
                    "ffmpeg",
                    "-re",
                    "-i", source_url,
                    "-f", "mpegts",
                    "-codec:v", "mpeg1video",
                    "-codec:a", "mp2",
                    "pipe:1"
                ]
                with open(FIFO_PATH, "wb", buffering=0) as fifo:
                    subprocess.run(inject_cmd, stdout=fifo)

        threading.Thread(target=run_injection, daemon=True).start()
