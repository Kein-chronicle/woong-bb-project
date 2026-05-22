# Automation Worker Design

## Recommendation
현재 기본 구조에서는 프로젝트가 직접 소유하는 `automation_worker`를 주 실행기로 두는 편이 맞다.

Codex 자동화는 실제 서비스 동작을 돌리지 않고, health check와 검수 보고만 맡는다.

## Why This Is Best
- 이미 운영 도구가 Python 기반이다.
- 상태 파일이 전부 JSON/JSONL이라 Python이 다루기 쉽다.
- 프로젝트 안에서 `launchd`나 동급 supervisor로 worker를 소유하면 실제 동작 로직과 상태를 한 곳에서 추적할 수 있다.
- 선톡, 상태 전환, 성장/리서치 같은 런타임 동작은 서비스 자체의 워커가 책임지는 편이 역할이 선명하다.
- Telegram 브리지와 자동 타이머 처리를 분리하면 대화 응답과 자동 이벤트가 서로 덜 꼬인다.

## Recommended Shape
- 이름: `woong-bb-automation-worker`
- 기본 실행기: `/Users/kein/Desktop/woong-bb/tools/automation_worker.py`
- launchd 관리 스크립트: `/Users/kein/Desktop/woong-bb/tools/manage_automation_worker.py`
- 원샷 타이머 실행기: `/Users/kein/Desktop/woong-bb/tools/run_timer_once.py`
- 역할:
  - 시간대 전환 감지
  - 날씨/미디어 조회 갱신
  - share priority 재계산
  - 선톡 후보 생성
  - 이미지/링크 공유 후보 계산
  - 실제 발송 가능 여부 판정
  - 성장/리서치 tick 실행

## Supervision Dependency
- 기본 타이머는 프로젝트 worker가 처리한다.
- Codex 자동화는 worker 상태 감시, 정적 검증, 코드/상태 검수만 담당한다.
- worker는 `launchd`나 동급 supervisor와 control/state layer를 함께 운영한다.
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
- launch agent 설치까지는 해도 되지만, 실제 `bootstrap/start`는 명시 지시 전까지 하지 않는다.

## Process Model
- 기본: project-owned worker가 60초 poll로 타이머와 상태 갱신을 직접 처리한다.
- 보조: `run_timer_once.py`와 `run_due_codex_timers.py`는 수동 복구나 단발 실행용으로만 남긴다.

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
- 설치/상태 확인용 스크립트는 `tools/manage_automation_worker.py`를 사용한다.

## Final Recommendation
- 구현 언어: Python
- 기본 실행 형태: project-owned long-running worker
- 실행 진입점: `/Users/kein/Desktop/woong-bb/tools/automation_worker.py`
- 프로세스 관리: 기본은 `launchd`, 대안은 `screen + control/state files`
- Codex 자동화 역할: health watch, 코드 검수, 안전한 운영 리포트
