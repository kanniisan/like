"""언어 콘텐츠 로컬 자동화: 음성/영상 -> 자막(원문+한국어) -> 단어장 -> 유튜브 메타 -> (선택) 자막 영상.

사용법:
  python langtube.py 입력파일_또는_폴더 [--lang ja] [--target 한국어] [--video] [--model qwen3:8b]
결과는 입력 옆의 output/<파일명>/ 에 저장된다.
"""
import argparse, json, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

MEDIA = {".wav", ".mp3", ".m4a", ".flac", ".mp4", ".mkv", ".mov", ".webm"}
OLLAMA = "http://localhost:11434/api/chat"


def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    hits = list(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    if hits:
        return str(hits[0])
    sys.exit("ffmpeg를 찾을 수 없습니다.")


def llm(model, prompt, as_json=False):
    body = {"model": model, "stream": False, "think": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.3}}
    if as_json:
        body["format"] = "json"
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        text = json.load(r)["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def add_cuda_dlls():
    import os, site
    for base in site.getsitepackages():
        for d in Path(base).glob("nvidia/*/bin"):
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]


def transcribe(path, lang):
    from faster_whisper import WhisperModel
    add_cuda_dlls()
    for name, dev, ct in (("large-v3", "cuda", "float16"), ("medium", "cpu", "int8")):
        try:
            model = WhisperModel(name, device=dev, compute_type=ct)
            segs, info = model.transcribe(str(path), language=lang, vad_filter=True)
            return [(s.start, s.end, s.text.strip()) for s in segs if s.text.strip()], info.language
        except Exception as e:
            print(f"  {name}/{dev} 실패({e}), 다음 방식 시도")
    sys.exit("음성 인식 실패")


BAD_TR = re.compile(r"[一-鿿぀-ヿ-�□]")


def translate(segs, target, model, batch=15):
    out = []
    for i in range(0, len(segs), batch):
        chunk = segs[i:i + batch]
        lines = {str(n): t for n, (_, _, t) in enumerate(chunk)}
        prompt = (f"다음 JSON의 각 문장을 자연스러운 {target}로 번역해라. 한글과 문장부호만 사용하고 한자·일본어·중국어 글자는 절대 섞지 마라. 같은 키를 유지한 JSON만 출력해라.\n"
                  + json.dumps(lines, ensure_ascii=False))
        try:
            res = json.loads(llm(model, prompt, as_json=True))
        except Exception:
            res = {}
        out += [str(res.get(str(n), "")) for n in range(len(chunk))]
    # 한자/가나가 섞였거나 원문과 같은 항목만 한 줄씩 재번역
    for i, ((_, _, src), tr) in enumerate(zip(segs, out)):
        if src.strip() and (not tr or tr == src or BAD_TR.search(tr)):
            for _ in range(3):
                fix = " ".join(_translate_once(src, target, model))
                if fix and fix != src and not BAD_TR.search(fix):
                    out[i] = fix
                    break
    return out


def _translate_once(src, target, model):
    prompt = (f"다음 문장을 자연스러운 {target} 한 문장으로 번역해라. 한글과 문장부호만 사용하고 "
              f"한자·일본어·중국어 글자는 절대 섞지 마라. 짧은 구어체/감탄사도 반드시 번역하고 원문을 그대로 남기지 마라. "
              f"예: だめだよ -> 안돼. 번역문만 출력해라.\n\n{src}")
    try:
        return [llm(model, prompt).splitlines()[0].strip()]
    except Exception:
        return [""]


def write_srt(path, segs, trans):
    with open(path, "w", encoding="utf-8") as f:
        for n, ((a, b, t), k) in enumerate(zip(segs, trans), 1):
            f.write(f"{n}\n{ts(a)} --> {ts(b)}\n{t}\n{k}\n\n")


