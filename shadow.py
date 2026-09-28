"""쉐도잉 영상 생성: 폴더의 음성 파일들 -> [듣기 화면 + 원음] -> [따라 말하기 화면 + 무음] 반복 -> 1편의 mp4.

사용법:
  python shadow.py 면접연습1 [--lang ja] [--limit 5] [--gap 1.3] [--repeat 1] [--out shadowing.mp4]
번역은 캐시(<폴더>/output/shadow_cache.json)에 저장되어 재실행 시 건너뛴다.
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

import langtube as lt

AUDIO = {".wav", ".mp3", ".m4a", ".flac"}  # 결과/원본 mp4가 섞여도 입력으로 잡지 않는다
W, H = 1920, 1080
FONTS = Path("C:/Windows/Fonts")
JP_FONT = next((str(FONTS / n) for n in ("YuGothB.ttc", "meiryob.ttc", "malgunbd.ttf") if (FONTS / n).exists()), None)
KR_FONT = str(FONTS / "malgun.ttf")
BG = {"listen": (30, 30, 46), "shadow": (20, 52, 44)}
LABEL = {"listen": ("듣기  LISTEN", (137, 180, 250)), "shadow": ("따라 말하기  SHADOWING", (250, 200, 100))}


import re
import pykakasi

_kks = pykakasi.kakasi()
_KANJI = re.compile(r"[一-鿿々]")
_KANA = re.compile(r"[぀-ヿー]")
BREAK_AFTER = "、。！？!?,."


def tokenize(text):
    """[(표기, 후리가나 or None)]. 送り仮名(뒤쪽 가나)는 후리가나에서 제외."""
    out = []
    for r in _kks.convert(text):
        o, h = r["orig"], r["hira"]
        if not _KANJI.search(o):
            out.append((o, None))
            continue
        stem, reading = o, h
        while len(stem) > 1 and len(reading) > 1 and _KANA.fullmatch(stem[-1]) and stem[-1] == reading[-1]:
            stem, reading = stem[:-1], reading[:-1]
        out.append((stem, reading))
        if stem != o:
            out.append((o[len(stem):], None))
    return out


PARTICLES = "はがをにでとものへや"


def phrases(tokens):
    """줄바꿈 가능 단위(구)로 묶는다: 문장부호 뒤, 조사(1~2자 가나) 뒤에서만 끊는다."""
    out, cur = [], []
    for t in tokens:
        cur.append(t)
        s = t[0]
        if s[-1] in BREAK_AFTER or (t[1] is None and len(s) <= 2 and s[-1] in PARTICLES and _KANA.fullmatch(s[0])):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def wrap_tokens(draw, tokens, font, ruby_font, max_w):
    """구 단위 줄바꿈 + 줄 길이 균형. 구 하나가 너무 길면 토큰 단위로 나눈다."""
    def w(tok):
        base = draw.textlength(tok[0], font=font)
        return max(base, draw.textlength(tok[1], font=ruby_font)) if tok[1] else base

    def greedy(units, limit):
        lines, cur, cur_w = [], [], 0
        for u in units:
            uw = sum(w(t) for t in u)
            if cur and cur_w + uw > limit:
                lines.append(cur)
                cur, cur_w = [], 0
            cur += u
            cur_w += uw
        return lines + [cur] if cur else lines

    units = []
    for p in phrases(tokens):
        if sum(w(t) for t in p) > max_w:
            units += [[t] for t in p]
        else:
            units.append(p)
    n = len(greedy(units, max_w))
    lo, hi = 0, max_w
    while hi - lo > 8:  # 같은 줄 수를 유지하는 최소 폭 -> 균형 잡힌 줄
        mid = (lo + hi) / 2
        if len(greedy(units, mid)) <= n:
            hi = mid
        else:
            lo = mid
    return greedy(units, hi)


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split(" "):
        cand = (cur + " " + word).strip()
        if draw.textlength(cand, font=font) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    return lines + [cur] if cur else lines


def render_frame(path, mode, idx, total, src, tr):
    img = Image.new("RGB", (W, H), BG[mode])
    d = ImageDraw.Draw(img)
    label, color = LABEL[mode]
    d.text((80, 60), label, font=ImageFont.truetype(KR_FONT, 56), fill=color)
    d.text((W - 80, 60), f"{idx} / {total}", font=ImageFont.truetype(KR_FONT, 48), fill=(160, 160, 180), anchor="ra")

    f_src = ImageFont.truetype(JP_FONT, 84)
    f_ruby = ImageFont.truetype(JP_FONT, 38)
    f_tr = ImageFont.truetype(KR_FONT, 56)
    src_lines = wrap_tokens(d, tokenize(src), f_src, f_ruby, W - 240)
    tr_lines = wrap(d, tr, f_tr, W - 240)
    line_h = 84 + 44 + 30
    block = len(src_lines) * line_h + 40 + len(tr_lines) * 76
    y = (H - block) // 2 + 20
    for line in src_lines:
        widths = [max(d.textlength(t, font=f_src), d.textlength(r, font=f_ruby) if r else 0) for t, r in line]
        x = (W - sum(widths)) / 2
        for (t, r), tw in zip(line, widths):
            d.text((x + tw / 2, y + 44), t, font=f_src, fill=(255, 255, 255), anchor="ma")
            if r:
                d.text((x + tw / 2, y), r, font=f_ruby, fill=(250, 200, 100), anchor="ma")
            x += tw
        y += line_h
    y += 40
    for ln in tr_lines:
        d.text((W // 2, y), ln, font=f_tr, fill=(190, 190, 210), anchor="ma")
        y += 76
    img.save(path)


def probe_duration(ffmpeg, f):
    r = subprocess.run([ffmpeg, "-i", str(f)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def make_segment(ffmpeg, png, out, dur, audio=None):
    cmd = [ffmpeg, "-y", "-loop", "1", "-framerate", "25", "-i", str(png)]
    if audio:
        cmd += ["-i", str(audio)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-t", f"{dur:.2f}", "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
            "-ar", "44100", "-ac", "2", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--target", default="한국어")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--limit", type=int, default=0, help="앞에서부터 N개만 (테스트용)")
    ap.add_argument("--start", type=int, default=0, help="앞에서 N개 건너뜀")
    ap.add_argument("--gap", type=float, default=1.3, help="따라 말하기 시간 = 원음 길이 x gap + 0.5초")
    ap.add_argument("--repeat", type=int, default=1, help="따라 말하기 반복 횟수")
    ap.add_argument("--out", default="shadowing.mp4")
    a = ap.parse_args()

    folder = Path(a.folder).resolve()
    files = sorted(f for f in folder.iterdir() if f.suffix.lower() in AUDIO)
    files = files[a.start:]
    if a.limit:
        files = files[:a.limit]
    ffmpeg = lt.find_ffmpeg()
    outdir = folder / "output"
    outdir.mkdir(exist_ok=True)
    cache_p = outdir / "shadow_cache.json"
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}

    for f in files:
        if f.name in cache:
            continue
        print(f"인식/번역: {f.name}")
        segs, _ = lt.transcribe(f, a.lang)
        src = " ".join(t for _, _, t in segs)
        tr = ""
        for _ in range(4):  # 한자/깨진 글자가 섞이면 재시도
            tr = " ".join(lt.translate([(0, 0, src)], a.target, a.model))
            if tr and not re.search(r"[一-鿿぀-ヿ-�□]", tr):
                break
        cache[f.name] = {"src": src, "tr": tr}
        cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    tmp = Path(tempfile.mkdtemp(prefix="shadow_"))
    parts = []
    for i, f in enumerate(files, 1):
        c = cache[f.name]
        dur = probe_duration(ffmpeg, f)
        if c.get("dur") != dur:
            c["dur"] = dur
            cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"렌더 {i}/{len(files)}: {c['src'][:30]}")
        p1, p2 = tmp / f"{i}_l.png", tmp / f"{i}_s.png"
        render_frame(p1, "listen", i, len(files), c["src"], c["tr"])
        render_frame(p2, "shadow", i, len(files), c["src"], c["tr"])
        s1 = tmp / f"{i}_a.mp4"
        make_segment(ffmpeg, p1, s1, dur + 0.4, audio=f)
        parts.append(s1)
        for r in range(a.repeat):
            s2 = tmp / f"{i}_b{r}.mp4"
            make_segment(ffmpeg, p2, s2, dur * a.gap + 0.5)
            parts.append(s2)

    lst = tmp / "list.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    out = folder / a.out
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                   check=True, capture_output=True)
    print(f"완료 -> {out}")


if __name__ == "__main__":
    main()
