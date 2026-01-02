Run python run_broadcast.py
/opt/hostedtoolcache/Python/3.10.19/x64/lib/python3.10/site-packages/google/api_core/_python_version_support.py:266: FutureWarning: You are using a Python version (3.10.19) which Google will stop supporting in new releases of google.api_core once it reaches its end of life (2026-10-04). Please upgrade to the latest Python version, or at least Python 3.11, to continue receiving updates for google.api_core past that date.
  warnings.warn(message, FutureWarning)
/home/runner/work/Daily-ai-News/Daily-ai-News/main.py:25: FutureWarning: 

All support for the `google.generativeai` package has ended. It will no longer be receiving 
updates or bug fixes. Please switch to the `google.genai` package as soon as possible.
See README for more details:

https://github.com/google-gemini/deprecated-generative-ai-python/blob/main/README.md

  import google.generativeai as genai_old  # type: ignore
 >> 📰 GATHERING INTEL (RSS PRIMARY)...
 >> ✍️ WRITING FULL EPISODE (SEGMENTED)...
    ✍️ Segment 1 attempt 1/3 (target 607 words)
    ⚠️ Segment 1 short (557 words). Retrying with stronger length pressure...
    ✍️ Segment 1 attempt 2/3 (target 607 words)
    ✍️ Segment 2 attempt 1/3 (target 1100 words)
    ⚠️ Segment 2 short (819 words). Retrying with stronger length pressure...
    ✍️ Segment 2 attempt 2/3 (target 1100 words)
    ⚠️ Segment 2 short (888 words). Retrying with stronger length pressure...
    ✍️ Segment 2 attempt 3/3 (target 1100 words)
    ⚠️ Segment 2 short (700 words). Retrying with stronger length pressure...
    ✍️ Segment 3 attempt 1/3 (target 800 words)
    ⚠️ Segment 3 short (700 words). Retrying with stronger length pressure...
    ✍️ Segment 3 attempt 2/3 (target 800 words)
    ✍️ Segment 4 attempt 1/3 (target 1400 words)
    ⚠️ Segment 4 short (1007 words). Retrying with stronger length pressure...
    ✍️ Segment 4 attempt 2/3 (target 1400 words)
    ⚠️ Segment 4 short (836 words). Retrying with stronger length pressure...
    ✍️ Segment 4 attempt 3/3 (target 1400 words)
    ⚠️ Segment 4 short (984 words). Retrying with stronger length pressure...
    ✍️ Segment 5 attempt 1/3 (target 607 words)
    ⚠️ Segment 5 short (546 words). Retrying with stronger length pressure...
    ✍️ Segment 5 attempt 2/3 (target 607 words)
    ⚠️ Segment 5 short (544 words). Retrying with stronger length pressure...
    ✍️ Segment 5 attempt 3/3 (target 607 words)
    ⚠️ Segment 5 short (491 words). Retrying with stronger length pressure...
    ✅ Script complete: 4142 words (~26.7 min est @ 155.0 wpm)
    Estimated minutes (text): ~26.7
 >> 🎙️ RECORDING (TTS)...
 >> 🎚️ STITCHING (ffmpeg concat)...
ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers
  built with gcc 13 (Ubuntu 13.2.0-23ubuntu3)
  configuration: --prefix=/usr --extra-version=3ubuntu5 --toolchain=hardened --libdir=/usr/lib/x86_64-linux-gnu --incdir=/usr/include/x86_64-linux-gnu --arch=amd64 --enable-gpl --disable-stripping --disable-omx --enable-gnutls --enable-libaom --enable-libass --enable-libbs2b --enable-libcaca --enable-libcdio --enable-libcodec2 --enable-libdav1d --enable-libflite --enable-libfontconfig --enable-libfreetype --enable-libfribidi --enable-libglslang --enable-libgme --enable-libgsm --enable-libharfbuzz --enable-libmp3lame --enable-libmysofa --enable-libopenjpeg --enable-libopenmpt --enable-libopus --enable-librubberband --enable-libshine --enable-libsnappy --enable-libsoxr --enable-libspeex --enable-libtheora --enable-libtwolame --enable-libvidstab --enable-libvorbis --enable-libvpx --enable-libwebp --enable-libx265 --enable-libxml2 --enable-libxvid --enable-libzimg --enable-openal --enable-opencl --enable-opengl --disable-sndio --enable-libvpl --disable-libmfx --enable-libdc1394 --enable-libdrm --enable-libiec61883 --enable-chromaprint --enable-frei0r --enable-ladspa --enable-libbluray --enable-libjack --enable-libpulse --enable-librabbitmq --enable-librist --enable-libsrt --enable-libssh --enable-libsvtav1 --enable-libx264 --enable-libzmq --enable-libzvbi --enable-lv2 --enable-sdl2 --enable-libplacebo --enable-librav1e --enable-pocketsphinx --enable-librsvg --enable-libjxl --enable-shared
  libavutil      58. 29.100 / 58. 29.100
  libavcodec     60. 31.102 / 60. 31.102
  libavformat    60. 16.100 / 60. 16.100
  libavdevice    60.  3.100 / 60.  3.100
  libavfilter     9. 12.100 /  9. 12.100
  libswscale      7.  5.100 /  7.  5.100
  libswresample   4. 12.100 /  4. 12.100
  libpostproc    57.  3.100 / 57.  3.100
Input #0, concat, from '/home/runner/work/Daily-ai-News/Daily-ai-News/episode_audio/concat_200ffaee29d24fb5bfb88962c23f73c5.txt':
  Duration: N/A, start: -0.025057, bitrate: 192 kb/s
  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 192 kb/s
    Metadata:
      encoder         : Lavc60.31
Stream mapping:
  Stream #0:0 -> #0:0 (mp3 (mp3float) -> mp3 (libmp3lame))
Press [q] to stop, [?] for help
Output #0, mp3, to '/home/runner/work/Daily-ai-News/Daily-ai-News/episode_audio/podcast_2026-01-02.mp3':
  Metadata:
    TSSE            : Lavf60.16.100
  Stream #0:0: Audio: mp3, 44100 Hz, stereo, fltp, 192 kb/s
    Metadata:
      encoder         : Lavc60.31.102 libmp3lame
size=       0kB time=N/A bitrate=N/A speed=N/A    
[mp3 @ 0x55cabb4dcf80] Estimating duration from bitrate, this may be inaccurate
[libmp3lame @ 0x55cabb4f2400] Queue input is backward in time
[mp3 @ 0x55cabb4f1b00] Application provided invalid, non monotonically increasing dts to muxer in stream 0: 662447 >= 994
[mp3 @ 0x55cabb4f1b00] Application provided invalid, non monotonically increasing dts to muxer in stream 0: 662447 >= 2146
[mp3 @ 0x55cabb4f1b00] Application provided invalid, non monotonically increasing dts to muxer in stream 0: 662447 >= 3298
[mp3 @ 0x55cabb4f1b00] Application provided invalid, non monotonically increasing dts to muxer in stream 0: 662447 >= 4450
[mp3 @ 0x55cabb4f1b00] Application provided invalid, non monotonically increasing dts to muxer in stream 0: 662447 >= 5602
