/**
 * 그리기 — 새 작업의 시작. 템플릿에서 그리거나 STEP 을 올린다.
 *
 * 저장 전에는 아무것도 남지 않는다. 「내 작업으로 저장」 하면 작업이 생기고 그 화면으로 간다 —
 * 거기서 계속 고치고, 지그를 만들고, 부품 · 지그로 승격한다.
 */

import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import type { Recipe } from '@/modules/cad/api'
import { saveRecipeAs } from '@/modules/cad/download'
import { templatesApi } from '@/modules/templates/api'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'
import { SaveTemplateDialog } from '@/modules/templates/SaveTemplateDialog'
import { worksApi } from '@/modules/works/api'
import type { WorkKind } from '@/modules/works/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 어디서 왔는지 — 저장할 때 버전 메모가 된다. */
type Origin = { source: 'manual' | 'template' | 'copy'; label: string }

export default function DrawPage() {
  const navigate = useNavigate()
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [noteOf, setNoteOf] = useState<Origin>({
    source: 'manual',
    label: '처음부터 그림',
  })
  /** 부품을 그린 것인지 지그를 그린 것인지 — 저장할 때 고른다. 그리는 방법은 같다. */
  const [kind, setKind] = useState<WorkKind>('part')
  /** 기존 작업을 불러와 고치는 중이면 그 작업 — **덮어 저장**할 수 있는 근거. */
  const [origin, setOrigin] = useState<{ id: string; name: string; kind: WorkKind } | null>(null)
  /** 어디에 저장하나 — 불러온 작업에 새 버전으로, 또는 새 작업으로. */
  const [target, setTarget] = useState<'overwrite' | 'new'>('new')
  const [recipe, setRecipe] = useState<Recipe | null>({
    version: 1,
    nodes: [],
  })
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [params, setParams] = useSearchParams()

  // 템플릿 공간에서 「그리기에서 열기」 로 왔을 때 — 주소의 id 를 받아 한 번만 싣는다.
  const wanted = params.get('template')
  useEffect(() => {
    if (!wanted) return
    let alive = true
    void (async () => {
      try {
        const template = await templatesApi.get(wanted)
        if (!alive) return
        setRecipe(template.recipe)
        setName(template.name)
        setNoteOf({ source: 'template', label: `${template.name} 템플릿에서` })
      } catch (caught) {
        if (alive) setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      } finally {
        // 주소를 비워 둔다 — 새로고침이나 「새로」 뒤에 다시 실리면 사람이 놀란다.
        if (alive) setParams({}, { replace: true })
      }
    })()
    return () => {
      alive = false
    }
  }, [wanted, setParams])

  async function download(format: 'step' | 'stl' | 'dxf' | 'svg') {
    if (!recipe) return
    setError(null)
    try {
      await saveRecipeAs(recipe, format, name || 'model')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  async function save() {
    if (!recipe) return
    setBusy(true)
    setError(null)
    try {
      if (target === 'overwrite' && origin) {
        // 불러온 작업에 **새 버전**으로 — 덮어쓰지만 옛 버전은 남는다(되돌릴 수 있다).
        await worksApi.addVersion(origin.id, { recipe, source: 'manual', note: noteOf.label })
        navigate(`/works/${origin.id}`)
        return
      }
      const made = await worksApi.create({
        name,
        recipe,
        kind,
        source: noteOf.source,
        note: noteOf.label,
      })
      navigate(`/works/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  async function startFromStep(file: File) {
    setBusy(true)
    setError(null)
    try {
      const made = await worksApi.createFromStep(file)
      navigate(`/works/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="그리기"
        description="빈 화면에서 그리거나 「파일」 탭에서 템플릿 · 기존 작업 · STEP 을 엽니다. 저장하기 전에는 아무것도 남지 않습니다."
      />
      <ErrorNotice error={error} />

      {recipe && (
        <RecipeEditor
          value={recipe}
          onChange={setRecipe}
          file={{
            save: { label: '저장', run: () => setSaving(true) },
            saveTemplate: () => setSavingTemplate(true),
            download: (format) => void download(format),
            importStep: { label: 'STEP 열기', run: (picked) => void startFromStep(picked), busy },
            onLoaded: (label, source, work) => {
              setNoteOf(source === 'copy' ? { source, label: `${label} 에서 복사` } : { source, label: `${label} 템플릿에서` })
              // 기존 작업을 불러왔으면 그 작업에 덮어 저장하는 것이 기본이다 — 사람은 「고치는 중」 이다.
              setOrigin(work ?? null)
              setTarget(work ? 'overwrite' : 'new')
              if (work) {
                setName(work.name)
                setKind(work.kind === 'assembly' ? 'part' : work.kind)
              }
            },
          }}
        />
      )}

      {recipe && <SaveTemplateDialog key={String(savingTemplate)} open={savingTemplate} recipe={recipe} onClose={() => setSavingTemplate(false)} />}

      <Dialog open={saving} onOpenChange={(open) => !open && !busy && setSaving(false)}>
        <DialogContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void save()
            }}
            className="space-y-4"
          >
            <DialogHeader>
              <DialogTitle>저장</DialogTitle>
              <DialogDescription>
                {origin
                  ? '불러온 작업에 덮어 저장할지, 새 작업으로 따로 저장할지 고릅니다.'
                  : '내 공간에 작업이 생기고 버전 1 이 평가됩니다. 남에게는 승격해야 보입니다.'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              {origin && (
                <div className="space-y-1">
                  <Label>어디에 저장합니까</Label>
                  <div className="grid gap-1">
                    {(
                      [
                        { value: 'overwrite', label: `「${origin.name}」 에 덮어 저장`, hint: '그 작업에 새 버전이 붙습니다. 옛 버전은 남아 되돌릴 수 있습니다.' },
                        { value: 'new', label: '새 작업으로 저장', hint: '원본은 그대로 두고 다른 이름의 작업을 만듭니다.' },
                      ] as const
                    ).map((one) => (
                      <button
                        key={one.value}
                        type="button"
                        onClick={() => setTarget(one.value)}
                        aria-pressed={target === one.value}
                        className={`rounded-md border px-3 py-2 text-left text-sm ${
                          target === one.value ? 'border-primary bg-primary/5' : 'hover:bg-accent'
                        }`}
                      >
                        <div className="font-medium">{one.label}</div>
                        <div className="text-muted-foreground text-xs">{one.hint}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {target === 'new' && (
                <>
              <Label htmlFor="work-name">작업 이름</Label>
              <Input id="work-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
                </>
              )}
              {target === 'new' && (
              <div className="space-y-1 pt-2">
                <Label>무엇으로 저장합니까</Label>
                <div className="flex gap-1">
                  {(
                    [
                      { value: 'part', label: '부품 · 제품' },
                      { value: 'jig', label: '지그' },
                    ] as const
                  ).map((one) => (
                    <button
                      key={one.value}
                      type="button"
                      onClick={() => setKind(one.value)}
                      aria-pressed={kind === one.value}
                      className={`flex-1 rounded-md border px-2 py-1.5 text-sm ${
                        kind === one.value ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
                      }`}
                    >
                      {one.label}
                    </button>
                  ))}
                </div>
                <p className="text-muted-foreground text-xs">
                  부품과 지그는 <b>서로 관계없는 각자의 도면</b>입니다. 둘을 함께 놓아 보려면 「조립」 에서 가져다 씁니다. 종류는 나중에 바꿀 수 있습니다.
                </p>
              </div>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setSaving(false)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy || (target === 'new' && !name.trim())}>
                {busy ? '저장 중…' : target === 'overwrite' && origin ? `「${origin.name}」 에 저장` : '새 작업으로 저장'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
