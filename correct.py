"""음성 인식/번역 오류 교정.

1) 용어집 <폴더>/glossary.json  {"src": {"全職": "前職"}, "tr": {"어린이집": "유치원"}}  -> 확정 치환
2) LLM 교정: 파일명의 제목(한국어/영어)을 힌트로 동음이의 오인식만 수정. 원문과 너무 달라지면 버린다.

shadow.py가 새 항목을 캐시에 넣을 때 자동 적용된다. 이미 만든 캐시를 다시 점검하려면:
  python correct.py 면접연습1 [--batch 10] [--no-llm]
바뀐 문장이 속한 편(episodes/epNN.*)은 삭제되어 다음 auto.py 실행 때 다시 만들어진다.
"""
import argparse, difflib, json, re, unicodedata
from pathlib import Path

import langtube as lt

DEFAULT_GLOSSARY = {"src": {"全職": "前職", "エクソード": "エピソード"}, "tr": {"어린이집": "유치원"}}
BAD_TR = re.compile(r"[一-鿿぀-ヿ-�□]")


def load_glossary(folder):
    p = Path(folder) / "glossary.json"
    if not p.exists():
        p.write_text(json.dumps(DEFAULT_GLOSSARY, ensure_ascii=False, indent=1), encoding="utf-8")
    g = json.loads(p.read_text(encoding="utf-8"))
    return g.get("src", {}), g.get("tr", {})


def hints_from_name(name):
    """'001_話者_한국어 제목_English title.wav' -> (한국어 제목, 영어 제목)"""
    parts = Path(name).stem.split("_")
    return (parts[2] if len(parts) > 2 else ""), (parts[3] if len(parts) > 3 else "")


def apply_glossary(text, table):
    for bad, good in table.items():
        text = text.replace(bad, good)
    return text


def llm_fix_src(src, name, model):
    ko, en = hints_from_name(name)
    if not (ko or en):
        return src
    prompt = ("다음은 일본어 음성 인식 결과다. 주제 힌트: "
              f"'{ko}' / '{en}'.\n"
              "동음이의어 등 명백한 오인식(예: 前職을 全職으로)만 고쳐라. 말투, 어순, 표현은 절대 바꾸지 마라. "
              "고칠 게 없으면 그대로 출력. 수정된 일본어 문장 한 줄만 출력.\n\n" + src)
    try:
        out = lt.llm(model, prompt).splitlines()[0].strip()
    except Exception:
        return src
    if unicodedata.normalize("NFKC", out) == unicodedata.normalize("NFKC", src):
        return src  # 전각/반각 부호만 다른 경우는 수정으로 보지 않는다
    ok = out and 0.85 <= difflib.SequenceMatcher(None, src, out).ratio() and abs(len(out) - len(src)) <= 3
    return out if ok else src


def correct_entry(name, src, tr, folder, model, use_llm=True, retranslate=None):
    """(src, tr, 바뀌었는지) 반환. 원문이 바뀌면 retranslate(src)로 번역을 다시 만든다."""
    g_src, g_tr = load_glossary(folder)
    new_src = apply_glossary(src, g_src)
    if use_llm:
        new_src = llm_fix_src(new_src, name, model)
    new_tr = tr
    if new_src != src and retranslate:
        new_tr = retranslate(new_src)
    new_tr = apply_glossary(new_tr, g_tr)
    return new_src, new_tr, (new_src, new_tr) != (src, tr)


def retranslate_factory(target, model):
    def f(src):
        tr = ""
        for _ in range(4):
            tr = " ".join(lt.translate([(0, 0, src)], target, model))
            if tr and not BAD_TR.search(tr):
                break
        return tr
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--target", default="한국어")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    folder = Path(a.folder).resolve()
    cache_p = folder / "output" / "shadow_cache.json"
    cache = json.loads(cache_p.read_text(encoding="utf-8"))
    audio = sorted(f.name for f in folder.iterdir() if f.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"})
    retr = retranslate_factory(a.target, a.model)
    changed_eps = set()
    for i, name in enumerate(audio):
        c = cache.get(name)
        if not c:
            continue
        src, tr, changed = correct_entry(name, c["src"], c["tr"], folder, a.model, not a.no_llm, retr)
        if changed:
            print(f"[{i // a.batch + 1}편 {i + 1}번]\n  원문 {c['src']}\n   -> {src}\n  번역 {c['tr']}\n   -> {tr}")
            c["src"], c["tr"] = src, tr
            changed_eps.add(i // a.batch + 1)
    cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    for ep in sorted(changed_eps):
        for f in (folder / "episodes").glob(f"ep{ep:02}.*"):
            f.unlink()
    print(f"교정된 편(삭제, 재생성 필요): {sorted(changed_eps) or '없음'}")


if __name__ == "__main__":
    main()
