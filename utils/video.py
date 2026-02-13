import os
import logging
import asyncio
import aiohttp
from aiogram.types import FSInputFile

logger = logging.getLogger("VideoManager")

class VideoManager:
    # Ссылка на исходное видео
    SOURCE_URL = "https://github.com/Rewixx-png/rew-host-assets/raw/main/%D0%9D%D0%BE%D0%B2%D1%8B%D0%B9%20%D0%BF%D1%80%D0%BE%D0%B5%D0%BA%D1%82%20114%20%5B33803A3%5D.mp4"
    
    RAW_PATH = "storage/video_raw.mp4"
    # Файл с реальной интерполяцией кадров (плавный)
    PROCESSED_PATH = "storage/video_smooth_60fps.mp4"
    
    _file_id: str | None = None

    @classmethod
    async def prepare(cls):
        if not os.path.exists("storage"):
            os.makedirs("storage")

        if os.path.exists(cls.PROCESSED_PATH):
            logger.info("✅ Smooth Video found. Ready.")
            return

        # 1. Скачивание исходника
        if not os.path.exists(cls.RAW_PATH):
            logger.info("⬇️ Downloading raw video...")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(cls.SOURCE_URL) as resp:
                        if resp.status == 200:
                            with open(cls.RAW_PATH, 'wb') as f:
                                f.write(await resp.read())
                            logger.info("✅ Raw video downloaded.")
                        else:
                            logger.error(f"❌ Failed to download video: {resp.status}")
                            return
            except Exception as e:
                logger.error(f"❌ Download error: {e}")
                return

        # 2. Генерация плавности (Motion Interpolation)
        logger.info("🧬 Starting AI Motion Interpolation (Creating new frames)...")
        logger.info("⚠️ This process is CPU intensive and may take time!")
        
        try:
            # Используем фильтр minterpolate для создания ПРОМЕЖУТОЧНЫХ кадров.
            # mi_mode=mci (Motion Compensated Interpolation) - это и есть "сглаживание".
            # Ставим 60 FPS, так как 120 FPS интерполяция займет слишком много времени на CPU.
            # 60 FPS достаточно для идеально плавного эффекта.
            cmd = [
                "ffmpeg",
                "-i", cls.RAW_PATH,
                "-vf", "minterpolate=fps=120:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                "-c:v", "libx264",
                "-preset", "veryfast", # Быстрый пресет, чтобы не ждать вечность
                "-crf", "20",          # Высокое качество
                "-c:a", "copy",        # Аудио копируем без изменений
                "-y",
                cls.PROCESSED_PATH
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # Ждем завершения
            await process.wait()
            
            if process.returncode == 0:
                logger.info("✅ Motion Interpolation complete! Video is now REAL 60 FPS (Smooth).")
                if os.path.exists(cls.RAW_PATH):
                    os.remove(cls.RAW_PATH)
            else:
                logger.error("❌ FFmpeg interpolation failed.")
                
        except Exception as e:
            logger.error(f"❌ Render error: {e}")

    @classmethod
    def get_file(cls):
        if cls._file_id:
            return cls._file_id
        
        if os.path.exists(cls.PROCESSED_PATH):
            return FSInputFile(cls.PROCESSED_PATH)
        
        # Fallback
        if os.path.exists(cls.RAW_PATH):
            return FSInputFile(cls.RAW_PATH)
        
        return None

    @classmethod
    def set_file_id(cls, file_id: str):
        if file_id:
            cls._file_id = file_id
            logger.info(f"💾 Video cached in Telegram. File ID: {file_id[:20]}...")