"""Render the full local pipeline with silent stub audio, then probe the MP4."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json, subprocess
from zhicast.parse import parse_script_file
from zhicast.tts import synthesize_script
from zhicast.subtitle import attach_subtitle_plan, write_srt
from zhicast.overlay import build_scenes, render_cover
from zhicast.render import build_video
with TemporaryDirectory(prefix='zhicast-demo-') as folder:
    out=Path(folder)
    script=parse_script_file('examples/presentation-script.md')
    script=synthesize_script(script,out_dir=out/'audio',provider_name='stub')
    script=attach_subtitle_plan(script)
    write_srt(script.subtitle_cues,out/'video.srt')
    scenes=build_scenes(script,out)
    cover=render_cover(script,out)
    video=build_video(script,scenes,out)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,r_frame_rate','-of','json',str(video)],text=True))
    print(json.dumps({'tts_provider':'stub (silent audio)','segments':len(script.segments),'subtitle_cues':len(script.subtitle_cues),'scene_images':len(scenes),'cover_exists':cover.is_file(),'srt_exists':(out/'video.srt').is_file(),'video_stream':probe['streams'][0]},ensure_ascii=False,indent=2))
