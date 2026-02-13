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
    Преобразует видео в 16:9 (1280x720) с добавлением черных полос (padding),
    чтобы оно корректно отображалось в Link Preview Telegram.
    """
    if not check_ffmpeg():
        print("❌ FFmpeg не установлен! Установите его: sudo apt install ffmpeg (или скачайте для Windows)")
        return

    print(f"🔄 Обработка видео: {input_path} -> {output_path}")
    
    # Команда FFmpeg:
    # -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
    # Это масштабирует видео, чтобы оно вписалось в 1280x720, и добавляет черные полосы по краям.
    
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "23",
        "-c:a", "copy",
        "-y", # Перезаписать output если есть
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ Готово! Теперь видео имеет соотношение 16:9.")
        print("📤 Загрузите новый файл на GitHub и обновите ссылку в коде.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при конвертации: {e}")

if __name__ == "__main__":
    # Пример использования:
    # python3 utils/ffmpeg_fix.py video.mp4 video_fixed.mp4
    
    if len(sys.argv) < 3:
        print("Использование: python3 utils/ffmpeg_fix.py <входной_файл> <выходной_файл>")
    else:
        fix_video_aspect_ratio(sys.argv[1], sys.argv[2])