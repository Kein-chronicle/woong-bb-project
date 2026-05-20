# Persistent Environment Design

## Purpose
이 문서는 자주 등장하지만 거의 바뀌지 않는 물건과 공간을 별도 메타 자산으로 고정하기 위한 설계다.

목표:
- 스마트폰, 스마트폰 케이스, 침실, 침대, 사이드 테이블, 식탁, 거실 같은 요소를 계속 비슷하게 유지
- 이미지 생성 시 현재 상황 묘사와 별개로 고정 오브젝트/공간 참조를 추가
- 사람이 사는 실제 집처럼 반복 노출되는 배경과 소품의 일관성 유지

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/persistent_environment_design_ko.md`
- State: `/Users/kein/Desktop/woong-bb/state/persistent_environment_state.json`
- Asset registry: `/Users/kein/Desktop/woong-bb/state/persistent_environment_assets.json`
- Meta reference folder: `/Users/kein/Desktop/woong-bb/working/eunbi/meta_references/generated`
- Prompt set: `/Users/kein/Desktop/woong-bb/working/eunbi/meta_references/prompts`

## Core Principle
- 바뀔 일이 거의 없는 물건은 appearance state가 아니라 persistent environment state에서 관리한다.
- 공간은 mood와 조명은 달라질 수 있어도 가구 배치, 재질, 색 계열, 기본 소품은 유지한다.
- 이미지 생성 시 사람이 프레임 중심이 아니더라도, 공간이나 오브젝트가 보이면 이 상태를 우선 참조한다.

## Persistent Object List

### 1. Smartphone
- 6.1인치급 슬림 스마트폰
- 전면은 거의 베젤 없는 블랙 글래스
- 후면 본체 색: 차콜/그래파이트
- 카메라 섬은 좌상단, 과하게 튀지 않는 플래그십형

### 2. Smartphone Case
- 반투명 스모크 그레이 매트 케이스
- 모서리는 살짝 더 진한 범퍼
- 과한 프린트 없음
- 작은 실버 포인트 하나 정도 허용

### 3. Home Bedroom
- 서울 강남권 오피스텔/아파트형 1인 주거 느낌
- 아이보리 벽, 따뜻한 우드 톤 가구
- 침구는 화이트 + 라이트 베이지 계열
- 조명은 전반적으로 따뜻한 전구색

### 4. Bedside Table
- 밝은 오크 톤 원목 협탁
- 위 소품:
  - 작은 무드등
  - 물컵 또는 텀블러
  - 핸드크림/립밤 정도의 생활 소품

### 5. Dining Table
- 2인용 또는 작은 4인용 우드 식탁
- 상판은 월넛/오크 중간톤
- 집밥, 커피, 베이킹 접시가 올려져도 어울리는 생활형 세팅

### 6. Living Room
- 라이트 그레이-베이지 패브릭 소파
- 낮은 우드 테이블
- 러그는 아이보리/웜그레이
- 깔끔하고 정돈된 30대 1인 가구 느낌

## Usage Rule
- 스마트폰이 손에 들리거나 거울셀카, 침대 위, 식탁 위에 놓일 때는 persistent object 상태를 우선 참조한다.
- 침실/거실/식탁이 등장하면 공간 프롬프트에 메타 공간 설명을 먼저 넣는다.
- 직전 이미지 참조가 켜져 있어도, 그 이미지에 스마트폰이나 집안 배경이 명확히 보였으면 persistent environment와 함께 교차 검증한다.

## Prompt Injection Rule
- 오브젝트가 보이면:
  - `persistent_environment_assets.json`의 해당 asset 설명 + 메타이미지 경로 같이 반영
- 공간이 보이면:
  - 고정 배치/재질/색 계열 설명 먼저 반영
  - 현재 시간대 조명과 날씨 영향만 후순위로 가산

## Future Expansion
- 머그컵
- 운동용 물병
- 자주 드는 가방
- 이어폰 케이스
- 집 현관/전신거울
