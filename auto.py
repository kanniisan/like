"""언어 쉐도잉 영상 자동화 시스템 (진입점).

  python auto.py 면접연습1                 # 폴더의 음성을 10개씩 묶어 편별 영상 + 메타 생성 (있는 편은 건너뜀)
  python auto.py 면접연습1 --watch         # 폴더를 감시하다가 새 음성이 채워지면 자동 실행
  python auto.py 면접연습1 --batch 8 --title "일본어 면접 쉐도잉" --repeat 2

결과: <폴더>/episodes/ep01.mp4, ep01.md (제목 후보 없이 목차/설명/챕터), ...
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

from langtube import find_ffmpeg
from shadow import probe_duration
from thumb import make_thumb

HERE = Path(__file__).parent
AUDIO = {".wav", ".mp3", ".m4a", ".flac"}


def audio_files(folder):
    return sorted(f for f in folder.iterdir() if f.suffix.lower() in AUDIO)


def fmt(sec):
    return f"{int(sec // 60):02}:{int(sec % 60):02}"


def write_meta(folder, ep, files, a, cache, gap_sec):
    """편별 설명란/챕터. 챕터 시간은 실제 영상 구성(듣기+따라말하기)으로 계산한다."""
    lines = [f"# {a.title} {ep:02}", "", "## 설명",
             f"{a.title} {ep:02}편입니다. 원음을 듣고, 이어지는 빈 구간에 따라 말해 보세요. "
             "일본어 원문(후리가나)과 한국어 번역이 함께 나옵니다.", "", "## 챕터"]
    t = 0.0
    for i, f in enumerate(files, 1):
        c = cache.get(f.name, {})
        dur = c.get("dur") or probe_duration(find_ffmpeg(), f)
        lines.append(f"{fmt(t)} {i}. {c.get('src', f.stem)[:40]}")
        t += (dur + 0.4) + a.repeat * (dur * a.gap + 0.5)
    lines += ["", "## 스크립트"]
    for i, f in enumerate(files, 1):
        c = cache.get(f.name, {})
        lines += [f"{i}. {c.get('src', '')}", f"   {c.get('tr', '')}"]
    (folder / "episodes" / f"ep{ep:02}.md").write_text("\n".join(lines), encoding="utf-8")


def split_episodes(files, a):
    """[(시작 인덱스, 파일목록)]. --final이면 batch/2 미만의 자투리를 앞 편에 합친다."""
    chunks = [(n, files[n:n + a.batch]) for n in range(0, len(files), a.batch)]
    if a.final and len(chunks) > 1 and len(chunks[-1][1]) < a.batch / 2:
        n, tail = chunks.pop()
        chunks[-1] = (chunks[-1][0], chunks[-1][1] + tail)
    return chunks


def run_once(folder, a):
    files = audio_files(folder)
    (folder / "episodes").mkdir(exist_ok=True)
    cache_p = folder / "output" / "shadow_cache.json"
    made = 0
    for ep, (n, chunk) in enumerate(split_episodes(files, a), 1):
        out = folder / "episodes" / f"ep{ep:02}.mp4"
        if len(chunk) < a.batch and not a.final:
            print(f"ep{ep:02}: {len(chunk)}개뿐이라 대기 (--final 로 앞 편에 합쳐 마무리)")
            continue
        meta = folder / "episodes" / f"ep{ep:02}.md"
        png = folder / "episodes" / f"ep{ep:02}.png"
        manifest = folder / "episodes" / f"ep{ep:02}.json"
        want = {"files": [f.name for f in chunk], "gap": a.gap, "repeat": a.repeat}
        if out.exists() and not manifest.exists() and len(chunk) == a.batch:
            manifest.write_text(json.dumps(want, ensure_ascii=False), encoding="utf-8")  # 구버전 결과 인수
        have = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None
        if have != want:  # 구성/옵션이 달라졌으면 그 편만 다시 만든다
            for f in (folder / "episodes").glob(f"ep{ep:02}.*"):
                f.unlink()
        if out.exists() and meta.exists() and png.exists():
            continue
        if not out.exists():
            print(f"ep{ep:02}: {len(chunk)}개 처리")
            subprocess.run([sys.executable, str(HERE / "shadow.py"), str(folder), "--start", str(n),
                            "--limit", str(len(chunk)), "--gap", str(a.gap), "--repeat", str(a.repeat),
                            "--lang", a.lang, "--out", f"episodes/ep{ep:02}.mp4"], check=True)
        manifest.write_text(json.dumps(want, ensure_ascii=False), encoding="utf-8")
        cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
        write_meta(folder, ep, chunk, a, cache, 0)
        first = cache.get(chunk[0].name, {})
        make_thumb(png, a.title, ep, first.get("src", ""), first.get("tr", ""))
        made += 1
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--batch", type=int, default=10, help="한 편에 넣을 문장 수")
    ap.add_argument("--title", default="일본어 쉐도잉")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--gap", type=float, default=1.3)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--final", action="store_true", help="마무리: 자투리(batch/2 미만)는 앞 편에 합치고, 나머지 묶음도 생성")
    ap.add_argument("--watch", action="store_true", help="폴더 감시 모드")
    a = ap.parse_args()
    folder = Path(a.folder).resolve()
    if not a.watch:
        run_once(folder, a)
        return
    print(f"감시 시작: {folder} (Ctrl+C 종료)")
    seen = -1
    while True:
        n = len(audio_files(folder))
        if n != seen:
            seen = n
            run_once(folder, a)
        time.sleep(30)


if __name__ == "__main__":
    main()
