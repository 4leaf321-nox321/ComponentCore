/**
 * 비슷한 태그 정리 — 같은 타입 안에서 이름이 띄어쓰기 · 이음표 · 대소문자만 다른 태그(「굽힘시험」 ·
 * 「굽힘 시험」)를 묶어 보이고 하나로 합친다(백엔드 `tagging.similar` · `merge`). 「늘리기」 로 쌓인
 * 어휘는 사람마다 적는 법이 달라 갈린다 — 그러면 거르개의 칩도 둘로 갈린다.
 *
 * 합치기는 온톨로지의 객체 합치기 그대로다. 붙은 것이 남길 태그로 옮겨 가고, 지는 쪽 이름은 남길
 * 태그의 별칭이 되어 같은 표기로 다시 붙여도 남길 것으로 풀린다. 규칙에 안 걸리는 것(「굽힘시험」 ·
 * 「3점 굽힘」)은 그 객체 화면의 「합치기」 로 한다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { tagsApi } from '@/modules/tagging/api'
import type { MergedTags, SimilarGroup } from '@/modules/tagging/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { josa } from '@/shared/folders/paths'
import { useResource } from '@/shared/hooks/useResource'

/** 「」 로 감싼 이름 뒤의 조사만 — 받침은 이름의 끝 글자로 정한다. */
const particle = (noun: string, consonant: string, vowel: string) => josa(noun, consonant, vowel).slice(noun.length)

const quoted = (names: string[]) => names.map((one) => `「${one}」`).join(' · ')

const groupKey = (group: SimilarGroup) => `${group.type_slug}:${group.members.map((one) => one.object_id).join(',')}`

export function SimilarTagsPanel() {
  const [round, setRound] = useState(0)
  const found = useResource(() => tagsApi.similar(), [round])
  const [done, setDone] = useState<string | null>(null)
  const groups = found.data?.groups ?? []
  const notes = found.data?.notes ?? []

  function merged(out: MergedTags, names: string[]) {
    setDone(
      `${quoted(names)}${particle(names[names.length - 1] ?? '', '을', '를')} 「${out.into.label}」에 합쳤습니다 — ` +
        `옮긴 것 ${out.moved}건` +
        (out.dropped ? `, 이미 붙어 있어 한 겹으로 둔 것 ${out.dropped}건` : '') +
        '.',
    )
    setRound((n) => n + 1)
  }

  return (
    <section className="space-y-3" aria-labelledby="similar-tags-title">
      <div className="flex items-center gap-2">
        <h2 id="similar-tags-title" className="text-base font-semibold">
          비슷한 태그 정리
        </h2>
        <Button size="sm" variant="outline" onClick={() => setRound((n) => n + 1)} disabled={found.loading}>
          다시 찾기
        </Button>
      </div>
      <p className="text-muted-foreground text-sm">
        같은 타입에서 이름이 띄어쓰기 · 이음표 · 대소문자만 다른 태그입니다. 합치면 붙은 것이 남길 태그로 옮겨 가고,
        합친 이름은 남길 태그의 별칭이 되어 같은 표기로 다시 붙여도 남길 태그로 붙습니다. 이 규칙에 안 걸리는 것은
        태그 객체 화면의 「합치기」를 쓰십시오.
      </p>
      {done && <p className="text-sm">{done}</p>}
      <ErrorNotice error={found.error} />
      {notes.map((one) => (
        <p key={one} className="text-muted-foreground text-xs">
          {one}
        </p>
      ))}
      {found.loading && !found.data ? (
        <p className="text-muted-foreground text-sm">찾는 중…</p>
      ) : groups.length === 0 ? (
        <p className="text-muted-foreground text-sm">비슷한 태그가 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {groups.map((group) => (
            <GroupCard key={groupKey(group)} group={group} onMerged={merged} />
          ))}
        </ul>
      )}
    </section>
  )
}

function GroupCard({
  group,
  onMerged,
}: {
  group: SimilarGroup
  onMerged: (out: MergedTags, names: string[]) => void
}) {
  const [keep, setKeep] = useState(group.keep)
  /** 합칠 것에서 뺀 것 — 규칙이 묶었지만 다른 말인 것. */
  const [left, setLeft] = useState<Set<string>>(new Set())
  const [asking, setAsking] = useState(false)
  const kept = group.members.find((one) => one.object_id === keep) ?? group.members[0]
  const merging = group.members.filter((one) => one.object_id !== keep && !left.has(one.object_id))
  const names = merging.map((one) => one.label)
  const moving = merging.reduce((sum, one) => sum + one.uses, 0)

  function toggle(id: string) {
    setLeft((before) => {
      const next = new Set(before)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <li className="space-y-2 rounded border p-3">
      <div className="text-muted-foreground text-xs">{group.type_label}</div>
      <table className="text-sm">
        <thead className="text-muted-foreground text-xs">
          <tr>
            <th className="pr-3 text-left font-normal">남길 것</th>
            <th className="pr-3 text-left font-normal">합칠 것</th>
            <th className="pr-3 text-left font-normal">이름</th>
            <th className="text-right font-normal">붙은 수</th>
          </tr>
        </thead>
        <tbody>
          {group.members.map((one) => (
            <tr key={one.object_id}>
              <td className="pr-3">
                <input
                  type="radio"
                  name={`keep-${groupKey(group)}`}
                  checked={keep === one.object_id}
                  onChange={() => setKeep(one.object_id)}
                  aria-label={`${one.label} 남기기`}
                />
              </td>
              <td className="pr-3">
                <input
                  type="checkbox"
                  checked={keep !== one.object_id && !left.has(one.object_id)}
                  disabled={keep === one.object_id}
                  onChange={() => toggle(one.object_id)}
                  aria-label={`${one.label} 합치기`}
                />
              </td>
              <td className="pr-3">
                <Link to={`/o/${group.type_slug}/${one.object_id}`} className="hover:underline">
                  {one.label}
                </Link>
                {one.key && <span className="text-muted-foreground ml-1 text-xs">{one.key}</span>}
              </td>
              <td className="text-right tabular-nums">{one.uses}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" disabled={merging.length === 0} onClick={() => setAsking(true)}>
        {merging.length}개를 「{kept.label}」에 합치기
      </Button>
      <ConfirmDialog
        open={asking}
        title={`「${kept.label}」에 합치시겠습니까?`}
        description={
          `${quoted(names)}${particle(names[names.length - 1] ?? '', '이', '가')} 지워지고, 붙어 있던 ` +
          `${moving}건이 「${kept.label}」에 옮겨 붙습니다(이미 둘 다 붙은 행은 한 겹으로). 지운 이름은 ` +
          `「${kept.label}」의 별칭이 됩니다. 객체 이력에 남지만 되돌리는 버튼은 없습니다.`
        }
        confirmLabel="합치기"
        destructive
        onConfirm={async () => {
          const out = await tagsApi.merge(
            keep,
            merging.map((one) => one.object_id),
          )
          onMerged(out, names)
        }}
        onClose={() => setAsking(false)}
      />
    </li>
  )
}
