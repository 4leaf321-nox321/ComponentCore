/**
 * 태그로 쓰는 타입 — **어느 타입에서 태그를 고르고, 어느 타입은 붙이는 사람이 늘리나**(ADR 0011).
 *
 * 작업 · 부품 · 지그의 태그 줄은 여기서 고른 타입만 보인다. 「늘리기」 면 붙이는 사람 누구나 그
 * 타입에 새 객체(전역)를 만든다 — 태그를 달수록 어휘가 쌓인다. 「고르기」 는 있는 것에서만 고른다
 * (정해 둔 목록 — 고객사 · 시험 규격). 「일반 태그」 는 끌 수 없다: 타입을 안 고른 태그와 옛
 * 꼬리표가 가는 곳이다.
 *
 * 끈 타입의 태그는 붙은 채 남는다 — 새로 고르는 자리에서만 빠진다.
 *
 * 아래 「비슷한 태그 정리」 는 늘리기로 갈린 이름(「굽힘시험」 · 「굽힘 시험」)을 하나로 합친다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { useOntology } from '@/modules/ontology/OntologyLayout'
import { SimilarTagsPanel } from '@/modules/tagging/SimilarTagsPanel'
import { tagsApi } from '@/modules/tagging/api'
import type { TagMode, TagSetting } from '@/modules/tagging/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

const MODES: { value: TagMode; label: string }[] = [
  { value: 'off', label: '태그로 안 씀' },
  { value: 'pick', label: '고르기' },
  { value: 'grow', label: '고르기 · 늘리기' },
]

export default function OntologyTagsPage() {
  const { reload } = useOntology()
  const loaded = useResource(() => tagsApi.settings(), [])
  const [fresh, setFresh] = useState<TagSetting[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const rows = fresh ?? (Array.isArray(loaded.data) ? loaded.data : [])

  async function change(slug: string, mode: TagMode) {
    setBusy(slug)
    setError(null)
    try {
      setFresh(await tagsApi.setMode(slug, mode))
      reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(null)
    }
  }

  if (loaded.error) return <ErrorNotice error={loaded.error} />
  if (!loaded.data && !fresh) return <p className="text-muted-foreground text-sm">조회 중…</p>

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        작업 · 부품 · 지그의 태그는 온톨로지의 객체입니다. 여기서 고른 타입이 태그 줄에 나타납니다. 「고르기 · 늘리기」
        타입은 붙이는 사람 누구나 새 이름을 만들 수 있고, 만든 객체는 모두가 봅니다(전역). 원 표를 비추는 타입(부서 ·
        계정 · 부품 …)은 태그가 아니라 <Link to="../relations" className="underline">관계</Link>로 잇습니다.
      </p>
      <ErrorNotice error={error} />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>타입</TableHead>
            <TableHead className="w-48">태그로</TableHead>
            <TableHead>참고</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.slug}>
              <TableCell>
                <Link to={`/o/${row.slug}`} className="hover:underline">
                  {row.label}
                </Link>{' '}
                <span className="text-muted-foreground text-xs">{row.slug}</span>
              </TableCell>
              <TableCell>
                <select
                  aria-label={`${row.label} 태그 방식`}
                  value={row.mode}
                  onChange={(e) => void change(row.slug, e.target.value as TagMode)}
                  disabled={busy !== null}
                  className="bg-background text-foreground h-8 rounded border px-2 text-sm"
                >
                  {MODES.filter((one) => !(row.is_default && one.value === 'off')).map((one) => (
                    <option key={one.value} value={one.value}>
                      {one.label}
                    </option>
                  ))}
                </select>
              </TableCell>
              <TableCell className="text-muted-foreground text-xs">
                {[
                  row.is_default ? '기본 — 타입을 안 고른 태그가 여기로' : '',
                  row.managed_by ? `${row.managed_by} 관리 — 고르기만` : '',
                  row.note,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <SimilarTagsPanel />
    </div>
  )
}
