"""
VideoManager with non-blocking background processing.
Video is prepared asynchronously without blocking bot startup.
"""
import os
import logging
import asyncio
import aiohttp
from aiogram.types import FSInputFile

logger = logging.getLogger("VideoManager")


class VideoManager:
    SOURCE_URL = "https://github.com/Rewixx-png/rew-host-assets/raw/main/%D0%9D%D0%BE%D0%B2%D1%8B%D0%B9%20%D0%BF%D1%80%D0%BE%D0%BA%D1%82%20114%20%5B33803A3%5D.mp4"
    
    RAW_PATH = "storage/video_raw.mp4"
    PROCESSED_PATH = "storage/video_smooth_60fps.mp4"
    
    _file_id: str | None = None
    _ready: bool = False
    _preparation_task: asyncio.Task | None = None
    
    @classmethod
    async def prepare(cls):
        if not os.path.exists("storage"):
            os.makedirs("storage")
        
        if os.path.exists(cls.PROCESSED_PATH):
            cls._ready = True
            return
        
        cls._preparation_task = asyncio.create_task(cls._prepare_video())
        logger.info("🎬 Video preparation started in background")
    
    @classmethod
    async def _prepare_video(cls):
        try:
            if not os.path.exists(cls.RAW_PATH):
                await cls._download_video()
            
            if os.path.exists(cls.RAW_PATH) and not os.path.exists(cls.PROCESSED_PATH):
                await cls._process_video()
            
            cls._ready = True
            logger.info("✅ Video preparation completed")
            
        except Exception as e:
            logger.error(f"❌ Video preparation failed: {e}")
            cls._ready = False
    
    @classmethod
    async def _download_video(cls):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cls.SOURCE_URL, timeout=30) as resp:
                    if resp.status == 200:
                        with open(cls.RAW_PATH, 'wb') as f:
                            while True:
                                chunk = await resp.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                        logger.info("✅ Video downloaded")
                    else:
                        raise Exception(f"Download failed: {resp.status}")
        except Exception as e:
            logger.error(f"❌ Download error: {e}")
            raise
    
    @classmethod
    async def _process_video(cls):
        try:
            cmd = [
                "ffmpeg",
                "-i", cls.RAW_PATH,
                "-vf", "fps=30,scale=480:-1:flags=lanczos",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-c:a", "copy",
                "-movflags", "+faststart",
                "-y",
                cls.PROCESSED_PATH
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                await asyncio.wait_for(process.wait(), timeout=120)
            except asyncio.TimeoutError:
                process.kill()
                raise Exception("FFmpeg timeout")
            
            if process.returncode == 0:
                if os.path.exists(cls.RAW_PATH):
                    os.remove(cls.RAW_PATH)
                    logger.info("🗑️ Raw video removed")
                
                size_mb = os.path.getsize(cls.PROCESSED_PATH) / (1024 * 1024)
                logger.info(f"✅ Video processed: {size_mb:.1f}MB")
            else:
                stderr = await process.stderr.read() if process.stderr else b""
                raise Exception(f"FFmpeg failed: {stderr.decode()[:200]}")
                
        except Exception as e:
            logger.error(f"❌ Render error: {e}")
            if os.path.exists(cls.RAW_PATH) and not os.path.exists(cls.PROCESSED_PATH):
                os.rename(cls.RAW_PATH, cls.PROCESSED_PATH)
                logger.info("⚠️ Using raw video as fallback")
    
    @classmethod
    def get_file(cls):
        if cls._file_id:
            return cls._file_id
        
        if os.path.exists(cls.PROCESSED_PATH):
            return FSInputFile(cls.PROCESSED_PATH)
        
        if os.path.exists(cls.RAW_PATH):
            return FSInputFile(cls.RAW_PATH)
        
        return None
    
    @classmethod
    def is_ready(cls) -> bool:
        return cls._ready
    
    @classmethod
    def set_file_id(cls, file_id: str):
        if file_id:
            cls._file_id = file_id
            logger.info("📎 Video file_id cached")
    
    @classmethod
    async def wait_for_ready(cls, timeout: float = 30.0):
        start = asyncio.get_event_loop().time()
        while not cls._ready:
            if asyncio.get_event_loop().time() - start > timeout:
                break
            await asyncio.sleep(0.5)
