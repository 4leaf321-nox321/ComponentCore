/**
 * 부품 카탈로그 — 승격된 부품. 로그인한 누구나 보고, 폴더로 나눠 둔다(옮기는 것은 올린 사람 · 관리자).
 * **공용 조립**(`kind='assembly'`)도 같은 화면이다 — 버전 · 폴더 · 태그 · 복사가 똑같다. 규격 부품 · 지그 수는
 * 조립에 뜻이 없어 뺀다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { partsApi } from '@/modules/parts/api'
import type { PartKind } from '@/modules/parts/api'
import { StandardExportButton, StandardImportDialog } from '@/modules/parts/StandardTransfer'
import { useAuth } from '@/shared/auth/AuthContext'
import { canEditProject, isSystemAdmin } from '@/shared/auth/roles'
import { ChosenBar, FolderCrumbs, FolderDialogs, FolderSelect, PickAll, PickBox, RowFolder } from '@/shared/folders/FolderParts'
import { FolderTree } from '@/shared/folders/FolderTree'
import { useFolderSpace } from '@/shared/folders/useFolderSpace'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { SearchBox } from '@/shared/components/SearchBox'
import { PageHeader } from '@/shared/components/PageHeader'
import { Pagination } from '@/shared/components/Pagination'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useDisplay } from '@/shared/api/display'
import { LinkFilter } from '@/modules/objects/LinkFilter'
import type { LinkChoice } from '@/modules/objects/LinkFilter'
import { tagsApi } from '@/modules/tagging/api'
import { TypedTagFilter } from '@/modules/tagging/TypedTagFilter'
import { describeShape, ShapeFilter, shapeConditionCount } from '@/shared/components/ShapeFilter'
import type { ShapeQuery } from '@/shared/components/ShapeFilter'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'


/** 종류마다 화면의 말 — 부품 · 공용 조립. */
const WORDS: Record<PartKind, { title: string; noun: string; all: string; description: string; empty: string; base: string }> = {
  part: {
    title: '부품',
    noun: '부품',
    all: '전체 부품',
    description: '내 작업에서 등록된 부품입니다. 등록된 버전은 변경할 수 없으며, 수정하려면 내 작업 공간으로 복사하십시오.',
    empty: '내 작업에서 ‘공용 부품으로 등록’을 실행하면 이 목록에 표시됩니다.',
    base: '/parts',
  },
  assembly: {
    title: '조립',
    noun: '조립',
    all: '전체 조립',
    description:
      '내 작업에서 등록된 조립입니다. 구성품은 공용 부품 · 지그의 정해진 버전을 가리킵니다. 수정하려면 내 작업 공간으로 복사하십시오.',
    empty: '조립 작업에서 ‘공용 조립으로 등록’을 실행하면 이 목록에 표시됩니다.',
    base: '/assemblies',
  },
}

