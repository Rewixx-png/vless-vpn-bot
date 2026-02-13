import subprocess
import sys
import os

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

def fix_video_aspect_ratio(input_path: str, output_path: str):
    """
    Преобразует видео в 16:9 (1280x720) с заполнением экрана (CROP).
    Включает фиксы для Telegram: yuv420p, movflags faststart.
    """
    if not check_ffmpeg():
        print("❌ FFmpeg не установлен! Установите его: sudo apt install ffmpeg (или скачайте для Windows)")
        return

    print(f"🔄 Обработка видео: {input_path} -> {output_path}")
    
    # Используем scale=...:increase + crop для заполнения экрана без черных полос
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level", "3.1",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-preset", "slow",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ Готово! Видео оптимизировано для Telegram (16:9 Full Screen, H.264 Main 3.1).")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при конвертации: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python3 utils/ffmpeg_fix.py <входной_файл> <выходной_файл>")
    else:
        fix_video_aspect_ratio(sys.argv[1], sys.argv[2])