import subprocess
import threading

def subprocess_string(ffmpeg_string:str):
    argument_list = ffmpeg_string.split(' ')
    return argument_list

#note an audio file is a two level structure. 
# It is a container (-f parameter in ffmpeg) 
# that contains packets encoded in specific format (-c:a parameter in ffmpeg)
#-f specifies the multiplexer aka muxer and -c:a specifies the audio codec
#even if putting raw audio in a shared place, these parameters must be specified

class InputStream:
    #class to read an input, ignore any video data and write raw audio (pcm_16le) in NUT container to a named pipe
    def __init__(self, input_string:str):
        self.current_process = None
        self.input_string = input_string
        self.lock = threading.Lock()
        self.output_cmd = ["-vn", "-c:a", "pcm_16le", '-f', 'nut', 'pipe:1']

    def stop_stream (self):
        with self.lock:
            if self.current_process:
                self.current_process.terminate()
                self.current_process.wait()
                self.current_process = None

    def start_stream(self):
        self.stop_stream()
        input_cmd = ["ffmpeg"] + subprocess_string(self.input_string) + self.output_cmd
        with self.lock:
            self.current_process = subprocess.Popen(input_cmd)
        x=1





class OutputStream:
    #class to read raw audio (pcm16_le, NUT) from a named pipe and write to output stream
    def __init__(self, output_string:str):
        self.current_process = None
        self.output_string = output_string
        self.input_cmd = ["-i", "pipe:0"]
        self.lock = threading.Lock()


if __name__ == "__main__":
    input=InputStream("-f alsa -i hw:1,0 -ac 2 -ar 44100", 'test_string')
    input.start_stream()
    