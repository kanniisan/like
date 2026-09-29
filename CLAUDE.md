# like — 언어 콘텐츠 유튜브 자동화 시스템

API 키 없이 로컬에서만 동작하는 자동화. 음성 폴더를 넣으면 쉐도잉 영상(일본어 원문 + 후리가나 + 한국어 번역), 썸네일, 제목 후보/설명/챕터, 단어장까지 만든다.

## 구성
- `auto.py` — 진입점. 폴더의 음성을 N개씩 묶어 편별로 `shadow.py`를 실행하고 `epNN.md`(설명/챕터/스크립트)를 쓴다. 편마다 `epNN.json`(포함 파일/옵션)을 저장해, 구성이 바뀐 편만 다시 만들고 나머지는 건너뜀. `--watch` 지원.
- `shadow.py` — 쉐도잉 영상 생성. 음성 인식 -> 번역 -> Pillow로 프레임 렌더 -> ffmpeg로 이어붙임. 인식/번역 결과와 음성 길이를 `<폴더>/output/shadow_cache.json`에 캐시.
- `extras.py` — 편별 유튜브 제목 후보(대본 내용만 근거)와 단어장 CSV 생성. `auto.py`가 `epNN_vocab.csv`로 저장.
- `thumb.py` — 편별 썸네일(1280x720) 생성. `auto.py`가 `epNN.png`로 저장.
- `correct.py` — 인식/번역 오류 교정. `<폴더>/glossary.json`(확정 치환) + 파일명 제목을 힌트로 한 LLM 교정. `shadow.py`가 새 항목에 자동 적용. 기존 캐시 재점검: `python correct.py 폴더` (바뀐 편은 삭제되므로 `auto.py`로 재생성).
- `langtube.py` — 공용 함수(Whisper 인식, Ollama 번역, ffmpeg 탐색) + 단독 실행용 자막/단어장/메타 생성기.

## 실행
더블클릭용: 음성 폴더를 `run.bat`(1회 실행, 마무리 포함)이나 `watch.bat`(폴더 감시)에 드래그.
```
python auto.py 면접연습1                # 10문장씩 편 생성
python auto.py 면접연습1 --watch        # 폴더 감시
python auto.py 면접연습1 --final        # 마무리: 자투리(batch/2 미만)는 앞 편에 합침
python shadow.py 면접연습1 --start 0 --limit 10 --out x.mp4
```

## 환경 (Windows 11)
- Python 3.12, `faster-whisper`, `pillow`, `pykakasi`, `watchdog`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (GPU 인식용)
- ffmpeg (winget `Gyan.FFmpeg`). PATH에 없을 수 있어 `find_ffmpeg()`가 WinGet 폴더를 직접 찾는다.
- Ollama(`localhost:11434`) + `qwen3:8b`. RTX 3060 12GB.

## 주의할 점
- 한글 Windows라 subprocess 출력은 `encoding="utf-8"`을 명시하고, 터미널에서는 `PYTHONIOENCODING=utf-8`을 쓴다.
- 입력은 오디오(wav/mp3/m4a/flac)만 대상이다. 같은 폴더의 mp4는 입력으로 잡지 않는다.
- 번역 LLM이 한자/일본어를 섞거나 유치원을 어린이집으로 옮기는 등 오류가 있다. 결과는 `shadow_cache.json`을 직접 고치면 반영된다 (재렌더 시 인식/번역 단계는 건너뜀).
- Whisper 인식 오류(예: 前職 -> 全職, エピソード -> エクソード)는 LLM이 다 못 잡는다. 반복되는 오류는 `glossary.json`에 추가하고, 업로드 전 검수한다.
- 후리가나는 `pykakasi` 사전 기반이라 다음자(多音字)/고유명사는 틀릴 수 있다.
- 미디어 파일과 생성 결과(`면접연습1/`, `episodes/`, `output/`)는 git에서 제외한다. 커밋하지 않는다.

## 미구현
유튜브 업로드(의도적으로 제외).
