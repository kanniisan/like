# like — 언어 콘텐츠 유튜브 자동화 시스템

API 키 없이 로컬에서만 동작하는 자동화. 음성 폴더를 넣으면 쉐도잉 영상(일본어 원문 + 후리가나 + 한국어 번역)과 유튜브용 메타를 만든다.

## 구성
- `auto.py` — 진입점. 폴더의 음성을 N개씩 묶어 편별로 `shadow.py`를 실행하고 `epNN.md`(설명/챕터/스크립트)를 쓴다. 이미 만든 편은 건너뜀. `--watch` 지원.
- `shadow.py` — 쉐도잉 영상 생성. 음성 인식 -> 번역 -> Pillow로 프레임 렌더 -> ffmpeg로 이어붙임. 인식/번역 결과와 음성 길이를 `<폴더>/output/shadow_cache.json`에 캐시.
- `langtube.py` — 공용 함수(Whisper 인식, Ollama 번역, ffmpeg 탐색) + 단독 실행용 자막/단어장/메타 생성기.

## 실행
```
python auto.py 면접연습1                # 10문장씩 편 생성
python auto.py 면접연습1 --watch        # 폴더 감시
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
- Whisper 인식 오류(예: 前職 -> 全職)가 있으므로 업로드 전 검수가 필요하다.
- 후리가나는 `pykakasi` 사전 기반이라 다음자(多音字)/고유명사는 틀릴 수 있다.
- 미디어 파일과 생성 결과(`면접연습1/`, `episodes/`, `output/`)는 git에서 제외한다. 커밋하지 않는다.

## 미구현
썸네일 자동 생성, 인식 오류 자동 교정, 유튜브 업로드(의도적으로 제외).
