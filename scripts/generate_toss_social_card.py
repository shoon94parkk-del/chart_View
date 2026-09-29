"""Generate the stable 1200x630 Chart View Toss share preview."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "static" / "social-card-toss.png"
FONT = Path("C:/Windows/Fonts/malgun.ttf")
BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")


def font(size, bold=False):
    path = BOLD if bold else FONT
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def main():
    image = Image.new("RGB", (1200, 630), "#f8fbff")
    draw = ImageDraw.Draw(image)
    for y in range(630):
        amount = y / 629
        draw.line((0, y, 1199, y), fill=(int(248 - 8 * amount), int(251 - 10 * amount), 255))
    draw.rounded_rectangle((64, 60, 1136, 570), radius=48, fill="#ffffff", outline="#e5edf9", width=2)
    draw.rounded_rectangle((112, 108, 198, 194), radius=22, fill="#3182f6")
    draw.line([(132, 165), (149, 148), (163, 156), (182, 130)], fill="white", width=8, joint="curve")
    draw.text((220, 116), "차트뷰", font=font(52, True), fill="#191f28")
    draw.text((112, 248), "종목을 더 분명하게", font=font(56, True), fill="#191f28")
    draw.text((112, 333), "차트 · 현재가 · 기업 정보를 한눈에", font=font(32), fill="#4e5968")
    draw.rounded_rectangle((112, 445, 355, 507), radius=31, fill="#e8f3ff")
    draw.text((147, 459), "차트뷰에서 보기", font=font(23, True), fill="#1769c2")
    draw.line([(775, 429), (835, 396), (885, 407), (936, 352), (997, 368), (1080, 284)], fill="#3182f6", width=9, joint="curve")
    draw.line([(775, 461), (842, 473), (888, 448), (940, 463), (996, 416), (1080, 428)], fill="#9fc4fb", width=6, joint="curve")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, optimize=True)


if __name__ == "__main__":
    main()
