"""편별 썸네일(1280x720) 자동 생성. 제목 + 편 번호 + 대표 문장(일본어/한국어)."""
from PIL import Image, ImageDraw, ImageFont

from shadow import JP_FONT, KR_FONT, wrap

W, H = 1280, 720
PALETTES = [((30, 30, 46), (137, 180, 250)), ((20, 52, 44), (250, 200, 100)),
            ((52, 30, 46), (245, 160, 190)), ((40, 40, 20), (180, 230, 120))]


def make_thumb(path, title, ep, src, tr):
    bg, accent = PALETTES[(ep - 1) % len(PALETTES)]
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 24, H], fill=accent)

    d.text((80, 70), f"EP.{ep:02}", font=ImageFont.truetype(JP_FONT, 120), fill=accent)
    f_title = ImageFont.truetype(KR_FONT, 64)
    y = 230
    for ln in wrap(d, title, f_title, W - 160):
        d.text((80, y), ln, font=f_title, fill=(255, 255, 255))
        y += 80

    f_src = ImageFont.truetype(JP_FONT, 44)
    y = 470
    for ln in wrap_chars(d, src, f_src, W - 160)[:2]:
        d.text((80, y), ln, font=f_src, fill=(235, 235, 245))
        y += 60
    d.text((80, y + 10), tr[:28] + ("…" if len(tr) > 28 else ""), font=ImageFont.truetype(KR_FONT, 36), fill=(170, 170, 190))
    img.save(path)


def wrap_chars(draw, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + [cur] if cur else lines
