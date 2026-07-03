# 온라인 리서치

## 이번에 검색한 키워드

- `roguelite meta progression design article hades dead cells unlock structure`
- `vampire survivors progression unlocks gold upgrades official`
- `halls of torment quest-based meta progression official`
- `slay the spire path relic choice official`

## 찾은 자료

- [What is Meta-Progression?](https://www.gamebrief.net/glossary/meta-progression) — 메타 성장은 런 바깥에 남는 해금/업그레이드 층이고, 실패 뒤에도 다음 시도를 여는 장치라는 점을 정리함. 특히 단순 스펙업뿐 아니라 콘텐츠 해금도 핵심 범주로 봄.
- [Hades on Steam](https://store.steampowered.com/app/1145360/hades/) — 매 탈출 시도마다 더 강해지고 스토리를 더 푼다고 소개함. `Mirror of Night` 같은 영구 성장으로 다음 런의 진입 장벽을 낮추되, 빌드 다양성은 각 런 안에서 다시 만듦.
- [Dead Cells on Steam](https://store.steampowered.com/app/588650/Dead_Cells/) — `새 경로`, `새 레벨 접근`, `변이`, `능력`, `무기`를 다음 런으로 이어지는 진척으로 제시함. 즉 메타 성장이 단순 공격력 증가가 아니라 `갈 수 있는 곳`과 `쓸 수 있는 것`을 넓힘.
- [Vampire Survivors on Steam](https://store.steampowered.com/app/1794680/Vampire_Survivors/) — 매 런에서 골드를 모아 다음 생존자를 돕는 업그레이드를 산다고 설명함. 런 밖 성장의 보상감은 강하지만, 구조상 수치 성장 쏠림이 크다는 점도 읽힘.
- [Halls of Torment on Steam](https://store.steampowered.com/app/2218750/Halls_of_Torment/) — `quest-based meta progression`을 전면에 내세움. 과제 달성 기반 해금과 런 내부 시너지 구성이 같이 굴러가는 구조라, 반복 플레이 동기를 목표 단위로 쪼개는 데 참고할 만함.
- [Slay the Spire on Steam](https://store.steampowered.com/app/646570/Slay_the_Spire/) — 위험한 길/안전한 길 선택, 카드와 유물 발견, 다른 보스 조합을 핵심 재미로 소개함. 즉 반복 동기를 수치보다 `선택의 결과가 달라지는 구조`로 유지함.

## 이번 리서치에서 읽힌 패턴

1. 좋은 메타 성장은 `다음 런을 더 쉽게 만드는 것`보다 `다음 런에서 더 많은 선택과 다른 운영을 가능하게 만드는 것`에 가까움.
2. Hades와 Dead Cells는 영구 진척이 있지만, 그 진척이 런 안 의사결정을 완전히 덮지 않음.
3. Vampire Survivors식 골드 구매는 즉각 보상은 강하지만, 너무 세지면 `반복 = 스펙 올리기`로 수렴할 위험이 있음.
4. Halls of Torment처럼 과제형 해금은 플레이어가 `왜 한 판 더 하지?`에 답하기 쉬움.
5. Slay the Spire처럼 경로와 보상 선택이 다음 전투의 성격을 바꾸면, 완주 동기가 단순 숫자보다 설득력 있게 남음.

## 웨일서바이버에 바로 주는 영향

- 메타 성장 축은 `영구 공격력/체력`보다 `엑트 클리어로 새 선택지 층을 여는 방식`이 더 맞음
- 엑트 보상은 `다음 엑트에서 요구하는 태그/무기 운영을 가능하게 하는 열쇠`여야 함
- 보상 획득 조건은 그냥 재화 구매보다 `엑트 클리어`나 `태그 운용 성취`에 걸어두는 편이 프로젝트 방향과 잘 맞음

---

## 전투력 계산 리서치 메모

이번엔 메타 성장 말고, `런 안 전투력`을 다른 게임들이 실제로 어떻게 풀어내는지 쪽으로 봤다.

### 참고한 자료

- [Brotato Wiki - Weapons](https://brotato.wiki.spellsandguns.com/Weapons)
- [Brotato Wiki - Attack Speed](https://brotato.wiki.spellsandguns.com/Attack_Speed)
- [Hades Wiki - Boons](https://hades.fandom.com/wiki/Boons)
- [Hades Wiki - Demeter/Boons](https://hades.fandom.com/wiki/Demeter/Boons_%28Hades%29)
- [Vampire Survivors Wiki - Evolution](https://vampire.survivors.wiki/w/Evolution)
- [Vampire Survivors Wiki - Limit Break](https://vampire.survivors.wiki/w/Limit_Break)

### 읽힌 패턴

1. `단일 DPS 하나`로 끝내지 않는다  
   Brotato는 무기 표에 DPS를 보여주지만, 위키에서도 `특수효과와 치명타는 DPS 계산에 포함되지 않는다`고 따로 둔다. 즉 표시용 기본 화력과 실전 체감 화력을 분리해서 본다.

2. `공속/쿨다운`은 선형 취급하면 자주 틀어진다  
   Brotato는 공속 100%면 기본적으로 쿨다운이 절반이 되지만, 음수 공속 구간, 근접 무기의 Range 영향, 최소 쿨다운, 무기별 체감 손실 때문에 완전 선형이 아니라고 적어둔다.  
   우리도 `공속 = DPS 비례 증가`로 고정하면 나중에 무기별 예외가 터질 가능성이 높다.

3. `희귀도/레벨`은 같은 성장처럼 보여도 별개 축이다  
   Hades는 boon rarity와 boon level이 둘 다 수치를 올리지만, 위키도 `+1 rarity`와 `+1 level`은 결과가 다르다고 분리해둔다.  
   실제 예시도 Common `+40%`가 Rare/Epic/Heroic에서 단순 같은 계단이 아니라 다른 배수 범위로 커진다.  
   우리 쪽도 `무기 레벨 성장`과 `태그 단계 성장`을 같은 계수표로 뭉개면 안 된다.

4. `시너지 해금`은 개별 레벨업과 따로 계산해야 한다  
   Vampire Survivors는 기본 무기를 최고 레벨까지 올리고, 특정 passive 조건을 맞춰야 evolution이 열린다.  
   즉 강해지는 구조가 `무기 레벨 상승`과 `조건 달성 후 변신` 두 층으로 갈라져 있다.  
   이건 우리 쪽 `무기 점수`와 `태그 활성 보너스`를 분리해야 하는 근거로 쓰기 좋다.

5. `상한 돌파`는 따로 취급하는 편이 안전하다  
   Vampire Survivors의 Limit Break처럼 최대 레벨 이후의 성장은 기본 성장과 다른 페이즈로 들어간다.  
   그래서 엑트1 계산식은 `현재 허용 상한 안에서의 기대 전투력`만 먼저 맞추고, 상한 돌파는 후속 모델로 분리하는 게 낫다.

### 웨일서바이버에 바로 가져올 규칙

- `무기 점수`와 `태그 점수`는 합치지 말고 별도 축으로 계산
- `무기 레벨 성장`과 `단계 해금/진화`는 다른 계수 체계로 계산
- `표시용 기본 화력`과 `실전 전투력`은 분리
- `공속/쿨다운`은 무기별 예외를 허용하는 함수형 계산으로 설계
- `시간축 기대 전투력`은 드로우 기대값까지 넣어서 구간별로 따로 계산

### 지금 계산식 설계에 주는 결론

우리가 만들 식은 `무기 3개 합산 DPS`가 아니라 아래처럼 가는 게 맞아 보인다.

1. 무기별 기본 점수 계산
2. 무기 레벨 계수 적용
3. 무기 3개 조합 보너스/패널티 적용
4. 태그 활성 단계 보너스 적용
5. 시간축 드로우 기대값을 넣은 기대 전투력으로 변환

즉 `정적 전투력 식`과 `시간축 기대 전투력 식`을 분리해서 가져가는 쪽이, 리서치된 사례들하고도 가장 잘 맞는다.
