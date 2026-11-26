/**
 * **3D 에서 담기** — 누른 것을 선택 그룹의 재료로 담는다(`ConditionsPanel` 에서 나눴다, 동작 그대로).
 *
 * 누를 때마다 서버가 그 자리를 부를 **선택 규칙 후보**를 준다(`/cad/recipe/selectors`) — 사람이 고른다. Ctrl(⌘)은
 * 넣고 빼기, Shift 는 더하기, Shift + 끌기는 사각형으로 여럿(후보는 한 번에 묻는다). 담은 것의 규칙은 하나면 그 규칙,
 * 여럿이면 합(`{"any": [...]}`).
 */

import { useMemo, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { conditionsApi, defaultRule } from '@/modules/conditions/api'
import type { NamedSelection, SelectorCandidate } from '@/modules/conditions/api'
import type { Member } from '@/modules/conditions/ConditionWindows'
import { ApiError } from '@/shared/api/client'
import type { MeasurePick, PickModifiers } from '@/shared/viewer/PickViewer'

/**
 * 3D 에서 찍은 것 → 서버에 물을 말. 면 · 엣지는 **번호도** 보낸다 — 판 윗면과 그 위 블록의
 * 아랫면처럼 중심이 같은 두 면은 자리만으로는 못 가른다.
 */
function toPick(pick: MeasurePick): { what: string; point: number[]; index?: number; label: string } {
  if (pick.kind === 'point') return { what: 'vertices', point: pick.at, label: '점' }
  if (pick.kind === 'edge') return { what: 'edges', point: pick.edge.midpoint, index: pick.edge.index, label: '엣지' }
  if (pick.kind === 'body') return { what: 'bodies', point: [], label: '바디' }
  return { what: 'faces', point: pick.face.center, index: pick.face.index, label: '면' }
}

/**
 * **무엇을 선택 대상인가.** 켠 것 하나만 잡힌다.
 *
 * 이것이 없으면 엣지를 고르려는데 점이 먼저 잡힌다 — 뷰어가 점 · 엣지 · 면 순으로 걸기
 * 때문이고, 그 순서를 사람이 바꿀 길이 없었다.
 *
 * 바디는 면을 눌러 고른다(덩어리를 겨눌 화면 요소가 따로 없다) — 그래서 면과 바디는
 * 동시에 켜면 안 된다. 하나씩만 켜는 것이 곧 그 문제도 푼다.
 */
export const PICK_KINDS = [
  // 작은 것에서 큰 것으로 — 점 · 엣지 · 면 · 바디.
  { key: 'point', label: '점', entity: 'vertex', what: 'vertices' },
  { key: 'edge', label: '엣지', entity: 'edge', what: 'edges' },
  { key: 'face', label: '면', entity: 'face', what: 'faces' },
  { key: 'body', label: '바디', entity: 'body', what: 'bodies' },
] as const

export type PickKind = (typeof PICK_KINDS)[number]['key']

export function useGroupPicking({
  recipe,
  names,
  onStart,
  onError,
}: {
  recipe: Recipe
  names: NamedSelection[]
  /** 누르기 시작했다 — 화면이 오류를 지우고 받을 창을 연다. */
  onStart: () => void
  /** 후보를 받지 못했다. */
  onError: (failure: Error) => void
}) {
  /** 3D 에서 고른 것들 — 「선택 그룹 추가」 창이나 조건 창이 이것으로 그룹을 만든다. */
  const [members, setMembers] = useState<Member[]>([])
  const [groupName, setGroupName] = useState('')

  /** 같은 것을 다시 눌렀는지 가르는 열쇠 — 면 · 엣지는 번호, 점은 좌표, 바디는 이름. */
  function memberKey(pick: MeasurePick): string {
    if (pick.kind === 'point') return `point:${pick.at.map((v) => v.toFixed(3)).join(',')}`
    if (pick.kind === 'edge') return `edge:${pick.edge.index}`
    if (pick.kind === 'face') return `face:${pick.face.index}`
    return `body:${pick.name}`
  }

  /**
   * 3D 에서 누른 것을 **담는다.** 아무것도 안 누르면 새로 고르고, Ctrl(⌘)은 넣고 빼기, Shift 는
   * 더하기다 — CAD 에서 손에 익은 그대로.
   *
   * 조건 창이 떠 있으면 그 창이 받고, 아니면 「선택 그룹 추가」 창이 받는다(없으면 연다).
   */
  async function ask(pick: MeasurePick, mods: PickModifiers = { ctrl: false, shift: false }) {
    onStart()
    const key = memberKey(pick)
    const had = members.some((one) => one.key === key)
    if (mods.ctrl && had) {
      setMembers((now) => now.filter((one) => one.key !== key))
      return
    }
    if (mods.shift && had) return
    const { what, point, index, label } = toPick(pick)
    let candidates: SelectorCandidate[]
    // **바디는 서버에 물을 것이 없다.** 면 · 엣지 · 점은 「이 자리를 무엇으로 부를까」 를
    // 셀렉터 후보로 되받아야 하지만, 바디는 **이름이 곧 답**이다(`topology.bodies`).
    if (pick.kind === 'body') {
      candidates = [{ label: `바디 ‘${pick.name}’`, select: { body: pick.name }, matches: 1 }]
    } else {
      try {
        candidates = (await conditionsApi.selectors(recipe, what, point, index)).candidates
      } catch (failure) {
        onError(failure instanceof ApiError ? failure : new Error(String(failure)))
        return
      }
    }
    if (candidates.length === 0) return
    // 기본 규칙은 **고른 그것 하나**를 가리키고 치수에 흔들리지 않는 것 — 하나씩 골라 묶는
    // 중이므로. 좌표만 쓰는 규칙은 DOE 에서 딴 형상을 집으므로 기본으로 두지 않는다. 같은
    // 반지름의 구멍 넷처럼 부류 전부가 필요하면 목록에서 바꾼다(몇 개에 맞는지 함께 보인다).
    const chosen = defaultRule(candidates)
    const entity = PICK_KINDS.find((one) => one.what === what)?.entity ?? 'face'
    const member: Member = { key, label, entity, pick, candidates, chosen }
    setMembers((now) => {
      if (!mods.ctrl && !mods.shift) return [member]
      return now.some((one) => one.key === key) ? now : [...now, member]
    })
  }

  /**
   * 사각형으로 고른 것들을 **더한다**(Shift). 이미 담긴 것은 건너뛰고, 규칙 후보는 서버에
   * **한 번에** 묻는다 — 하나씩 물으면 고른 수만큼 도면을 다시 만든다.
   */
  async function addMany(picks: MeasurePick[]) {
    if (picks.length === 0) return
    onStart()
    const seen = new Set(members.map((one) => one.key))
    const fresh = picks.filter((pick) => {
      const key = memberKey(pick)
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    const asking = fresh.filter((pick) => pick.kind !== 'body').map(toPick)
    let answers: { candidates: SelectorCandidate[] }[] = []
    if (asking.length > 0) {
      try {
        answers = (await conditionsApi.selectorsMany(recipe, asking.map(({ what, point, index }) => ({ what, point, index })))).items
      } catch (failure) {
        onError(failure instanceof ApiError ? failure : new Error(String(failure)))
        return
      }
    }
    let at = 0
    const made: Member[] = []
    for (const pick of fresh) {
      const { what, label } = toPick(pick)
      const candidates =
        pick.kind === 'body'
          ? [{ label: `바디 ‘${pick.name}’`, select: { body: pick.name }, matches: 1 }]
          : (answers[at++]?.candidates ?? [])
      if (candidates.length === 0) continue
      const chosen = defaultRule(candidates)
      const entity = PICK_KINDS.find((one) => one.what === what)?.entity ?? 'face'
      made.push({ key: memberKey(pick), label, entity, pick, candidates, chosen })
    }
    setMembers((now) => [...now, ...made.filter((one) => !now.some((have) => have.key === one.key))])
  }

  /** 담은 것들의 규칙 — 하나면 그 규칙, 여럿이면 **합**(`{"any": [...]}`). */
  function groupSelect(list: Member[]): Record<string, unknown> {
    const rules = list.map((one) => one.candidates[one.chosen].select)
    return rules.length === 1 ? rules[0] : { any: rules }
  }

  /** 같은 규칙의 선택 그룹이 이미 있으면 그 이름 — 새로 만들지 않고 그것을 쓴다. */
  const existing = useMemo(() => {
    if (members.length === 0) return null
    const select = JSON.stringify(groupSelect(members))
    const same = names.find((one) => one.entity === members[0].entity && JSON.stringify(one.select) === select)
    return same?.name ?? null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [members, names])

  /** 이름을 안 적으면 — 첫 규칙의 말에 「외 N」. */
  const defaultName =
    members.length === 0
      ? ''
      : `${members[0].candidates[members[0].chosen].label}${members.length > 1 ? ` 외 ${members.length - 1}개` : ''}`

  function clearMembers() {
    setMembers([])
    setGroupName('')
  }

  return { members, setMembers, groupName, setGroupName, clearMembers, ask, addMany, groupSelect, existing, defaultName }
}
