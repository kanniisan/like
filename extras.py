"""편별 제목 후보 + 단어장. 대본(원문/번역)에 있는 내용만 근거로 쓰게 제한한다."""
import json, re

import langtube as lt

BAD = re.compile(r"[一-鿿぀-ヿ-�□]")


def make_titles(series, ep, trs, model):
    """제목 후보 5개. 실패하면 템플릿으로 대체."""
    fallback = [f"{series} {ep:02}편 | 듣고 따라 말하기", f"[{series}] EP.{ep:02} 쉐도잉 연습",
                f"{series} {ep:02} | 실전 문장 {len(trs)}개"]
    sample = "\n".join(f"- {t}" for t in trs)
    prompt = ("아래는 일본어 쉐도잉 영상에 나오는 문장들의 한국어 번역이다.\n" + sample +
              f"\n\n이 영상의 유튜브 제목 후보 5개를 한국어로 만들어라. 규칙:\n"
              f"- 위 문장들에 실제로 나오는 주제(예: 지원동기, 경력, 수료 후 계획)만 사용하고 없는 내용은 지어내지 마라.\n"
              f"- 시리즈명 '{series}'를 포함하고, 40자 이내.\n"
              "- 한글, 숫자, 기본 문장부호만 사용(한자/일본어 금지).\n"
              'JSON만 출력: {"titles": ["...", "..."]}')
    try:
        titles = json.loads(lt.llm(model, prompt, as_json=True)).get("titles", [])
    except Exception:
        titles = []
    good = [t for t in titles if isinstance(t, str) and 0 < len(t) <= 45 and not BAD.search(t)]
    return (good + fallback)[:5]


def write_vocab(path, srcs, target, model):
    words = lt.vocab("\n".join(srcs), target, model)
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("word,reading,meaning,example\n")
        for w in words:
            f.write(",".join('"%s"' % str(w.get(k, "")).replace('"', "'")
                             for k in ("word", "reading", "meaning", "example")) + "\n")
    return len(words)
