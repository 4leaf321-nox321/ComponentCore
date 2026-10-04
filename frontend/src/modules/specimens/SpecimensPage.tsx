/**
 * **시험 규격** — 공개 규격(ASTM · ISO)과 사내 규격의 프리셋 목록. 규격을 골라 시편 · 시험 지그 ·
 * 해석 조건이 붙은 내 작업을 만든다. 사내 규격은 시스템 관리자가 공개 규격을 복사해 고친다
 * (판정은 서버 — 여기서는 단추만 가린다).
 *
 * 값마다 출처가 있고, 규격서와 대조하기 전이면 「검토 필요」 로 보인다. 공개 규격의 값을 고치는
 * 길은 코드(릴리스)뿐이다 — 틀린 값을 찾으면 사내 규격으로 복사해 바로 쓰고, 코드는 따로 고친다.
 */

import { useState } from 'react'

import { PresetDialog } from '@/modules/specimens/PresetDialog'
import { SpecimenDialog } from '@/modules/specimens/SpecimenDialog'
import { loadSpanText, radiusText, spanText, specimensApi } from '@/modules/specimens/api'
import type { PresetRow } from '@/modules/specimens/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

type Editing = { row: PresetRow; mode: 'copy' | 'edit' }

export default function SpecimensPage() {
  const { user } = useAuth()
  const admin = isSystemAdmin(user)
  const presets = useResource(() => specimensApi.list('bending'), [])
  const [making, setMaking] = useState<PresetRow | null>(null)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [removing, setRemoving] = useState<PresetRow | null>(null)
  const rows = presets.data ?? []

  return (
    <div>
      <PageHeader
        title="시험 규격"
        description="ASTM·ISO 공개 규격과 사내 규격의 시편, 시험 지그, 해석 조건입니다. 규격을 선택하여 해석 모델을 내 작업으로 생성합니다. 사내 규격은 관리자가 공개 규격을 복사하여 등록합니다."
      />
      <h2 className="mb-2 text-sm font-semibold">굽힘</h2>
      <ErrorNotice error={presets.error} className="mb-4" />
      {rows.length === 0 && !presets.loading ? (
        <EmptyState title="시험 규격이 없습니다" hint="서버 버전을 확인하십시오." />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>규격</TableHead>
              <TableHead>방식</TableHead>
              <TableHead>시편 (mm)</TableHead>
              <TableHead>지지 간격</TableHead>
              <TableHead>반지름 (지지 / 노즈)</TableHead>
              <TableHead>상태</TableHead>
              <TableHead className="text-right">작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const preset = row.preset
              const inner = loadSpanText(preset)
              return (
                <TableRow key={row.id}>
                  <TableCell>
                    <span className="font-medium">{row.name}</span>
                    {row.origin === 'internal' && (
                      <Badge variant="secondary" className="ml-1">
                        사내
                      </Badge>
                    )}
                    <p className="text-muted-foreground max-w-md text-xs">{preset.source}</p>
                    {preset.note && <p className="text-muted-foreground max-w-md text-xs">{preset.note}</p>}
                  </TableCell>
                  <TableCell>{preset.setup.points}점</TableCell>
                  <TableCell className="font-mono text-xs">
                    {preset.specimen.length} × {preset.specimen.width} × {preset.specimen.thickness}
                  </TableCell>
                  <TableCell className="text-xs">
                    {spanText(preset)}
                    {inner && <p className="text-muted-foreground">하중 간격 {inner}</p>}
                  </TableCell>
                  <TableCell className="text-xs">
                    {radiusText(preset.setup.support_radius)} / {radiusText(preset.setup.nose_radius)}
                  </TableCell>
                  <TableCell>
                    {preset.verified ? <Badge variant="outline">대조 완료</Badge> : <Badge variant="destructive">검토 필요</Badge>}
                  </TableCell>
                  <TableCell className="space-x-1 text-right whitespace-nowrap">
                    <Button size="sm" onClick={() => setMaking(row)}>
                      시편 생성
                    </Button>
                    {admin && row.origin === 'builtin' && (
                      <Button size="sm" variant="outline" onClick={() => setEditing({ row, mode: 'copy' })}>
                        사내 규격으로 복사
                      </Button>
                    )}
                    {admin && row.origin === 'internal' && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => setEditing({ row, mode: 'edit' })}>
                          수정
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setRemoving(row)}>
                          삭제
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
      {making && <SpecimenDialog row={making} onClose={() => setMaking(null)} />}
      {editing && (
        <PresetDialog
          row={editing.row}
          mode={editing.mode}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            presets.reload()
          }}
        />
      )}
      <ConfirmDialog
        open={removing !== null}
        title="사내 규격 삭제"
        description={`‘${removing?.name ?? ''}’을(를) 삭제합니다. 이 규격으로 이미 생성한 작업과 지그는 그대로 유지됩니다.`}
        confirmLabel="삭제"
        destructive
        onConfirm={async () => {
          if (!removing) return
          await specimensApi.remove(removing.id)
          presets.reload()
        }}
        onClose={() => setRemoving(null)}
      />
    </div>
  )
}
