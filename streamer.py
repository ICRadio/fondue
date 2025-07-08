import os
import subprocess
import threading
import time
from pathlib import Path

FIFO_PATH = Path("/tmp/input_pipe")


class Streamer:
    def __init__(self,
                 output_path: str = "output.mp3",
                 default_source: str = 'audio1',
                 fade_duration: int = 2) -> None:

        self.output_path = output_path
        self.fade = float(fade_duration)
        self._lock = threading.Lock()
        self._writer: subprocess.Popen
        self._writer = None
        self._active_url: str
        self._active_url = None

        self._play_start_time = None
        self._make_fifo()
        self._fifo_dummy_fd = os.open(str(FIFO_PATH), os.O_RDWR)
        self._start_output_proc()
        if default_source:
            self.inject_source(default_source)
            self._active_url = default_source

    # -- Private methods
    def _make_fifo(self) -> None:
        if FIFO_PATH.exists():
            FIFO_PATH.unlink()
        os.mkfifo(FIFO_PATH)
        print(f'[STREAMER] FIFO READY at {FIFO_PATH}')

    def _start_output_proc(self) -> None:
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-f", "s16le", "-ar", "44100", "-ac", "2",
            "-i", str(FIFO_PATH),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-f", "mp3",
            "-content_type", "audio/mpeg",
            "-y",  # Overwrite output file
            self.output_path
        ]
        subprocess.Popen(
            cmd,
            preexec_fn=os.setsid
        )

    def _validate_stream(self, url: str, timeout: float = 5.0):
        print(f"[STREAMER] Validating stream: {url}")
        try:
            cmd = [
                "ffmpeg",
                "-loglevel", "error",
                "-t", "1",  # Try to decode 1 second
            ]

            # Add format for soundcard input
            if url == "hw:CARD=CODEC":
                cmd += ["-f", "alsa"]

            cmd += [
                "-i", url,
                "-vn",
                "-f", "null",
                "-"
            ]

            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"[STREAMER] Validation timed out for: {url}")
                proc.kill()
                return False

            if proc.returncode != 0:
                print(f"[STREAMER] Validation failed with return code {proc.returncode} for: {url}")
            return proc.returncode == 0

        except Exception as e:
            print(f"[STREAMER] Exception while validating stream: {e}")
            return False

    # -- Process management
    @staticmethod
    def _kill(proc: subprocess.Popen, name: str, timeout: float = 2.0) -> None:
        if proc and proc.poll() is None:
            print(f'[STREAMER] Killing {name} process')
            proc.send_signal(subprocess.signal.SIGTERM)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f'[STREAMER] {name} process did not terminate in time, killing it')
                proc.kill()
            print(f'[STREAMER] {name} process killed')

    def _spawn_passthrough(self, url: str) -> subprocess.Popen:
        if url == "hw:CARD=CODEC":
            print('[STREAMER] Using hardware codec input')
            format_string = ["-f", "alsa"]
        else:
            print(f'[STREAMER] Using URL input: {url}')
            format_string = ["-re"]

        cmd = [
            "ffmpeg",
            *format_string,
            "-i", url,
            "-vn",
            "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le",
            "-f", "s16le",
            "-loglevel", "error",
            "-y",
            str(FIFO_PATH)
        ]
        print(f'[STREAMER] Spawning passthrough for source: {url}')
        return subprocess.Popen(
            cmd,
            preexec_fn=os.setsid,
        )

    def inject_source(self, url: str):
        with self._lock:
            if url == self._active_url:
                return
            if not self._validate_stream(url):
                print(f'[STREAMER] Invalid stream URL: {url}')
                return
            self._kill(self._writer, "writer")

            start = time.time()
            self._writer = self._spawn_passthrough(url)
            self._active_url = url
            self._play_start_time = start

    def crossfade_stream(self, url: str, duration: int):
        fade = float(duration or self.fade)
        with self._lock:
            old_url = self._active_url
            if old_url is None or url == old_url:
                return self.inject_source(url)
            if not self._validate_stream(url):
                print(f'[STREAMER] Invalid stream URL: {url}')
                return False

            print(f'[STREAMER] Crossfading from {old_url} to {url}')
            now = time.time()
            elapsed = 0.0
            if self._play_start_time is not None:
                elapsed = now - self._play_start_time
            print(f'[STREAMER] Elapsed time: {elapsed:.2f} seconds')

            self._kill(self._writer, "old-writer")

            # Determine input format flags
            old_fmt = ["-f", "alsa"] if old_url == "hw:CARD=CODEC" else ["-re"]
            new_fmt = ["-f", "alsa"] if url == "hw:CARD=CODEC" else ["-re"]

            # Handle optional seeking (only if old input is seekable)
            ss_flag = ["-ss", f"{elapsed:.3f}"] if old_url != "hw:CARD=CODEC" else []

            cmd = [
                "ffmpeg",
                "-loglevel", "error",
                *ss_flag,
                *old_fmt, "-i", old_url,
                *new_fmt, "-i", url,
                "-filter_complex",
                (
                    f"[0:a]atrim=0:{fade},afade=t=out:st=0:d={fade}[a0];"
                    f"[1:a]afade=t=in:st=0:d={fade}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=longest:dropout_transition={fade}[aout]"
                ),
                "-map", "[aout]",
                "-ac", "2", "-ar", "44100",
                "-c:a", "pcm_s16le",
                "-f", "s16le",
                "-y", str(FIFO_PATH)
            ]

            start = now
            self._writer = subprocess.Popen(
                cmd,
                preexec_fn=os.setsid
            )
            self._active_url = url
            self._play_start_time = start

    def shutdown(self) -> None:
        print('[STREAMER] Shutting down')
        with self._lock:
            self._kill(self._writer, "writer")

            if hasattr(self, '_fifo_dummy_fd'):
                os.close(self._fifo_dummy_fd)
                del self._fifo_dummy_fd
            if FIFO_PATH.exists():
                FIFO_PATH.unlink()
        print('[STREAMER] Shutdown complete')