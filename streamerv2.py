import subprocess
import threading
import os
import signal
import time


FIFO_PATH = "/tmp/audio_pipe"
FADE_DURATION = 2 #seconds

def ffmpeg_string_to_subprocess_list(ffmpeg_string:str):
    argument_list = ffmpeg_string.split(' ')
    return argument_list

# note a media file/stream is a two level structure. 
# It is a container (-f parameter in ffmpeg) 
# that contains audio (and video) packets encoded in specific format (-c:a (-c:v) parameter in ffmpeg)
# -f specifies the multiplexer aka muxer and -c:a specifies the audio codec
# even if putting raw audio in a shared place like a fifo/pipe, these parameters must be specified
# that way ffmpeg knows how to structure the data to be written to the output
# and a subsequent ffmpeg process knows how to read it

class InputStream:
    '''class to read a general input, ignore any video data and write raw audio (pcm_s16le*) in NUT container to a named pipe
     *Pulse Code Modulation, 16 bit, Little Endian , NUT is a proprietary container developed by the ffmpeg project for raw audio and video'''
    def __init__(self, input_string:str):
        self.input_process = None
        self.input_string = input_string
        self.lock = threading.Lock()
        self.output_cmd = ["-vn", "-c:a", "pcm_s16le", '-f', 'nut',  "-y", FIFO_PATH]
        # -vn ensures video packets are not put in the output

    def __del__(self):
        self.stop_stream()
        
    def stop_stream (self):
        if self.input_process:
            os.killpg(os.getpgid(self.input_process.pid), signal.SIGTERM)
            self.input_process.wait()
            self.input_process = None



    def start_stream(self, input_string=None):
        ''' begin writing to the FIFO from a general source as described by input_string'''
        
        self.stop_stream()    
        if input_string:
            #optional parameter allows starting a stream from a new source
            self.input_string = input_string

        ffmpeg_cmd = ["ffmpeg"] + ffmpeg_string_to_subprocess_list(self.input_string) + self.output_cmd                
        self.input_process= subprocess.Popen(ffmpeg_cmd, preexec_fn=os.setsid)
        
    def crossfade_to_new_source(self, new_input_string):
        self.stop_stream()
        #phase one, do the crossfade
        # crossfade_command = ["ffmpeg", "-y"] + ffmpeg_string_to_subprocess_list(self.input_string) + ffmpeg_string_to_subprocess_list(new_input_string)
        # crossfade_command += ["-filter_complex",
        #                         f"[0:a][1:a]acrossfade=d={FADE_DURATION}[a]",
        #                         "-map", "[a]",
        #                         "-t", str(FADE_DURATION + 2),]
        # crossfade_command += self.output_cmd
        # subprocess.run(crossfade_command)
        #phase 2, start streaming new source
        self.start_stream(new_input_string)
        






class OutputStream:
    '''class to read raw audio (pcm_s16le, NUT) from a named pipe and write to a general output stream'''
    def __init__(self, output_string:str):
        self.output_process = None
        self.output_string = output_string
        self.input_cmd = ["-i", FIFO_PATH, "-f", "NUT", "-c:a", "pcm_s16le"]
        self._ensure_fifo()
    
    def __del__(self):
        self.stop_stream()
        
        
    def _ensure_fifo(self):
        if os.path.exists(FIFO_PATH):
            os.remove(FIFO_PATH)
        
        os.mkfifo(FIFO_PATH)
        
    def stop_stream (self):
        if self.output_process:
            os.killpg(os.getpgid(self.output_process.pid), signal.SIGTERM)
            self.output_process.wait()
            self.output_process = None

    
    def start_stream(self):
        
        self.stop_stream()
        ffmpeg_cmd = ["ffmpeg"] + self.input_cmd + ffmpeg_string_to_subprocess_list(self.output_string)
        self.output_process = subprocess.Popen(ffmpeg_cmd, preexec_fn=os.setsid)

if __name__ == "__main__":
    
    #instantiating OutputStream object creates the FIFO to ensure the InputStream object has somewhere to write to
    output = OutputStream("-c:a libmp3lame -f mp3 -content_type 'audio/mpeg' icecast://source:mArc0n1@icr-emmental.media.su.ic.ac.uk:8888/radio")
    #input = InputStream("-f alsa -i hw:1,0 -ac 2 -ar 44100")
    input = InputStream("-re -i /home/tb1516/Durufle_requiem.mp3")
    
    #start putting data into FIFO before reading data from it!!!
    input.start_stream()
    output.start_stream()
    time.sleep(60)
    input.crossfade_to_new_source("-re -i /home/tb1516/cppdev/fondue/audio_sources/Like_as_the_hart.mp3")
    time.sleep(60)
    output.stop_stream()
    input.stop_stream()

    

    