def vocab(text, target, model):
    prompt = (f"다음 문장에서 학습자에게 유용한 핵심 단어/표현을 15개 골라라(문장에 실제로 나오는 것만). "
              f"각 항목: word=원문 표기, reading=히라가나 읽기, meaning={target}로 된 뜻(원문을 그대로 베끼지 마라), "
              f"example=그 단어가 나온 원문 문장.\n"
              f"반드시 이 형식의 JSON 객체 하나로만 출력: "
              f"{{\"words\": [{{\"word\": \"\", \"reading\": \"\", \"meaning\": \"\", \"example\": \"\"}}, ...]}}\n\n{text}")
    try:
        data = json.loads(llm(model, prompt, as_json=True))
        if isinstance(data, dict):
            data = data.get("words") or next((v for v in data.values() if isinstance(v, list)), [data])
        return [w for w in data if isinstance(w, dict) and w.get("word")]
    except Exception:
        return []


def meta(text, target, model):
    prompt = (f"아래 대본으로 언어 학습 유튜브 영상 메타데이터를 {target}로 만들어라. "
              "JSON만 출력: {\"titles\":[제목 후보 5개],\"description\":설명란 3~4문장,\"tags\":[태그 10개],"
              "\"chapters\":[{\"time\":\"MM:SS\",\"title\":챕터명}]}\n"
              "챕터는 아래 대본의 [MM:SS] 표시를 참고해 4~8개.\n\n" + text)
    try:
        return json.loads(llm(model, prompt, as_json=True))
    except Exception:
        return {}


def burn_video(ffmpeg, src, srt, dst):
    is_audio = src.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"}
    style = "FontName=Malgun Gothic,FontSize=22,Outline=2,MarginV=40"
    srt_f = str(srt).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{srt_f}':force_style='{style}'"
    if is_audio:
        cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x1e1e2e:s=1920x1080:r=25", "-i", str(src),
               "-vf", vf, "-shortest", "-c:v", "libx264", "-c:a", "aac", str(dst)]
    else:
        cmd = [ffmpeg, "-y", "-i", str(src), "-vf", vf, "-c:a", "copy", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)


def process(path, a):
    out = path.parent / "output" / path.stem
    out.mkdir(parents=True, exist_ok=True)
    print(f"[{path.name}] 음성 인식...")
    segs, lang = transcribe(path, a.lang)
    print(f"[{path.name}] 번역 ({len(segs)}문장)...")
    trans = translate(segs, a.target, a.model)
    write_srt(out / "bilingual.srt", segs, trans)
    script = "\n".join(f"[{int(s // 60):02}:{int(s % 60):02}] {t}" for s, _, t in segs)
    (out / "script.txt").write_text(script, encoding="utf-8")

    words = vocab(script, a.target, a.model)
    with open(out / "vocab.csv", "w", encoding="utf-8-sig") as f:
        f.write("word,reading,meaning,example\n")
        for w in words:
            f.write(",".join('"%s"' % str(w.get(k, "")).replace('"', "'") for k in ("word", "reading", "meaning", "example")) + "\n")

    m = meta(script, a.target, a.model)
    md = ["# 유튜브 메타데이터", "", "## 제목 후보"] + [f"- {t}" for t in m.get("titles", [])]
    md += ["", "## 설명", m.get("description", ""), "", "## 챕터"]
    md += [f"{c.get('time')} {c.get('title')}" for c in m.get("chapters", []) if isinstance(c, dict)]
    md += ["", "## 태그", ", ".join(m.get("tags", []))]
    (out / "youtube_meta.md").write_text("\n".join(md), encoding="utf-8")

    if a.video:
        print(f"[{path.name}] 자막 영상 렌더링...")
        burn_video(find_ffmpeg(), path, out / "bilingual.srt", out / "subtitled.mp4")
    print(f"[{path.name}] 완료 -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--lang", default="ja", help="원문 언어 코드 (ja, en, zh ...)")
    ap.add_argument("--target", default="한국어")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--video", action="store_true", help="자막 입힌 mp4 생성")
    a = ap.parse_args()
    p = Path(a.input).resolve()
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in MEDIA) if p.is_dir() else [p]
    for f in files:
        process(f, a)
