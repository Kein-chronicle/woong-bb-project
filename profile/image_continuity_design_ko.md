# Image Continuity Design

## Purpose
이 문서는 웅삐가 이미지를 여러 번 보낼 때, 직전 이미지와의 시간 간격과 상황 변화량을 기준으로 착장, 얼굴 상태, 분위기, 공간을 얼마나 유지할지 정하는 연속성 설계다.

핵심 목표:
- 방금 보낸 사진 다음 사진이 갑자기 다른 사람처럼 보이지 않게 하기
- 짧은 시간 차이면 직전 사진 자체를 참조해 공간/착장/얼굴 상태를 최대한 유지하기
- 시간이 좀 흘렀어도 같은 일정 블록이면 적어도 착장과 얼굴 상태는 유지하기

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/image_continuity_design_ko.md`
- State: `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json`
- Resolver: `/Users/kein/Desktop/woong-bb/tools/image_continuity_resolver.py`
- Appearance state: `/Users/kein/Desktop/woong-bb/state/eunbi_appearance_state.json`
- Share event design: `/Users/kein/Desktop/woong-bb/profile/share_event_design_ko.md`

## Core Principle
- 이미지 생성은 항상 현재 appearance state만 보는 것으로 끝내지 않는다.
- 최근 전송 이미지가 있으면 `appearance continuity`와 `photo continuity`를 함께 판정한다.
- 판정 결과는 세 가지다.
  - `full_scene_reference`
  - `outfit_face_reference`
  - `no_direct_image_reference`

## Continuity Bands

### 1. Immediate Repeat Window
- 기준: 최근 이미지 전송 후 `20분 이내`
- 조건:
  - 큰 활동 전환이 없음
  - 샤워, 운동, 귀가, 옷 갈아입기 같은 외형 리셋 이벤트가 없음
- 처리:
  - 직전 이미지 자체를 직접 참조
  - 공간, 조명, 표정 결, 헤어 흐름, 착장을 최대한 유지
- 사용 모드:
  - `full_scene_reference`

### 2. Same Outfit Window
- 기준: 시간이 `20분 초과`여도 같은 일정 블록/같은 착장 컨텍스트
- 예:
  - 오전 집중 작업 중
  - 점심 포함 같은 근무 착장 블록
  - 퇴근 전까지 같은 출근복 유지
  - 카페/외출 중 아직 갈아입지 않은 상태
- 처리:
  - 직전 이미지를 참조하되 공간은 바뀔 수 있음
  - 착장, 헤어 정돈 정도, 메이크업 무너짐 정도, 얼굴 컨디션은 직전 이미지에 맞춰 유지
- 사용 모드:
  - `outfit_face_reference`

### 3. Expired Continuity
- 기준:
  - 샤워, 운동 후, 귀가 후 갈아입음, 잠옷 전환, 출근복에서 홈웨어로 전환 등
  - 다른 일정 블록으로 넘어감
- 처리:
  - 직전 이미지 자체는 직접 참조하지 않음
  - 현재 appearance state만 기준으로 새로 구성
- 사용 모드:
  - `no_direct_image_reference`

## Outfit Continuity Families
- `hospital_workday`
  - 출근 준비
  - 출근길
  - 오전 근무
  - 점심
  - 오후 근무
  - 퇴근 직전/퇴근길
- `home_relaxed`
  - 저녁 집
  - 밤 홈웨어
  - 자기 전
- `exercise_block`
  - 러닝
  - 수영 전후
  - 헬스/자전거
- `cafe_outing`
  - 카페
  - 외출
  - 가벼운 산책/공원

같은 family 안에서는 시간 차가 좀 있어도 `outfit_face_reference`를 우선 검토한다.

## Preserve Scope

### full_scene_reference
- 유지 우선순위:
  1. 얼굴 컨디션
  2. 헤어 흐름과 묶음 상태
  3. 메이크업 상태
  4. 상하의/아우터/가방/액세서리
  5. 공간과 조명 톤
  6. 포즈 결

### outfit_face_reference
- 유지 우선순위:
  1. 상하의/아우터/가방/액세서리
  2. 헤어 상태
  3. 메이크업 무너짐 정도
  4. 얼굴 피로/개운함 상태
- 바뀌어도 되는 것:
  - 장소
  - 배경
  - 프레이밍
  - 손에 든 것

### no_direct_image_reference
- 현재 appearance state와 situation state를 새 기준으로 사용

## Required Snapshot On Image Send
- 이미지를 실제 보낸 직후 `image_continuity_state.json`에 아래를 기록한다.
  - 마지막 이미지 경로
  - 전송 시각
  - 당시 appearance snapshot
  - continuity family
  - scene tag
  - selfie/lifestyle 여부

그래야 다음 이미지 생성 때 직전 이미지를 정확히 참조할 수 있다.

## Resolver Rule
- 이미지 생성 전 `image_continuity_resolver.py`를 먼저 실행한다.
- resolver는 메시지 로그의 마지막 outgoing image와 현재 appearance state를 읽고 아래를 계산한다.
  - continuity band
  - preserve scope
  - direct reference path
  - preserve target fields
  - continuity reason

## Prompt Usage
- `full_scene_reference`면:
  - 직전 사진과 같은 공간, 같은 착장, 같은 얼굴 상태를 유지하는 보정 프롬프트를 건다.
- `outfit_face_reference`면:
  - 직전 사진과 같은 옷, 같은 헤어/메이크업/얼굴 컨디션 유지
  - 공간과 구도만 현재 상황에 맞게 바꾼다.
- `no_direct_image_reference`면:
  - 현재 appearance state 기준으로 새 장면 생성

## Examples

### Example A
- 06:45 출근길 셀피 보냄
- 06:58 또 셀피 보냄
- 결과:
  - `full_scene_reference`
  - 출근복, 얼굴 상태, 조명 톤, 배경 결 최대 유지

### Example B
- 08:40 작업 중 셀피 보냄
- 13:10 점심 직후 사진 보냄
- 결과:
  - `outfit_face_reference`
  - 같은 근무 착장 유지
  - 얼굴 피로감/립 수정 정도만 소폭 변화
  - 공간은 휴게실/복도 등으로 바뀔 수 있음

### Example C
- 17:20 퇴근길 출근복 사진 보냄
- 21:40 샤워 후 잠옷 사진 보냄
- 결과:
  - `no_direct_image_reference`
  - 직전 출근복 이미지는 더 이상 직접 참조하지 않음
