# Automation Supervision Design

## Purpose
이 문서는 `woong-bb Codex timer dispatcher`와 선택적 `automation worker`를 안정적으로 감시, 제어하기 위한 운영 설계다.

핵심 목표:
- 이중 실행 방지
- dispatcher 실행 이력 기반 상태 감시
- sidecar worker를 켤 경우 heartbeat 기반 상태 감시
- 세팅모드에서 즉시 관제 가능
- 꼬였을 때 안전한 stop/start/restart

## Recommended Architecture
- 기본: Codex cron automation이 `/Users/kein/Desktop/woong-bb/tools/run_due_codex_timers.py`를 주기 실행한다.
- 보조: 실시간 감지가 필요할 때만 `telegram bridge`와 분리된 `python automation worker`를 켠다.
- 그 위에 `supervision/control layer`를 둔다.

구성:
1. Codex cron dispatcher
2. dispatcher state/history
3. optional worker process
4. optional singleton lock + heartbeat/status writer
5. supervisor command layer
6. setting mode dashboard/state reader

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/automation_supervision_design_ko.md`
- Worker state: `/Users/kein/Desktop/woong-bb/state/automation_worker_state.json`
- Codex dispatcher state: `/Users/kein/Desktop/woong-bb/state/codex_timer_dispatch_state.json`
- Supervisor state: `/Users/kein/Desktop/woong-bb/state/automation_supervisor_state.json`
- Control commands: `/Users/kein/Desktop/woong-bb/state/automation_control.json`
- Health snapshots: `/Users/kein/Desktop/woong-bb/state/automation_health.json`

## Core Rules

### 1. Singleton Guarantee
기본 dispatcher는 long-running process가 아니므로 singleton lock이 필요 없다.

sidecar worker를 켤 경우:
- worker 시작 전 lock 파일 확보
- 이미 살아 있는 pid + 최근 heartbeat가 유효하면 새 worker 시작 금지
- lock은 아래 기준으로 stale 여부 판정
  - pid 존재 여부
  - heartbeat 최신 시각
  - generation token 일치 여부

### 2. Heartbeat
Codex dispatcher는 heartbeat 대신 `codex_timer_dispatch_state.json`의 `last_checked_at`, `history`, `errors`를 본다.

sidecar worker를 켤 경우:
- worker는 매 loop마다 heartbeat 기록
- 필드:
  - `pid`
  - `started_at`
  - `last_heartbeat_at`
  - `current_phase`
  - `last_success_at`
  - `last_error_at`
  - `last_error_summary`
  - `generation`

### 3. Safe Restart
- restart 요청 시 순서:
  1. control state에 `requested_action=restart`
  2. 현재 pid 종료 시도
  3. lock release 확인
  4. generation 증가
  5. 새 worker 시작
- 같은 generation이 아니면 예전 worker는 상태 기록만 하고 작업 중단

### 4. Health Model
- `healthy`
- `starting`
- `idle`
- `running`
- `degraded`
- `stuck`
- `stopped`
- `duplicate_suspected`

판정 예:
- heartbeat 2분 이내: healthy/running
- heartbeat 2-5분 지연: degraded
- heartbeat 5분 초과: stuck
- pid 2개 이상 감지: duplicate_suspected

## Control Plane

### Control File
- `automation_control.json`
- 세팅모드에서 수정 가능한 명령:
  - `start`
  - `stop`
  - `restart`
  - `disable`
  - `enable`
  - `clear_stale_lock`
  - `force_recalc`

### Launch Authorization
- 기본 원칙은 `explicit_user_command_only_for_sidecar`다.
- 구현 완료만으로는 sidecar worker를 시작하지 않는다.
- 세팅모드에서 준비 상태를 점검한 뒤, 마스터가 시작 지시를 했을 때만 `start` 또는 `enable`을 적용한다.
- 그 전까지는 control/state 파일만 갱신하고 health는 `stopped`를 유지한다.

### State Response
- worker는 control file을 읽고 작업
- 처리 후:
  - `last_applied_action`
  - `last_applied_at`
  - `last_action_result`
  기록

## Monitoring Requirements For Setting Mode
- 세팅모드에서는 아래를 바로 읽고 보고할 수 있어야 한다.
  - dispatcher 마지막 실행 시각
  - dispatcher 최근 fired/error 이력
  - worker on/off
  - 시작 승인 정책
  - pid
  - 마지막 heartbeat 시각
  - 현재 상태
  - 마지막 성공 시각
  - 마지막 오류
  - duplicate 여부
  - pending control action

## Recommended Commands
- `worker 상태`
- `worker 켜`
- `worker 꺼`
- `worker 재시작`
- `worker 강제정리`
- `worker 재계산`

## Failure Handling
- duplicate 의심:
  - 새 worker 시작 금지
  - health 상태를 `duplicate_suspected`로 표기
  - 세팅모드에서 정리 명령 필요
- stale lock:
  - pid 없음 + heartbeat 오래됨이면 `clear_stale_lock` 허용
- 반복 실패:
  - 3회 이상 연속 실패 시 `degraded`
  - 자동 이벤트 발송은 멈추고 상태 갱신만 유지 가능

## Best Operational Choice
- worker 본체: Python
- supervisor: 같은 Python 계열 상태 파일 기반
- macOS 운영: 최종적으로 `launchd`
- 초기 운용: `screen + control/state files`

## Final Recommendation
가장 관리하기 쉬운 구조는:
- `Codex cron dispatcher`
- optional `Python worker`
- sidecar 사용 시 `single lock + heartbeat`
- `JSON control/state plane`
- `setting mode 관제`
- 기본은 Codex automation, sidecar가 필요할 때만 `launchd or screen supervisor`
