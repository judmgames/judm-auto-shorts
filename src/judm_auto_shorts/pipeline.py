from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path

from .config import Settings
from .creative import CreativeReject
from .editor import auto_edit, probe
from .hosting.cloudinary_host import delete_video, upload_video
from .metadata import make_metadata
from .providers.drive import DriveProvider
from .publishers.instagram import publish_reel
from .publishers.tiktok import publish_file as publish_tiktok
from .publishers.youtube import publish as publish_youtube
from .tokens import refresh_tiktok


KEY = {
    "youtube": "judm_youtube_id",
    "instagram": "judm_instagram_id",
    "tiktok": "judm_tiktok_id",
}


def published(props, platform):
    return bool((props or {}).get(KEY[platform]))


def prepare_oldest(drive: DriveProvider, s: Settings, ready_id: str):
    new = drive.list_new(s.inbox_id, limit=20)
    if not new:
        return None
    f = new[0]
    drive.set_props(f["id"], judm_state="ready", judm_error="")
    try:
        drive.move(f["id"], ready_id)
    except Exception:
        pass
    return drive.get(f["id"])


def process_one() -> dict:
    s = Settings.load()
    drive = DriveProvider()
    sib = drive.resolve_siblings(s.inbox_id)
    prepare_oldest(drive, s, sib["ready"])
    ready = drive.list_ready(s.inbox_id, sib["ready"], limit=20)
    if not ready:
        return {"status": "idle", "message": "No source videos in 00_INBOX or 01_READY"}

    f = ready[0]
    props = f.get("appProperties") or {}
    missing = [p for p in s.targets if not published(props, p)]
    if not missing:
        drive.move_or_mark(f["id"], sib["posted"], "posted")
        return {"status": "posted", "source": f["name"], "message": "Already complete"}

    runnable = [p for p in missing if s.enabled(p)]
    if not runnable:
        drive.set_props(
            f["id"],
            judm_state="ready",
            judm_error="waiting_for_platform_approval",
        )
        return {
            "status": "waiting",
            "source": f["name"],
            "missing": missing,
            "message": "No missing target platform is enabled yet",
        }

    drive.set_props(f["id"], judm_state="posting", judm_error="")
    result = {
        "status": "posting",
        "source": f["name"],
        "missing_before": missing,
        "attempting": runnable,
        "published": {},
    }

    try:
        with tempfile.TemporaryDirectory(prefix="judm_") as td:
            raw = Path(td) / f["name"]
            drive.download(f["id"], raw)
            pr = probe(raw)
            if pr.duration < 2 or pr.width < 240 or pr.height < 240:
                raise RuntimeError(f"Source video too small/short: {pr}")

            base_meta = make_metadata(f["name"])
            recent = drive.list_posted(sib["posted"], limit=6)
            recent_styles = [
                (x.get("appProperties") or {}).get("judm_creative_style")
                for x in recent
            ]
            recent_signatures = [
                (x.get("appProperties") or {}).get("judm_creative_signature")
                for x in recent
            ]
            recent_styles = [x for x in recent_styles if x]
            recent_signatures = [x for x in recent_signatures if x]

            avoid_styles: set[str] = set()
            avoid_signatures: set[str] = set()
            if len(recent_styles) >= 2 and recent_styles[0] == recent_styles[1]:
                avoid_styles.add(recent_styles[0])
            if (
                len(recent_signatures) >= 2
                and recent_signatures[0] == recent_signatures[1]
            ):
                avoid_signatures.add(recent_signatures[0])

            outputs = auto_edit(
                raw,
                Path(td) / "edited",
                base_meta,
                avoid_styles=avoid_styles,
                avoid_signatures=avoid_signatures,
            )
            creative = outputs["creative"]
            meta = make_metadata(f["name"], creative)
            result["creative"] = creative
            result["highlight"] = outputs["highlight"]
            result["quality"] = outputs.get("quality", {})
            result["recent_styles"] = recent_styles[:3]
            result["recent_signatures"] = recent_signatures[:3]
            result["avoid_styles"] = sorted(avoid_styles)
            result["avoid_signatures"] = sorted(avoid_signatures)

            if "youtube" in runnable:
                vid = publish_youtube(
                    outputs["youtube"],
                    meta.youtube_title,
                    meta.youtube_description,
                )
                drive.set_props(
                    f["id"],
                    judm_youtube_id=vid,
                    judm_error="",
                    judm_creative_style=creative["style"],
                    judm_creative_signature=creative.get("signature", ""),
                )
                result["published"]["youtube"] = vid

            if "instagram" in runnable:
                url, public_id = upload_video(outputs["instagram"])
                try:
                    mid = publish_reel(url, meta.instagram_caption)
                finally:
                    try:
                        delete_video(public_id)
                    except Exception:
                        pass
                drive.set_props(
                    f["id"],
                    judm_instagram_id=mid,
                    judm_error="",
                    judm_creative_style=creative["style"],
                    judm_creative_signature=creative.get("signature", ""),
                )
                result["published"]["instagram"] = mid

            if "tiktok" in runnable:
                token = (
                    refresh_tiktok()
                    if os.getenv("TIKTOK_REFRESH_TOKEN")
                    else os.getenv("TIKTOK_ACCESS_TOKEN")
                )
                tid = publish_tiktok(outputs["tiktok"], meta.tiktok_caption, token)
                drive.set_props(
                    f["id"],
                    judm_tiktok_id=tid,
                    judm_error="",
                    judm_creative_style=creative["style"],
                    judm_creative_signature=creative.get("signature", ""),
                )
                result["published"]["tiktok"] = tid

        props = drive.get(f["id"]).get("appProperties") or {}
        still = [p for p in s.targets if not published(props, p)]
        if still:
            drive.set_props(
                f["id"],
                judm_state="ready",
                judm_error="waiting:" + ",".join(still),
            )
            result.update(status="partial", missing_after=still)
        else:
            drive.move_or_mark(f["id"], sib["posted"], "posted")
            result.update(status="posted", missing_after=[])
        return result

    except CreativeReject as exc:
        msg = ("CreativeReject:" + str(exc))[:115]
        drive.set_props(f["id"], judm_state="creative_reject", judm_error=msg)
        result.update(status="creative_reject", error=msg)
        return result
    except Exception as exc:
        msg = (type(exc).__name__ + ":" + str(exc))[:115]
        drive.set_props(f["id"], judm_state="ready", judm_error=msg)
        result.update(status="error", error=msg)
        raise


def main():
    try:
        print(json.dumps(process_one(), ensure_ascii=False, indent=2))
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
