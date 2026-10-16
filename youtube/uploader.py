import logging
import time
from pathlib import Path
from typing import List, Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

import config
from growth.network_guard import NetworkGuard, NETWORK_EXCEPTIONS
from youtube.auth import YouTubeAuth

logger = logging.getLogger(__name__)


class YouTubeUploader:
    def __init__(self, auth: Optional[YouTubeAuth] = None):
        self.auth = auth or YouTubeAuth()
        self._service = None

    @property
    def service(self):
        if self._service is None:
            creds = self.auth.get_credentials()
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        category_id: str = "27",
        privacy_status: Optional[str] = None,
        pinned_comment: Optional[str] = None,
        thumbnail_path: Optional[Path] = None,
    ) -> dict:
        """
        Uploads an MP4 video to YouTube with metadata and returns video details.
        Attaches custom thumbnail if thumbnail_path is provided.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        privacy_status = privacy_status or config.YOUTUBE_PRIVACY_STATUS
        tags = tags or []

        # Sanitize title (max 100 chars for YouTube)
        clean_title = title[:95] if len(title) > 95 else title

        body = {
            "snippet": {
                "title": clean_title,
                "description": description,
                "tags": tags,
                "categoryId": str(category_id),
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        logger.info(f"Starting upload for: '{clean_title}' (Privacy: {privacy_status})")

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5,  # 5MB chunks
        )

        request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        retry = 0
        max_retries = 10

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")
            except NETWORK_EXCEPTIONS as net_err:
                logger.warning(f"⚠️ Network disconnected during upload ({net_err}). Pausing and waiting for reconnection...")
                NetworkGuard.wait_for_network()
                logger.info("🌐 Network restored. Resuming YouTube upload chunk...")
                time.sleep(2)
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504] and retry < max_retries:
                    retry += 1
                    wait_time = 2 ** retry
                    logger.warning(f"YouTube server error ({e.resp.status}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"YouTube upload error: {e}")
                    from youtube.upload_healer import YouTubeUploadHealer
                    healer = YouTubeUploadHealer(uploader=self)
                    
                    # Attempt auto-correction (metadata cleanup, token refresh, media remux, etc.)
                    def retry_cb(r_path, r_meta):
                        return self.upload_video(
                            video_path=r_path,
                            title=r_meta.get("title", clean_title),
                            description=r_meta.get("description", description),
                            tags=r_meta.get("tags", tags),
                            category_id=category_id,
                            privacy_status=privacy_status,
                            pinned_comment=pinned_comment,
                            thumbnail_path=thumbnail_path,
                        )

                    corrected_res = healer.attempt_auto_correction(
                        error=e,
                        video_path=video_path,
                        metadata={"title": clean_title, "description": description, "tags": tags},
                        retry_callback=retry_cb,
                    )
                    if corrected_res:
                        return corrected_res

                    raise e

        video_id = response.get("id")
        video_url = f"https://youtu.be/{video_id}"
        logger.info(f"Successfully uploaded video to YouTube! URL: {video_url}")

        # Post pinned discussion comment if requested
        if pinned_comment and video_id:
            try:
                self.post_comment(video_id, pinned_comment)
            except Exception as e:
                logger.warning(f"Could not post pinned comment: {e}")

        # Attach custom thumbnail if provided
        thumbnail_attached = False
        if thumbnail_path and video_id:
            thumbnail_attached = self.set_thumbnail(video_id, thumbnail_path)

        return {
            "video_id": video_id,
            "video_url": video_url,
            "title": clean_title,
            "privacy_status": privacy_status,
            "thumbnail_attached": thumbnail_attached,
        }

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> bool:
        """
        Attaches a custom thumbnail to an uploaded YouTube video via Data API v3.
        """
        if not thumbnail_path or not Path(thumbnail_path).exists():
            logger.warning(f"Thumbnail path does not exist: {thumbnail_path}")
            return False

        try:
            logger.info(f"🖼️ Setting custom thumbnail for video {video_id}: {Path(thumbnail_path).name}")
            media = MediaFileUpload(
                str(thumbnail_path),
                mimetype="image/jpeg" if Path(thumbnail_path).suffix.lower() in [".jpg", ".jpeg"] else "image/png",
                resumable=False,
            )
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=media,
            ).execute()
            logger.info(f"✨ Custom thumbnail successfully set for video {video_id}!")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Could not set custom thumbnail for video {video_id}: {e}")
            return False

    def post_comment(self, video_id: str, comment_text: str) -> None:
        """
        Posts a top-level comment on the newly uploaded video.
        """
        logger.info(f"Posting comment to video {video_id}...")
        self.service.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text,
                        }
                    },
                }
            },
        ).execute()
