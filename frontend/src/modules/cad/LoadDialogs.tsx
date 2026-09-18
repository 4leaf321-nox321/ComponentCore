/**
 * 「파일」 탭의 불러오기 — 레시피(내장 · 저장 템플릿)와 기존 작업. 편집기 안에서 열리고 고르면 지금
 * 레시피를 바꾼다. 지금 그린 것이 있으면 한 번 묻는다.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'
import { worksApi } from '@/modules/works/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

type Loaded = { recipe: Recipe; label: string; source: 'template' | 'copy' }

function Row({ title, hint, action }: { title: React.ReactNode; hint?: React.ReactNode; action: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-md border px-3 py-2 text-sm">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{title}</p>
        {hint && <p className="text-muted-foreground truncate text-xs">{hint}</p>}
      </div>
      {action}
    </div>
  )
}

export function LoadRecipeDialog({ open, onClose, onLoad }: { open: boolean; onClose: () => void; onLoad: (loaded: Loaded) => void }) {
  const schema = useResource(() => cadApi.schema(), [open])
  const saved = useResource(() => cadApi.templates(), [open])
  const [busy, setBusy] = useState<string | null>(null)
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>레시피 불러오기</DialogTitle>
          <DialogDescription>내장 템플릿과 저장한 템플릿. 고르면 지금 레시피를 바꿉니다.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <p className="text-muted-foreground text-xs">내장</p>
            {Object.entries(schema.data?.template_labels ?? {}).map(([kind, label]) => (
              <Row
                key={kind}
                title={label}
                action={
                  <Button
                    size="sm"
                    onClick={() =>
                      onLoad({
                        recipe: structuredClone(schema.data!.templates[kind]),
                        label,
                        source: 'template',
                      })
                    }
                  >
                    불러오기
                  </Button>
                }
              />
            ))}
          </div>
          <div className="space-y-1">
            <p className="text-muted-foreground text-xs">저장한 템플릿</p>
            {(saved.data ?? []).length === 0 && <p className="text-muted-foreground text-xs">아직 없습니다 — 「템플릿으로 저장」 으로 만듭니다.</p>}
            {(saved.data ?? []).map((t) => (
              <Row
                key={t.id}
                title={
                  <>
                    {t.name} <span className="text-muted-foreground text-xs">{t.mine ? '내 것' : `공용 · ${t.owner_name}`}</span>
                  </>
                }
                hint={t.description || shownDateTime(t.updated_at)}
                action={
                  <div className="flex gap-1">
                    {t.mine && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy === t.id}
                        onClick={async () => {
                          if (!window.confirm(`템플릿 「${t.name}」 을 지웁니까?`)) return
                          setBusy(t.id)
                          await cadApi.removeTemplate(t.id)
                          setBusy(null)
                          saved.reload()
                        }}
                      >
                        지우기
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={() =>
                        onLoad({
                          recipe: structuredClone(t.recipe),
                          label: t.name,
                          source: 'template',
                        })
                      }
                    >
                      불러오기
                    </Button>
                  </div>
                }
              />
            ))}
          </div>
          <ErrorNotice error={schema.error ?? saved.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function LoadWorkDialog({ open, onClose, onLoad, currentWorkId }: { open: boolean; onClose: () => void; onLoad: (loaded: Loaded) => void; currentWorkId?: string }) {
  const works = useResource(() => worksApi.list(0, 100), [open])
  const [busy, setBusy] = useState<string | null>(null)
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>기존 작업 불러오기</DialogTitle>
          <DialogDescription>「레시피 가져오기」 는 그 작업의 현재 부품을 여기로 복사합니다(원본은 그대로). 「열기」 는 그 작업으로 갑니다.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          {(works.data?.items ?? [])
            .filter((w) => w.id !== currentWorkId)
            .map((w) => (
              <Row
                key={w.id}
                title={w.name}
                hint={`부품 v${w.current_version} · 지그 ${w.jig_run_count}회 · ${shownDateTime(w.updated_at)}`}
                action={
                  <div className="flex gap-1">
                    <Button asChild size="sm" variant="ghost">
                      <Link to={`/works/${w.id}`}>열기</Link>
                    </Button>
                    <Button
                      size="sm"
                      disabled={busy === w.id || w.current_version === 0}
                      onClick={async () => {
                        setBusy(w.id)
                        try {
                          const full = await worksApi.get(w.id)
                          if (full.current)
                            onLoad({
                              recipe: structuredClone(full.current.recipe),
                              label: `${w.name} v${full.current.number}`,
                              source: 'copy',
                            })
                        } finally {
                          setBusy(null)
                        }
                      }}
                    >
                      레시피 가져오기
                    </Button>
                  </div>
                }
              />
            ))}
          {(works.data?.items ?? []).length === 0 && <p className="text-muted-foreground text-xs">작업이 없습니다.</p>}
          <ErrorNotice error={works.error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
