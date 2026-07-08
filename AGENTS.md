# Codex 작업 지침

이 저장소의 기준 문서는 `CLAUDE.md`입니다. Codex로 작업할 때는 먼저 이 파일을 확인한 뒤, `CLAUDE.md` 전체를 읽고 그 내용을 그대로 따릅니다.

## 핵심 규칙

1. 작업 시작 전 `git fetch origin`과 `git status --short --branch`로 원격 `main`과 로컬 상태를 확인합니다.
2. 로컬 `main`이 뒤처져 있으면 코드 수정 전에 `git merge --ff-only origin/main` 등 fast-forward 방식으로 맞춥니다.
3. 기능 수정은 `codex/<topic>` 브랜치에서 진행하고, `data.json`/`crawl_log.txt` 자동 갱신분을 코드 변경과 우발적으로 섞지 않습니다.
4. `main` push는 Cloudflare Pages 배포를 유발하므로, 사용자가 명시적으로 요청했거나 배포 의도가 분명할 때만 수행합니다.
5. 작업 종료 시 변경 파일, 검증 결과, 배포 여부를 간단히 남겨 Claude Code가 이어받을 수 있게 합니다.
