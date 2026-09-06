from __future__ import annotations
import json, os
from dataclasses import dataclass

TRUE = {"1","true","yes","on"}

def b(name:str, default=False)->bool:
    return os.getenv(name, str(default)).strip().lower() in TRUE

def csv(name:str, default:str)->list[str]:
    return [x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()]

@dataclass(frozen=True)
class Settings:
    inbox_id: str
    targets: tuple[str,...]
    youtube_enabled: bool
    instagram_enabled: bool
    tiktok_enabled: bool

    @classmethod
    def load(cls):
        return cls(
            inbox_id=os.getenv("DRIVE_INBOX_FOLDER_ID","1_a7e-874zRIyV_ojedYj0edQisGcfnUd"),
            targets=tuple(csv("TARGET_PLATFORMS","youtube,instagram,tiktok")),
            youtube_enabled=b("YOUTUBE_ENABLED"),
            instagram_enabled=b("INSTAGRAM_ENABLED"),
            tiktok_enabled=b("TIKTOK_ENABLED"),
        )

    def enabled(self, platform:str)->bool:
        return {
            "youtube": self.youtube_enabled,
            "instagram": self.instagram_enabled,
            "tiktok": self.tiktok_enabled,
        }.get(platform, False)
