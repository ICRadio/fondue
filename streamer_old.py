# streamer.py
import os
import subprocess
import threading
import signal
import time

FIFO_PATH = "/tmp/input_pipe"

class Streamer:
    def __init__(self, output_path="output.mp3", default_source=None):
        print('[STREAMER] Created')
        self.output_path = output_path
        self.default_source = default_source
        self.stream_time = time.time()
        self.ffmpeg_proc = None
        self.event = threading.Event()
        self._ensure_fifo()
        self.start_stream()
        if self.default_source:
            self.inject_source(self.default_source)

    def _ensure_fifo(self):
        if os.path.exists(FIFO_PATH):
            os.remove(FIFO_PATH)
        os.mkfifo(FIFO_PATH)
        print('[STREAMER] FIFO ACTIVE')

    def start_stream(self):
        """Start persistent FFmpeg process that reads from the named pipe and writes to the output."""
        cmd = [
            "ffmpeg",
            "-re",
            "-f",
            "nut",
            "-i", FIFO_PATH,
            "-c:a",
            "libmp3lame",
            self.output_path,
        ]
        self.ffmpeg_proc = subprocess.Popen(
            cmd,
            preexec_fn=os.setsid,
            # stdout=sys.stdout,
            # stderr=sys.stderr
        )
        print('[STREAMER] STREAM STARTED')

    def stop_stream(self):
        if self.ffmpeg_proc:
            print('[STREAMER] trying to kill')
            # os.killpg(os.getpgid(self.ffmpeg_proc.pid), signal.SIGTERM)
            self.ffmpeg_proc.kill()
            # self.ffmpeg_proc.wait()
            # self.ffmpeg_proc = None
            print('[STREAMER] after kill')

    def crossfade_stream(self, old_url, new_url, fade_duration=2):
        """
        Crossfade from old stream to new one, then continue streaming only the new one.
        Writes the result into the named pipe.
        """

        def _impl():
            # Phase 1: crossfade transition segment
            print('[STREAMER] ATTEMPTING CROSSFADE')
            self.event.set()
            print('[STREAMER] CHECKPOINT 1')
            time.sleep(5)
            print('[STREAMER] DONE SLEEPING')
            self.event.clear()
            print('[STREAMER] CHECKPOINT 2')
            # crossfade_cmd = [
            #     "ffmpeg",
            #     "-re", "-t", str(fade_duration + 2), "-i", old_url,
            #     "-re", "-t", str(fade_duration + 2), "-i", new_url,
            #     "-filter_complex", f"[0:a][1:a]acrossfade=d={fade_duration}[a]",
            #     "-map", "[a]",
            #     "-vn",
            #     "-c:a", "pcm_s16le",
            #     "-f", "nut",
            #     "-y",
            #     FIFO_PATH,
            # ]
            # # raw command to crossfade
            # # ffmpeg -re -t 4 -i c1c2.wav -re -t 4 -i creep.mp3 -filter_complex "[0:a][1:a]acrossfade=d=2[a]" -map "[a]" -vn -c:a libmp3lame test.mp3
            # try:
            #     subprocess.run(crossfade_cmd, timeout=15)
            # except subprocess.TimeoutExpired:
            #     print('[STREAMER] FUCK SAKE')

            print('[STREAMER] DONE FADING')

            # Phase 2: stream from new source indefinitely
            continue_cmd = [
                "ffmpeg",
                "-re",
                "-i", new_url,
                "-vn",
                "-c:a", "pcm_s16le",
                "-f", "nut",
                "-y",
                FIFO_PATH
            ]

            self.ffmpeg_proc = subprocess.Popen(continue_cmd)
            self.stream_time = time.time()
            print('[STREAMER] NEW SOURCE FROM NOW')

            while not self.event.is_set():
                if self.ffmpeg_proc.poll():
                    return

            self.stop_stream()
            print('[STREAMER] STOPPED STREAM')

        threading.Thread(target=_impl).start()

    def inject_source(self, source_url):
        """
        Inject a single RTMP or file source directly into the stream, without crossfade.
        Useful for initial stream or instant switches.
        """
        def _impl():
            inject_cmd = [
                "ffmpeg",
                "-re",
                "-i", source_url,
                "-vn",
                "-c:a",
                "pcm_s16le",
                "-f",
                "nut",
                "-y",
                FIFO_PATH
            ]
            self.ffmpeg_proc = subprocess.Popen(inject_cmd)
            print('[STREAMER] INJECTED SOURCE')
            # self.event.wait()
            # print('[STREAMER] killing initial audio stream')
            # self.stop_stream()

        threading.Thread(target=_impl).start()
