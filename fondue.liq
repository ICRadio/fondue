#!/usr/bin/env liquidsoap
# fondue liquidsoap configuration

# when started, liquid soap:
# 1. loads sources (ALSA, RTMP streams, files)
# 2. sets up the crossfading audio graph
# 3. connects to Icecast for output
# 4. starts listening on port 1234 for telnet connections

# controller opens a TCP connection to 1234 to talk to liquidsoap

# quick notes: 
# |> is a redirection, ?? is a fallback operator
# amplify using is amplify(factor, [effects])
# current fallback for dead streams is silence, ideally this would be sustain
# here we use telnet to easily integrate with the Flask surface
# note telnet is not encrypted, but we bind it to localhost only

# global settings: logging and telnet config
# =============================

set("log.file.path", "liquidsoap.log")
set("log.level", 4)  # debug level
set("server.telnet", true)  # start built in telnet server
set("server.telnet.port", 1234)  # listen on 1234
set("server.telnet.bind_addr","127.0.0.1")

# source definitions
# ==================

# studio (ALSA hardware input)
studio = input.alsa(device="hw:CARD=CODEC")
studio = studio |> amplify(1.0, [])

# test MP3 file (looped)
mp3_test = single("test.mp3")
mp3_test = mp3_test |> amplify(1.0, [])

# RTMP streams (with fallback to silence if unavailable)
rtmp_kif = input.rtmp(url="rtmp://icr-brannigan.media.su.ic.ac.uk/live/icr-kif")
rtmp_kif = (rtmp_kif |> amplify(1.0, [])) ?? blank(duration=1.0)

rtmp_morbo = input.rtmp(url="rtmp://icr-brannigan.media.su.ic.ac.uk/live/icr-morbo")
rtmp_morbo = (rtmp_morbo |> amplify(1.0, [])) ?? blank(duration=1.0)

rtmp_test = input.rtmp(url="rtmp://icr-brannigan.media.su.ic.ac.uk/live/test")
rtmp_test = (rtmp_test |> amplify(1.0, [])) ?? blank(duration=1.0)

# source switching
# ================

# studio is the currently active source (controlled via telnet)
active_source = ref("STUDIO")

# func to change sources
def source_switch() =
  switch(
    track_sensitive=false,
    [
      ({!active_source == "STUDIO"}, studio),
      ({!active_source == "mp3 - test"}, mp3_test),
      ({!active_source == "RTMP - icr-kif"}, rtmp_kif),
      ({!active_source == "RTMP - icr-morbo"}, rtmp_morbo),
      ({!active_source == "RTMP - test"}, rtmp_test),
    ]
  )

# main stream with crossfading
# =============================

# crossfade configuration
fade_in = 2.0   # fade in duration (seconds)
fade_out = 2.0  # fade out duration (seconds)

stream = source_switch() |> cross(fade_in=fade_in, fade_out=fade_out)  # fade between switched sources

# resampling and format standardization
stream = stream |> resample(44100)

# Icecast output
# ==============

# read Icecast password from environment variable
# basically call script like ICECAST_PASSWORD="m*****1" liquidsoap fondue.liq
icecast_password = os.getenv("ICECAST_PASSWORD")
if icecast_password == "" then
  log.severe("ICECAST_PASSWORD environment variable not set!")
end

ignore(  # discard return value
  output.icecast(
    %mp3(bitrate=192),
    host="icr-emmental.media.su.ic.ac.uk",
    port=8888,
    password=icecast_password,
    mount="/radio",
    stream
  )
)

# Telnet server commands
# ======================
# these commands should be called from the controller script

def set_source(source_name) =
  if list.mem(source_name, ["STUDIO", "mp3 - test", "RTMP - icr-kif", "RTMP - icr-morbo", "RTMP - test"]) then
    active_source := source_name  
    "OK: Switched to #{source_name}"
  else
    "ERROR: Unknown source #{source_name}"
  end

def get_source() =
  !active_source

# register telnet commands
server.register_command("set_source",
  "Set active source. Usage: set_source <source_name>",
  fun (args) ->
    match args with
    | [source_name] -> set_source(source_name)
    | _ -> "ERROR: Invalid arguments"
    end
)

server.register_command("get_source",
  "Get currently active source",
  fun (args) -> get_source()
)

server.register_command("list_sources",
  "List all available sources",
  fun (args) ->
    "Available sources: STUDIO, mp3 - test, RTMP - icr-kif, RTMP - icr-morbo, RTMP - test"
)
