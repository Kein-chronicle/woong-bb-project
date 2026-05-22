# Automation Worker Design

## Recommendation
현재 기본 구조에서는 `Codex cron dispatcher`가 가장 안정적이다.

별도 Python sidecar worker는 계속 떠 있어야 하는 고빈도/실시간 감지가 필요할 때만 보조로 켠다.

## Why This Is Best
- 이미 운영 도구가 Python 기반이다.
- 상태 파일이 전부 JSON/JSONL이라 Python이 다루기 쉽다.
- Codex 자동화가 주기 실행과 실패 보고를 맡으면 long-running worker lock/heartbeat 꼬임이 줄어든다.
- 고정 시각 타이머는 한 번 실행하고 끝나는 원샷 작업이라 cron dispatcher와 잘 맞는다.
- Telegram 브리지와 자동 타이머 처리를 분리하면 대화 응답과 자동 이벤트가 서로 덜 꼬인다.

## Recommended Shape
- 이름: `woong-bb-automation-worker`
- 기본 실행기: `/Users/kein/Desktop/woong-bb/tools/run_due_codex_timers.py`
- 원샷 타이머 실행기: `/Users/kein/Desktop/woong-bb/tools/run_timer_once.py`
- 역할:
  - 시간대 전환 감지
  - 날씨/미디어 조회 갱신
  - share priority 재계산
  - 선톡 후보 생성
  - 이미지/링크 공유 후보 계산
  - 실제 발송 가능 여부 판정

## Supervision Dependency
- 기본 타이머는 Codex automation `woong-bb-codex-timer-dispatcher`가 처리한다.
- sidecar worker를 켜는 경우에는 단독으로만 두지 않고 supervisor/control layer와 함께 운영한다.
- 관련 문서: `/Users/kein/Desktop/woong-bb/profile/automation_supervision_design_ko.md`
- 관련 상태 파일:
  - `/Users/kein/Desktop/woong-bb/state/automation_supervisor_state.json`
  - `/Users/kein/Desktop/woong-bb/state/automation_control.json`
  - `/Users/kein/Desktop/woong-bb/state/automation_health.json`

## Activation Gate
- 연결과 구현은 먼저 끝내도 된다.
- 실제 sidecar worker 시작은 마스터의 명시적 지시 전까지 금지한다.
- 준비가 끝나면 자동으로 시작하지 않고, `실행 가능 상태`와 확인 항목을 보고한 뒤 시작 여부를 묻는다.
- 기본 상태는 `disabled/stopped`로 유지한다.

## Process Model
- 기본: Codex cron이 1시간마다 dispatcher를 실행하고, 그 사이 due 된 고정 시각 타이머를 idempotent하게 처리한다.
- 보조: sidecar worker는 실시간 미답장 감지, 5분 단위 대화 guard, 즉시성 높은 이벤트 약속 처리에만 사용한다.

## Avoid
- 모든 작업을 sidecar worker 하나에 몰아넣기
  - long-running process, lock, heartbeat, 로그 경로가 꼬이기 쉽다
- 브리지 내부에 직접 섞기
  - 대화 처리와 자동화가 강하게 결합돼 장애 추적이 어려워진다

## Runtime Loop
1. 현재 mode 확인
2. `setting`이면 대부분 skip
3. 상태 파일 로드
4. 재계산 필요 여부 판정
5. 필요 시 점수/상황/외형/미디어 상태 갱신
6. 발송 후보 있으면 guard 확인
7. 전송 실행
8. 상태/로그 기록
9. sleep

## Reliability Rules
- 파일 lock 사용
- 같은 이벤트 중복 발송 방지용 idempotency key 유지
- 마지막 성공 실행 시각 기록
- 실패해도 다음 루프에서 복구 가능해야 함
- heartbeat 기반 health 상태 갱신
- generation token으로 구버전 worker 자기중단

## Ops Recommendation
- 1순위: `launchd`로 macOS 백그라운드 관리
- 2순위: 기존 botctl 스타일로 screen 프로세스 관리

## Final Recommendation
- 구현 언어: Python
- 기본 실행 형태: Codex cron dispatcher
- sidecar 실행 형태: Telegram 브리지와 분리된 단일 워커, 명시적 요청 시에만 사용
- 프로세스 관리: 기본은 Codex automation, sidecar가 필요하면 `launchd` 또는 `screen + control/state files`
