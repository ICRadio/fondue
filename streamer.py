import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import logging
logger = logging.getLogger(__name__)

FIFO_PATH = Path("/tmp/input_pipe")
LOG_FILE = "ffmpeg.log"

with open(LOG_FILE, "a") as log_file:
    log_file.write(f"\n=== STREAM RESTARTED {time.strftime('%Y-%m-%d %H:%M:%S')}===\n ")

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
        logger.info(f'[STREAMER] FIFO READY at {FIFO_PATH}')

    def _start_output_proc(self) -> None:
        cmd = [
            "ffmpeg",
            "-hide_banner",  # Added to suppress version info
            "-loglevel", "debug",  # capture maximum ffmpeg verbosity
            "-thread_queue_size", "512", # increase ALSA/FIFO queue to prevent blocking
	    "-f", "s16le", "-ar", "44100", "-ac", "2",
	    "-fflags", "+genpts", # generate timestamps if DTS errors arise
            "-i", str(FIFO_PATH),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-f", "mp3",
            "-content_type", "audio/mpeg",
            "-y",  # Overwrite output file
            self.output_path
        ]
        with open(LOG_FILE, 'a') as log_file:
            log_file.write(f"\n=== _start_output_proc {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
            subprocess.Popen(
                cmd,
                preexec_fn=os.setsid,
                stdout=log_file,
                stderr=log_file
            )

    def _validate_stream(self, url: str, timeout: float = 5.0):
        if url == "hw:CARD=CODEC":
            logger.info(f'[STREAMER] Skipping validation for codec.') # to avoid ffmpeg issue
            return True
        
        if url.startswith("rtmp://"): # give rtmp room to breathe
            timeout = 7.5

        logger.info(f"[STREAMER] Validating stream: {url}")
        
        try:
            cmd = [
                "ffmpeg",
                "-hide_banner",  # Added to suppress version info
                "-loglevel", "debug",
                "-t", "1",  # Try to decode 1 second
		"-thread_queue_size", "512",
            ]

            # Add format for soundcard input
            if url == "hw:CARD=CODEC":
                cmd += ["-f", "alsa",
		    "-fflags", "+genpts" # only generate pts for live inputs
		]

            cmd += [
                "-i", url,
                "-vn",
                "-f", "null",
                "-"
            ]

            with open(LOG_FILE, 'a') as log_file:
                log_file.write(f"\n=== _validate_stream {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=log_file
                )
        
                try:
                    proc.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.error(f"[STREAMER] Validation timed out for: {url}")
                    proc.kill()
                    return False

                if proc.returncode != 0:
                    logger.error(f"[STREAMER] Validation failed with return code {proc.returncode} for: {url}")
                return proc.returncode == 0

        except Exception as e:
            logger.error(f"[STREAMER] Exception while validating stream: {e}")
            return False

    # -- Process management
    @staticmethod
    def _kill(proc: subprocess.Popen, name: str, timeout: float = 2.0) -> None:
        if proc and proc.poll() is None:
            logger.info(f'[STREAMER] Killing {name} process')
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.error(f'[STREAMER] {name} process did not terminate in time, killing it')
                proc.kill()
            logger.error(f'[STREAMER] {name} process killed')

    def _spawn_passthrough(self, url: str) -> subprocess.Popen:
        logger.info(f'[STREAMER] Spawning passthrough for source: {url}')
        format_string = []
        loop_flag = []

        if url == "hw:CARD=CODEC":
            logger.info('[STREAMER] Using hardware codec input')
            format_string = ["-f", "alsa",
			  "-fflags", "+genpts" # generate pts for live sources
			]

        elif Path(url).is_file():
            logger.info('[STREAMER] Detected file input, enabling loop')
            loop_flag = ["-stream_loop", "-1"]
        else:
            logger.info(f'[STREAMER] Using URL input: {url}')
            format_string = ["-re"]

        cmd = [
            "ffmpeg",
            "-hide_banner",  # Added to suppress version info
            "-thread_queue_size", "512",
	    *loop_flag,
            *format_string,
            "-i", url,
            "-vn",
            "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le",
            "-f", "s16le",
            "-loglevel", "debug",
            "-y",
            str(FIFO_PATH)
        ]
        with open(LOG_FILE, 'a') as log_file:
            log_file.write(f"\n=== _spawn_passthrough {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
            return subprocess.Popen(
                cmd,
                preexec_fn=os.setsid,
                stdout=log_file,
                stderr=log_file
            )

    def inject_source(self, url: str):
        with self._lock:
            if url == self._active_url:
                return
            if not self._validate_stream(url):
                logger.error(f'[STREAMER] Invalid stream URL: {url}')
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
                logger.error(f'[STREAMER] Invalid stream URL: {url}')
                return False

            logger.info(f'[STREAMER] Crossfading from {old_url} to {url}')
            now = time.time()
            elapsed = 0.0
            if self._play_start_time is not None:
                elapsed = now - self._play_start_time
            logger.info(f'[STREAMER] Elapsed time: {elapsed:.2f} seconds')

            self._kill(self._writer, "old-writer")

            # Determine input format flags
            old_fmt = ["-f", "alsa", "-fflags", "+genpts"] if old_url == "hw:CARD=CODEC" else ["-re"]
            new_fmt = ["-f", "alsa", "-fflags", "+genpts"] if url == "hw:CARD=CODEC" else ["-re"]

            # Handle optional seeking (only if old input is seekable)
            ss_flag = ["-ss", f"{elapsed:.3f}"] if old_url != "hw:CARD=CODEC" else []

            # add loop flag for new URL if end in .mp3
            if url.endswith((".mp3", ".wav", ".flac", ".ogg")) or Path(url).is_file():
                logger.info('[STREAMER] Detected file input for new URL, enabling loop')
                new_fmt.append("-stream_loop")
                new_fmt.append("-1")

            cmd = [
                "ffmpeg",
                "-hide_banner",  # Added to suppress version info
                "-loglevel", "debug",
		"-thread_queue_size", "512",
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
            with open(LOG_FILE, 'a') as log_file:
                log_file.write(f"\n=== crossfade_stream {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
                self._writer = subprocess.Popen(
                    cmd,
                    preexec_fn=os.setsid,
                    stdout=log_file,
                    stderr=log_file
                )
            self._active_url = url
            self._play_start_time = start

    def shutdown(self) -> None:
        logger.info('[STREAMER] Shutting down')
        with self._lock:
            self._kill(self._writer, "writer")

            if hasattr(self, '_fifo_dummy_fd'):
                os.close(self._fifo_dummy_fd)
                del self._fifo_dummy_fd
            if FIFO_PATH.exists():
                FIFO_PATH.unlink()
        logger.info('[STREAMER] Shutdown complete')
