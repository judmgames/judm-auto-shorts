from __future__ import annotations
import json, math, os, subprocess
from dataclasses import dataclass
from pathlib import Path
import cv2, numpy as np
from .metadata import Metadata

@dataclass
class Probe: duration:float; width:int; height:int; fps:float; has_audio:bool
@dataclass
class Highlight: start:float; duration:float; peak_at:float; confidence:float

def run(cmd:list[str]):
    return subprocess.run(cmd, check=True, text=True, capture_output=True)

def probe(path:str|Path)->Probe:
    d=json.loads(run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)]).stdout)
    v=next(s for s in d["streams"] if s.get("codec_type")=="video")
    fr=v.get("avg_frame_rate") or "30/1"; a,b=fr.split("/"); fps=float(a)/max(float(b),1)
    dur=float(v.get("duration") or d.get("format",{}).get("duration") or 0)
    return Probe(dur,int(v["width"]),int(v["height"]),fps,any(s.get("codec_type")=="audio" for s in d["streams"]))

def norm(x):
    if not len(x): return x
    lo,hi=np.percentile(x,[10,95]); return np.zeros_like(x) if hi<=lo+1e-9 else np.clip((x-lo)/(hi-lo),0,1)

def visual_scores(path, hz=2.0):
    cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 30; step=max(int(round(fps/hz)),1)
    t=[]; s=[]; pg=ph=None; i=0
    while True:
        ok,f=cap.read()
        if not ok: break
        if i%step: i+=1; continue
        sm=cv2.resize(f,(320,180),interpolation=cv2.INTER_AREA); g=cv2.cvtColor(sm,cv2.COLOR_BGR2GRAY); hsv=cv2.cvtColor(sm,cv2.COLOR_BGR2HSV)
        h=cv2.calcHist([hsv],[0,1],None,[24,24],[0,180,0,256]); cv2.normalize(h,h)
        if pg is None: score=0.0
        else:
            motion=float(np.mean(cv2.absdiff(g,pg)))/255
            scene=float(cv2.compareHist(ph,h,cv2.HISTCMP_BHATTACHARYYA))
            edge=float(np.mean(cv2.absdiff(cv2.Canny(pg,80,160),cv2.Canny(g,80,160))))/255
            score=.58*motion+.27*scene+.15*edge
        t.append(i/fps); s.append(score); pg,ph=g,h; i+=1
    cap.release(); return np.asarray(t,np.float32),np.asarray(s,np.float32)

def audio_scores(path,hz=2.0):
    try: raw=subprocess.check_output(["ffmpeg","-v","error","-i",str(path),"-vn","-ac","1","-ar","8000","-f","f32le","pipe:1"])
    except subprocess.CalledProcessError: return np.array([]),np.array([])
    x=np.frombuffer(raw,np.float32); win=max(int(8000/hz),1)
    rms=np.asarray([float(np.sqrt(np.mean(seg*seg)+1e-12)) for i in range(math.ceil(len(x)/win)) if (seg:=x[i*win:(i+1)*win]).size],np.float32)
    return np.arange(len(rms),dtype=np.float32)/hz,rms

def choose_highlight(path,target=18.0,min_len=12.0,max_len=24.0)->Highlight:
    p=probe(path)
    if p.duration<=0: raise ValueError("duration unavailable")
    if p.duration<=max_len: return Highlight(0,p.duration,p.duration*.55,1)
    vt,vs=visual_scores(path)
    if not len(vt): return Highlight(0,min(target,p.duration),target*.55,0)
    vs=norm(vs); ai=np.zeros_like(vs)
    if p.has_audio:
        at,av=audio_scores(path)
        if len(at): ai=np.interp(vt,at,norm(av),left=0,right=0)
    c=.78*vs+.22*ai
    if len(c)>=3: c=.8*c+.2*np.convolve(c,np.ones(3)/3,mode="same")
    L=min(max(target,min_len),max_len,p.duration-.1); step=float(np.median(np.diff(vt))) if len(vt)>1 else .5; n=max(int(L/step),1)
    if len(c)<=n: start=0
    else:
        sums=np.convolve(c,np.ones(n),mode="valid"); best=int(np.argmax(sums)); peak_global=float(vt[min(best+int(np.argmax(c[best:best+n])),len(vt)-1)])
        start=max(0,peak_global-L*.58); start=min(start,p.duration-L)
    mask=(vt>=start)&(vt<=start+L); local=c[mask]
    peak=float(vt[mask][int(np.argmax(local))]-start) if len(local) else L*.55
    conf=float(np.mean(np.sort(local)[-max(1,int(len(local)*.15)):])) if len(local) else 0
    return Highlight(start,L,peak,conf)

