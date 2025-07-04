import os
import subprocess
import threading
import time
from pathlib import Path

FIFO_PATH = Path("/tmp/input_pipe")


class Streamer:
    def __init__(self, output_path: str = "output.mp3", default_source: str = 'audio1') -> None:
        print('[STREAMER] Created')
        self.output_path = output_path
        self.lock = threading.Lock()
        self._out_proc    = None
        self._inject_proc = None
        self._active_url  = None

        self._make_fifo()
        self._start_output_proc()

        if default_source:
            self.inject_source(default_source)

    # -- Private methods
    def _make_fifo(self) -> None:
        if FIFO_PATH.exists():
            FIFO_PATH.unlink()
        os.mkfifo(FIFO_PATH)
        print('[STREAMER] FIFO READY')

    def _start_output_proc(self) -> None:
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-f", "s16le", "-ar", "44100", "-ac", "2",
            "-i", FIFO_PATH,
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-y",  # Overwrite output file
            self.output_path
        ]
        self._out_proc = subprocess.Popen(
            cmd,
            preexec_fn=os.setsid
        )

    @staticmethod
    def _stop_proc(proc: subprocess.Popen, name: str, timeout: float = 2.0) -> None:
        if proc and proc.poll() is None:
            print(f'[STREAMER] Stopping {name} process')
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f'[STREAMER] {name} process did not terminate in time, killing it')
                proc.kill()
            print(f'[STREAMER] {name} process stopped')

    def _spawn_inject(self, url: str) -> subprocess.Popen:

        cmd = [
            "ffmpeg",
            "-re",
            "-i", url,
            "-vn",
            "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le",
            "-f", "s16le",
            "-loglevel", "error",
            "-y",
            str(FIFO_PATH)
        ]
        print(f'[STREAMER] Injecting source: {url}')
        return subprocess.Popen(
            cmd,
            preexec_fn=os.setsid,
        )

    # -- Public methods
    def inject_source(self, url: str) -> None:
        with self.lock:
            if url == self._active_url:
                return
            self._stop_proc(self._inject_proc, "old-inject")
            self._inject_proc = self._spawn_inject(url)
            self._active_url = url

    def crossfade_stream(self, url: str, duration: int = 2) -> None:
        with self.lock:
            old_url = self._active_url
            if old_url is None or url == old_url:
                self.inject_source(url)
                return

            if getattr(self, '_xfading', False):
                print('[STREAMER] Already crossfading, skipping new request')
                return
            self._xfading = True
            old_inject_proc = self._inject_proc

        def _xfade():
            try:
                print(f'[STREAMER] Crossfading from {old_url} to {url}')
                cmd = [
                    "ffmpeg",
                    "-loglevel", "error",
                    "-re", "-i", old_url,
                    "-re", "-i", url,
                    "-filter_complex",
                    (
                        f"[0:a]atrim=0:{duration},afade=t=out:st=0:d={duration}[a0];"
                        f"[1:a]atrim=0:{duration},afade=t=in:st=0:d={duration}[a1];"
                        f"[a0][a1]amix=inputs=2:duration=first[aout]"
                    ),
                    "-map", "[aout]",
                    "-ac", "2",
                    "-ar", "44100",
                    "-c:a", "pcm_s16le",
                    "-f", "s16le",
                    "-y", str(FIFO_PATH)
                ]

                xf_proc = subprocess.Popen(
                    cmd,
                    preexec_fn=os.setsid
                )
                # xf_proc.wait()
                time.sleep(duration - 0.1)
                self._spawn_inject(url)
                self._active_url = url
                time.sleep(0.1)
                self._stop_proc(old_inject_proc, "old-inject")
                print('[STREAMER] Crossfade complete, new source injected')

            finally:
                with self.lock:
                    self._xfading = False

        threading.Thread(target=_xfade, daemon=True).start()

    def shutdown(self) -> None:
        print('[STREAMER] Shutting down')
        with self.lock:
            self._stop_proc(self._inject_proc, "inject")
            self._stop_proc(self._out_proc, "output")
            if FIFO_PATH.exists():
                FIFO_PATH.unlink()
        print('[STREAMER] Shutdown complete')