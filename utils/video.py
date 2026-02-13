import os
import asyncio
import logging
import aiohttp
from aiogram.types import FSInputFile

logger = logging.getLogger("VideoManager")

class VideoManager:
    SOURCE_URL = "https://github.com/Rewixx-png/rew-host-assets/raw/main/94ad313e2d09bc8fa8c70b09384200e9.mp4"
    RAW_PATH = "storage/video_raw.mp4"
    PROCESSED_PATH = "storage/video_fixed.mp4"
    
    _file_id: str | None = None

    @classmethod
    async def prepare(cls):
        if not os.path.exists("storage"):
            os.makedirs("storage")

        if os.path.exists(cls.PROCESSED_PATH):
            logger.info("✅ Processed video found. Skipping download/conversion.")
            return

        logger.info("⬇️ Downloading video...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cls.SOURCE_URL) as resp:
                    if resp.status == 200:
                        with open(cls.RAW_PATH, 'wb') as f:
                            f.write(await resp.read())
                    else:
                        logger.error(f"❌ Failed to download video: {resp.status}")
                        return
        except Exception as e:
            logger.error(f"❌ Download error: {e}")
            return

        logger.info("🔄 Running FFmpeg to fix aspect ratio (16:9)...")
        try:
            # Исправленная команда для 100% совместимости с Telegram
            # -pix_fmt yuv420p: Обязательно для поддержки всех плееров (иначе видео черное/зеленое)
            # -movflags +faststart: Чтобы видео начинало играть сразу, не дожидаясь полной загрузки (превью)
            # -profile:v main -level 3.1: Максимальная совместимость
            # scale + pad: Масштабируем в 1280x720, сохраняя пропорции, остальное заливаем черным
            
            cmd = [
                "ffmpeg",
                "-i", cls.RAW_PATH,
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-profile:v", "main",
                "-level", "3.1",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac", 
                "-b:a", "128k",
                "-y",
                cls.PROCESSED_PATH
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await process.wait()
            
            if process.returncode == 0:
                logger.info("✅ FFmpeg conversion successful!")
                if os.path.exists(cls.RAW_PATH):
                    os.remove(cls.RAW_PATH)
            else:
                logger.error("❌ FFmpeg failed.")
        except Exception as e:
            logger.error(f"❌ FFmpeg execution error: {e}")

    @classmethod
    def get_file(cls):
        if cls._file_id:
            return cls._file_id
        
        if os.path.exists(cls.PROCESSED_PATH):
            return FSInputFile(cls.PROCESSED_PATH)
        
        return None

    @classmethod
    def set_file_id(cls, file_id: str):
        if file_id:
            cls._file_id = file_id
            logger.info(f"💾 Video cached in Telegram. File ID: {file_id[:20]}...")