export default function PartsPage({ kind = 'part' }: { kind?: PartKind }) {
  const words = WORDS[kind]
  const assembly = kind === 'assembly'
  const [offset, setOffset] = useState(0)
  const [q, setQ] = useState('')
  /** 고른 꼬리표 — 빈 문자열이면 안 거른다. */
  const [tagId, setTagId] = useState('')
  /** 기준정보로 — 「적용 모델 = P5」. */
  const [linked, setLinked] = useState<LinkChoice | null>(null)
  /** 형상 조건 — 「M6 구멍이 있는 판」 · 「이 상자 안에 드는 것」. */
  const [shape, setShape] = useState<ShapeQuery>({})
  /** 규격 부품만 — 지그 생성기가 고르는 받침 · 위치 핀 · 토글 클램프. */
  const [standardOnly, setStandardOnly] = useState(false)
  /** 규격 부품 묶음 가져오기 창 — 시스템 관리자만. */
  const [importing, setImporting] = useState(false)
  const PAGE = useDisplay().list_page_size
  const space = useFolderSpace(assembly ? 'assemblies' : 'parts', { ...partsApi, folders: () => partsApi.folders(kind) }, { onRefilter: () => setOffset(0) })
  const page = useResource(
    () =>
      partsApi.list(offset, PAGE, q, '', {
        kind,
        folder: space.folder,
        shape,
        standard: standardOnly ? 'any' : '',
        tagId,
        linkObject: linked?.objectId,
        linkRelation: linked?.relation,
      }),
    [offset, q, tagId, linked, shape, PAGE, space.folder, space.version, standardOnly, kind],
  )
  const tags = useResource(() => tagsApi.used('part'), [page.data])
  const rows = page.data?.items ?? []
  /** 옮길 수 있는 줄 — 올린 사람 · 관리자. 판정은 서버가 다시 한다. */
  const { user } = useAuth()
  const movable = (ownerId: string) => canEditProject(user, ownerId)
  /** 규격 부품 내보내기 · 가져오기 — 표시일 뿐이다(판정은 서버). */
  const admin = isSystemAdmin(user)
  const chosenStandard = rows.filter((row) => space.chosen.has(row.id) && row.standard).map((row) => row.id)
  const filtered = Boolean(q || tagId || linked || standardOnly || space.folder !== null || shapeConditionCount(shape) > 0)

  return (
    <div>
      <PageHeader title={words.title} description={words.description} />
      <div className="flex gap-4">
        {/* 폴더 — 넓은 화면에서 왼쪽에. 좁으면 위의 고르개로. */}
        <aside className="hidden w-56 shrink-0 md:block">
          <FolderTree space={space} allLabel={words.all} noun={words.noun} />
        </aside>
        <div className="min-w-0 flex-1">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FolderSelect space={space} allLabel={words.all} />
        <SearchBox value={q} onChange={(next) => { setQ(next); setOffset(0) }} />
        <TypedTagFilter tags={tags.data ?? []} value={tagId} onChange={(next) => { setTagId(next); setOffset(0) }} />
        <LinkFilter base="parts" value={linked} onChange={(next) => { setLinked(next); setOffset(0) }} />
        <ShapeFilter value={shape} onChange={(next) => { setShape(next); setOffset(0) }} />
        {!assembly && (
        <Button
          size="sm"
          variant={standardOnly ? 'default' : 'outline'}
          aria-pressed={standardOnly}
          onClick={() => {
            setStandardOnly(!standardOnly)
            setOffset(0)
          }}
        >
          규격 부품
        </Button>
        )}
        {admin && !assembly && (
          <Button size="sm" variant="outline" onClick={() => setImporting(true)}>
            규격 부품 가져오기
          </Button>
        )}
      </div>
      <FolderCrumbs space={space} allLabel={words.all} />
      <ChosenBar space={space}>{admin && <StandardExportButton ids={chosenStandard} />}</ChosenBar>
      <ErrorNotice error={page.error} className="mb-4" />
      {rows.length === 0 && !page.loading ? (
        filtered ? (
          <EmptyState title={`조건에 맞는 ${words.noun}이 없습니다`} hint={`검색어, 태그, 폴더, 형상 조건을 변경하십시오. 빈 폴더에는 ${words.noun}을 끌어다 놓아 이동할 수 있습니다.`} />
        ) : (
          <EmptyState title={`등록된 ${words.noun}이 없습니다`} hint={words.empty} />
        )
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <PickAll space={space} ids={rows.filter((row) => movable(row.owner_id)).map((row) => row.id)} />
                </TableHead>
                <TableHead>이름</TableHead>
                <TableHead>버전</TableHead>
                {!assembly && <TableHead>지그</TableHead>}
                <TableHead>등록자</TableHead>
                <TableHead>수정일</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.id}
                  draggable={movable(row.owner_id)}
                  onDragStart={(event) => space.startDrag(event, row.id)}
                  data-state={space.chosen.has(row.id) ? 'selected' : undefined}
                >
                  <TableCell>
                    <PickBox space={space} id={row.id} name={row.name} disabled={!movable(row.owner_id)} />
                  </TableCell>
                  <TableCell>
                    <Link to={`${words.base}/${row.id}`} className="font-medium hover:underline">
                      {row.name}
                    </Link>
                    {row.standard && <span className="ml-1 rounded border px-1 text-[10px]" title="규격 부품 — 지그 생성기가 고를 수 있습니다.">규격 {row.standard.part_no}</span>}
                    <RowFolder space={space} folder={row.folder} />
                    {row.description && <p className="text-muted-foreground max-w-md truncate text-xs">{row.description}</p>}
                    {row.shape && <p className="text-muted-foreground font-mono text-[11px]">{describeShape(row.shape)}</p>}
                  </TableCell>
                  <TableCell>v{row.current_version}</TableCell>
                  {!assembly && <TableCell>{row.jig_count}</TableCell>}
                  <TableCell>{row.owner_name}</TableCell>
                  <TableCell className="text-sm">{shownDateTime(row.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {page.data && (
            <Pagination total={page.data.total} limit={page.data.limit} offset={page.data.offset} onChange={(next) => { setOffset(next); space.setChosen(new Set()) }} />
          )}
        </>
      )}
        </div>
      </div>
      <FolderDialogs space={space} noun={words.noun} shared />
      {importing && (
        <StandardImportDialog
          onClose={() => setImporting(false)}
          onDone={() => {
            space.refresh()
            page.reload()
          }}
        />
      )}
    </div>
  )
}
