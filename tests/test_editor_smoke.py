import os,subprocess
from pathlib import Path
from judm_auto_shorts.editor import auto_edit,probe
from judm_auto_shorts.metadata import make_metadata

def test_editor_smoke(tmp_path):
    src=tmp_path/'SLIME_test.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=1280x720:rate=30','-f','lavfi','-i','sine=frequency=700:sample_rate=48000','-t','4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(src)],check=True)
    os.environ['JUDM_HOOK_FONT']='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
    os.environ['JUDM_BODY_FONT']='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    out=auto_edit(src,tmp_path/'out',make_metadata(src.name))
    for k in ('youtube','instagram','tiktok'):
        p=Path(out[k]); assert p.exists() and p.stat().st_size>1000
        pr=probe(p); assert pr.width==1080 and pr.height==1920
