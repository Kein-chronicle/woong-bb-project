# couple_script_sample

- bundles: 100
- utterances: 1000
- raw sources: 13
- language priority: Korean-only in this build

## notes
- 공개 유튜브 커플/부부 영상의 자동 자막을 정리했습니다.
- 화자 표시는 실제 음성 분리 없이 교대형으로 추정했습니다.
- 연구용 초벌 말뭉치로는 쓸 수 있지만, 정밀 분석 전에는 원본 영상 청취 확인이 좋습니다.
- 번역본이 아니라 한국어 원천 자막만 사용했습니다.
- `source_quality_report.json`에 소스별 수용 발화 수와 품질 요약을 함께 저장합니다.

## files
- `raw/`: 영상 단위 정규화 자막
- `bundles/`: 10발화 단위 묶음
- `manifest.json`: 원본 인덱스
- `source_quality_report.json`: 소스별 accepted 발화 수와 품질 요약
