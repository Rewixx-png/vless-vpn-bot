import io
import qrcode
from aiogram.types import BufferedInputFile

class QRGenerator:
    @staticmethod
    def generate(text: str) -> BufferedInputFile:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        return BufferedInputFile(bio.read(), filename="qr.png")