def font(role="body"):
    if role=="hook": candidates=[os.getenv("JUDM_HOOK_FONT",""),str(Path.home()/".local/share/fonts/DoHyeon-Regular.ttf"),"/usr/local/share/fonts/judm/DoHyeon-Regular.ttf"]
    else: candidates=[os.getenv("JUDM_BODY_FONT",""),"/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for x in candidates:
        if x and Path(x).exists(): return x
    family="Do Hyeon" if role=="hook" else "Noto Sans CJK KR"
    cp=subprocess.run(["fc-match","-f","%{file}",family],text=True,capture_output=True)
    if cp.stdout.strip() and Path(cp.stdout.strip()).exists(): return cp.stdout.strip()
    raise FileNotFoundError(f"font missing: {role}")

def esc(s): return s.replace("\\",r"\\").replace(":",r"\:").replace("'",r"\'").replace("%",r"\%").replace(",",r"\,")
def hook_size(s):
    n=len(s.replace(" ","")); return 78 if n<=12 else 68 if n<=16 else 60 if n<=20 else 54

def render(src,dst,meta:Metadata,hl:Highlight,platform:str):
    src,dst=Path(src),Path(dst); dst.parent.mkdir(parents=True,exist_ok=True); p=probe(src)
    hf,bf=font("hook"),font("body"); hs=hook_size(meta.hook); hk,lab=esc(meta.hook),esc(meta.game_label)
    # Preserve the entire gameplay view; blurred background fills 9:16. Add two small zoom punches around hook and payoff.
    z2=max(1.5,min(hl.peak_at,hl.duration-1.2)); z1_end=min(1.15,hl.duration)
    factor=f"1+0.035*between(t,0,{z1_end:.2f})+0.045*between(t,{max(0,z2-.45):.2f},{min(hl.duration,z2+.55):.2f})"
    base=(f"[0:v]trim=start={hl.start:.3f}:duration={hl.duration:.3f},setpts=PTS-STARTPTS,split=2[bg0][fg0];"
          f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=34,eq=brightness=-0.10:saturation=.82[bg];"
          f"[fg0]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
          f"[comp]scale=w='trunc(1080*({factor})/2)*2':h='trunc(1920*({factor})/2)*2':eval=frame,"
          f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2[zoom]")
    cta=esc("살았다" if meta.game_key in {"SLIME","BLINE"} else "한 번 더")
    c0=max(0,hl.duration-2.2)
    if platform=="tiktok":
        texts=(f";[zoom]drawtext=fontfile='{hf}':text='{hk}':fontsize={hs}:fontcolor=white:borderw=4:bordercolor=black@.92:"
               f"box=1:boxcolor=black@.38:boxborderw=24:x=(w-text_w)/2:y=170:enable='between(t,0,3.2)'[vout]")
    else:
        texts=(f";[zoom]drawtext=fontfile='{hf}':text='{hk}':fontsize={hs}:fontcolor=white:borderw=4:bordercolor=black@.92:"
               f"box=1:boxcolor=black@.38:boxborderw=24:x=(w-text_w)/2:y=170:enable='between(t,0,3.2)'[t1];"
               f"[t1]drawtext=fontfile='{bf}':text='{lab}':fontsize=34:fontcolor=white@.92:borderw=2:bordercolor=black@.8:x=54:y=h-180[t2];"
               f"[t2]drawtext=fontfile='{hf}':text='{cta}':fontsize=54:fontcolor=white:borderw=4:bordercolor=black@.9:"
               f"x=(w-text_w)/2:y=h-310:enable='between(t,{c0:.2f},{hl.duration:.2f})'[vout]")
    fc=base+texts
    if p.has_audio: fc+=f";[0:a]atrim=start={hl.start:.3f}:duration={hl.duration:.3f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.08,afade=t=out:st={max(0,hl.duration-.22):.2f}:d=0.22[aout]"
    cmd=["ffmpeg","-y","-v","error","-i",str(src),"-filter_complex",fc,"-map","[vout]"]
    if p.has_audio: cmd += ["-map","[aout]","-c:a","aac","-b:a","160k","-ar","48000"]
    else: cmd += ["-an"]
    cmd += ["-c:v","libx264","-preset","medium","-crf","19","-pix_fmt","yuv420p","-r","30","-movflags","+faststart","-maxrate","8M","-bufsize","16M",str(dst)]
    run(cmd); return str(dst)

def auto_edit(src,out_dir,meta:Metadata):
    hl=choose_highlight(src); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); stem=Path(src).stem
    result={}
    for p,s in (("youtube","yt"),("instagram","ig"),("tiktok","tt")): result[p]=render(src,out/f"{stem}_{s}.mp4",meta,hl,p)
    result["highlight"]={"start":round(hl.start,3),"duration":round(hl.duration,3),"peak_at":round(hl.peak_at,3),"confidence":round(hl.confidence,3)}
    return result
