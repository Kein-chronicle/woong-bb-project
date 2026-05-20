# Automation Worker Design

## Recommendation
현재 구조에서는 `별도 Python 워커 프로세스 1개`가 가장 안정적이다.

## Why This Is Best
- 이미 운영 도구가 Python 기반이다.
- 상태 파일이 전부 JSON/JSONL이라 Python이 다루기 쉽다.
- Telegram 브리지와 분리하면 대화 응답과 자동 이벤트가 서로 덜 꼬인다.
- 재시작, 로그, 상태 확인을 `botctl.py`와 비슷한 방식으로 관리하기 쉽다.

## Recommended Shape
- 이름: `woong-bb-automation-worker`
- 역할:
  - 시간대 전환 감지
  - 날씨/미디어 조회 갱신
  - share priority 재계산
  - 선톡 후보 생성
  - 이미지/링크 공유 후보 계산
  - 실제 발송 가능 여부 판정

## Supervision Dependency
- worker는 단독으로만 두지 않고 supervisor/control layer와 함께 운영한다.
- 관련 문서: `/Users/kein/Desktop/woong-bb/profile/automation_supervision_design_ko.md`
- 관련 상태 파일:
  - `/Users/kein/Desktop/woong-bb/state/automation_supervisor_state.json`
  - `/Users/kein/Desktop/woong-bb/state/automation_control.json`
  - `/Users/kein/Desktop/woong-bb/state/automation_health.json`

## Activation Gate
- 연결과 구현은 먼저 끝내도 된다.
- 실제 worker 시작은 마스터의 명시적 지시 전까지 금지한다.
- 준비가 끝나면 자동으로 시작하지 않고, `실행 가능 상태`와 확인 항목을 보고한 뒤 시작 여부를 묻는다.
- 기본 상태는 `disabled/stopped`로 유지한다.

## Process Model
- Telegram 브리지와 별도 프로세스
- 짧은 주기 poll + 이벤트 기반 재계산 혼합
- 권장 주기:
  - 일반 상태 점검: 60초
  - 시간대 전환 직전/직후: 즉시
  - 실제 링크 확보/이미지 전송 후: 즉시

## Avoid
- cron만으로 구성
  - 대화 중 상태, 미답장, 쿨다운 반영이 거칠다
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
- 실행 형태: Telegram 브리지와 분리된 단일 워커
- 프로세스 관리: macOS면 `launchd`, 현재 운영 일관성을 중시하면 초기엔 `screen + botctl`로 시작 후 `launchd`로 옮기는 방식
