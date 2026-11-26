/**
 * **3D 에 비출 것** — 조건 화면의 표시 층을 한 곳에서 짓는다(`ConditionsPanel` 에서 나눴다, 동작 그대로).
 *
 * - 담은 것(선택 그룹을 만드는 중) — 번호와 함께.
 * - 트리에서 고른 선택 그룹 — 서버가 지금 형상에서 푼 것, 그리고 몇 개를 집는지(트리에 적는다).
 * - 접촉 표시(켰을 때) — 본딩은 붉게, 그 밖의 접촉은 푸르게.
 * - 고치는 조건의 자리 — 창을 연 조건이 가리키는 선택 그룹(접촉은 접촉면 · 대상면 색).
 */

import { useEffect, useMemo, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { conditionsApi } from '@/modules/conditions/api'
import type { ConditionItem, NamedSelection } from '@/modules/conditions/api'
import type { Member } from '@/modules/conditions/ConditionWindows'
import { bodyMarks, CONTACT_COLOR, contactKind, contactMarks, emptyMarks, foundMarks, mergeMarks, SOURCE_COLOR, TARGET_COLOR, TIE_COLOR } from '@/modules/conditions/highlight'
import type { ContactKind, FoundRow } from '@/modules/conditions/highlight'
import type { TreeSelection } from '@/modules/conditions/ModelTree'
import type { MeasureMarks, MeshData } from '@/shared/viewer/PickViewer'

export interface MarksInput {
  recipe: Recipe
  mesh: MeshData | null | undefined
  names: NamedSelection[]
  contacts: ConditionItem[]
  members: Member[]
  tree: TreeSelection
  /** 창에서 고치는 조건 — 해석 설정 창이면 비출 것이 없다. */
  editing: { group: string; item: ConditionItem } | null
  /** 그 조건의 대상 칸 — 그 종류가 쓰는 것만(`only_for`). */
  editingTargets: string[]
  showContacts: boolean
}

export function useConditionMarks({ recipe, mesh, names, contacts, members, tree, editing, editingTargets, showContacts }: MarksInput) {
  /**
   * 담은 것을 3D 에 **번호와 함께** — 목록의 몇 번이 어디인지 보인다. 바디는 그 파트의 면 전부
   * (단품은 면에 파트 이름이 없고 바디가 「전체」 하나다).
   */
  const memberMarks = useMemo<MeasureMarks | undefined>(() => {
    if (members.length === 0) return undefined
    const out: MeasureMarks = { points: [], segments: [], labels: [], edges: [], faces: [] }
    members.forEach((member, index) => {
      const text = String(index + 1)
      const pick = member.pick
      if (pick.kind === 'point') {
        out.points.push(pick.at)
        out.labels.push({ at: pick.at, text, tone: 'entity' })
      } else if (pick.kind === 'edge') {
        out.edges.push({ points: pick.edge.points, tone: 'live' })
        out.labels.push({ at: pick.edge.midpoint, text, tone: 'entity' })
      } else if (pick.kind === 'face') {
        out.faces.push({ vertices: pick.face.vertices, triangles: pick.face.triangles, tone: 'live' })
        out.labels.push({ at: pick.face.center, text, tone: 'entity' })
      } else {
        for (const face of mesh?.faces ?? []) {
          if ((face.part || '전체') === pick.name) {
            out.faces.push({ vertices: face.vertices, triangles: face.triangles, tone: 'live' })
          }
        }
      }
    })
    return out
  }, [members, mesh])

  /**
   * **트리에서 고른 선택 그룹을 3D 에 비춘다** — 그 그룹이 지금 형상에서 집는 것들. 규칙은
   * 서버가 푼다(합 · 태그까지). 바디 그룹은 물을 것이 없다 — 파트 이름이 곧 답이다.
   */
  const litGroup = tree?.kind === 'selection' ? names[tree.index] : undefined
  const litKey = litGroup ? JSON.stringify([litGroup.entity, litGroup.select]) : ''
  const [lit, setLit] = useState<{ key: string; what: string; rows: FoundRow[] } | null>(null)
  useEffect(() => {
    if (!litGroup || litGroup.entity === 'body') return
    let alive = true
    conditionsApi
      .resolve(recipe, litGroup.select)
      .then((got) => alive && setLit({ key: litKey, what: got.what, rows: got.items }))
      // 못 풀면 비추지 않을 뿐이다 — 개수 자리에 0 이 보여 「지금 아무것도 안 집는다」 를 말한다.
      .catch(() => alive && setLit({ key: litKey, what: '', rows: [] }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [litKey, recipe])
  const groupMarks = useMemo<MeasureMarks | undefined>(() => {
    if (!mesh || !litGroup) return undefined
    if (litGroup.entity === 'body') return bodyMarks(mesh, litGroup.select)
    return lit?.key === litKey ? foundMarks(mesh, lit.what, lit.rows) : undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mesh, litKey, lit])
  /** 지금 형상에서 그 그룹이 몇 개를 집나 — 트리에 적는다. 푸는 중이면 `null`. */
  const litCount = !litGroup
    ? null
    : litGroup.entity === 'body'
      ? (Array.isArray(litGroup.select.any) ? litGroup.select.any.length : 1)
      : lit?.key === litKey
        ? lit.rows.length
        : null
  const contactGroups = useMemo(() => {
    const byName = new Map(names.map((one) => [one.name, one]))
    const out: { select: Record<string, unknown>; kind: ContactKind }[] = []
    for (const one of contacts) {
      for (const side of [one.source, one.target]) {
        const group = byName.get(String(side ?? ''))
        if (group && group.entity !== 'body') out.push({ select: group.select, kind: contactKind(one.type) })
      }
    }
    return out
  }, [contacts, names])
  const contactsKey = JSON.stringify(contactGroups)
  const [contactRows, setContactRows] = useState<{ key: string; items: { what: string; rows: FoundRow[]; kind: ContactKind }[] } | null>(null)
  useEffect(() => {
    if (!showContacts || contactGroups.length === 0) return
    let alive = true
    void Promise.all(
      contactGroups.map((group) =>
        conditionsApi
          .resolve(recipe, group.select)
          .then((got) => ({ what: got.what, rows: got.items, kind: group.kind }))
          // 못 푼 그룹은 칠하지 않을 뿐이다.
          .catch(() => ({ what: 'faces', rows: [] as FoundRow[], kind: group.kind })),
      ),
    ).then((items) => alive && setContactRows({ key: contactsKey, items }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showContacts, contactsKey, recipe])
  const contactLayer = useMemo(
    () => (showContacts && mesh && contactRows?.key === contactsKey ? contactMarks(mesh, contactRows.items) : undefined),
    [showContacts, mesh, contactRows, contactsKey],
  )
  const contactCounts = {
    tie: contactLayer?.faces.filter((one) => one.color === TIE_COLOR).length ?? 0,
    contact: contactLayer?.faces.filter((one) => one.color === CONTACT_COLOR).length ?? 0,
  }
  /**
   * **고치는 조건의 자리** — 창을 연 조건이 가리키는 선택 그룹을 3D 에 비춘다. 접촉은 접촉면(Contact)을
   * 붉게, 대상면(Target)을 푸르게 — 그 접촉이 어디인지 창을 연 채 보인다. 구속 · 하중은 강조색.
   */
  const editRefs = useMemo(() => {
    if (!editing || editing.group === 'analysis') return []
    const byName = new Map(names.map((one) => [one.name, one]))
    return editingTargets.flatMap((field) => {
      const group = byName.get(String(editing.item[field] ?? ''))
      return group ? [{ field, group }] : []
    })
  }, [editing, names, editingTargets])
  const editKey = JSON.stringify(editRefs.map((one) => [one.field, one.group.entity, one.group.select]))
  const [editRows, setEditRows] = useState<{ key: string; items: { field: string; what: string; rows: FoundRow[] }[] } | null>(null)
  useEffect(() => {
    const asking = editRefs.filter((one) => one.group.entity !== 'body')
    if (asking.length === 0) return
    let alive = true
    void Promise.all(
      asking.map((one) =>
        conditionsApi
          .resolve(recipe, one.group.select)
          .then((got) => ({ field: one.field, what: got.what, rows: got.items }))
          .catch(() => ({ field: one.field, what: '', rows: [] as FoundRow[] })),
      ),
    ).then((items) => alive && setEditRows({ key: editKey, items }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editKey, recipe])
  const contactEditing = editing?.group === 'contacts'
  const editLayer = useMemo<MeasureMarks | undefined>(() => {
    if (!mesh || editRefs.length === 0) return undefined
    const out = emptyMarks()
    for (const ref of editRefs) {
      const found = editRows?.key === editKey ? editRows.items.find((one) => one.field === ref.field) : undefined
      const layer = ref.group.entity === 'body' ? bodyMarks(mesh, ref.group.select) : found ? foundMarks(mesh, found.what, found.rows) : undefined
      if (!layer) continue
      const color = contactEditing ? (ref.field === 'source' ? SOURCE_COLOR : TARGET_COLOR) : undefined
      out.faces.push(...layer.faces.map((face) => (color ? { ...face, color, opacity: 0.6 } : face)))
      out.edges.push(...layer.edges)
      out.points.push(...layer.points)
    }
    return out
  }, [mesh, editRefs, editRows, editKey, contactEditing])
  /**
   * 담는 중이면 담은 것, 아니면 트리에서 고른 그룹 — 그 아래에 고치는 조건의 자리, 접촉 표시.
   * 접촉을 고치는 동안은 접촉 표시를 끈다(같은 색을 다른 뜻으로 쓴다).
   */
  const marks = mergeMarks(contactEditing ? undefined : contactLayer, editLayer, memberMarks ?? groupMarks)

  return { marks, litCount, contactCounts, editRefs, contactEditing }
}
