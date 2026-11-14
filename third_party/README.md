# third_party

외부 코드를 참고용으로 두는 폴더입니다. 이 README 를 뺀 나머지는 git 에 올리지 않습니다 (`.gitignore`).
실험은 이 폴더가 없어도 돌아갑니다. 공식 코드와 대조해 볼 때만 필요합니다.

## TSRBench 공식 코드

```bash
git clone https://github.com/tianyi-lab/TSRBench.git third_party/TSRBench
git -C third_party/TSRBench checkout 084e3f0060eaf1d6882542110e2305c23b9c6816
```

`ts2img/benchmarks/tsrbench/` 와 `ts2img/charts/_render.py` 는 위 commit 을 기준으로 재현했습니다.
다르게 동작하는 부분은 `ts2img/benchmarks/tsrbench/CHANGES.md` 에 있습니다.

주의

- 공식 코드를 직접 고치지 않습니다. 바꿀 것이 있으면 `ts2img/` 쪽에 구현하고 CHANGES.md 에 적습니다.
- 공식 저장소의 일부 파일에는 주석 처리된 API key 문자열이 남아 있습니다. 우리 것이 아니니 쓰지 말고, 이 폴더를 git 에 올리지 마세요.
- 공식 `download_data.py` 가 가리키는 데이터 저장소(`ParadiseYu/TSRBench`)는 접근할 수 없습니다. 데이터는 `python -m ts2img download` 로 받습니다 (`umd-zhou-lab/TSRBench`).
