from __future__ import annotations
import os, uuid
import cloudinary, cloudinary.uploader

def configure():
    cloudinary.config(cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],api_key=os.environ["CLOUDINARY_API_KEY"],api_secret=os.environ["CLOUDINARY_API_SECRET"],secure=True)

def upload_video(path:str)->tuple[str,str]:
    configure(); public_id=f"judm-auto/{uuid.uuid4().hex}"
    r=cloudinary.uploader.upload_large(path,resource_type="video",public_id=public_id,overwrite=False)
    return r["secure_url"],public_id

def delete_video(public_id:str):
    configure(); return cloudinary.uploader.destroy(public_id,resource_type="video",invalidate=True)
