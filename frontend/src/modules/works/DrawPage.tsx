/**
 * 새 작업 — 부품이나 지그를 그려 **새 작업으로** 저장하는 곳. 빈 화면 · 템플릿 · 기존 작업의 사본 ·
 * STEP 에서 시작한다.
 *
 * 저장 전에는 아무것도 남지 않는다. 저장하면 작업이 생기고 그 화면으로 간다 — 거기서 계속 고치고
 * (덮어 저장은 거기 「수정」 의 일), 공용 부품 · 지그로 승격한다.
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
  /**
   * 기존 작업을 불러왔으면 그 이름 · 종류를 기본값으로 — 하지만 **여기서는 늘 새 작업**이다.
   * 기존 작업을 덮어 고치는 일은 「내 작업 › 수정」 이 한다. 한 화면이 두 가지를 하면 어느
   * 쪽인지 매번 물어야 한다.
   */
  const [origin, setOrigin] = useState<{ id: string; name: string; kind: WorkKind } | null>(null)
  const [recipe, setRecipe] = useState<Recipe | null>({
    version: 1,
    nodes: [],
  })
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [params, setParams] = useSearchParams()

  // 템플릿 공간에서 「새 작업으로 열기」 로 왔을 때 — 주소의 id 를 받아 한 번만 싣는다.
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
        title="새 작업"
        description="부품이나 지그를 그려 새 작업으로 저장합니다. 빈 화면에서 그리거나 「파일」 탭에서 템플릿 · 기존 작업(사본) · STEP 을 엽니다. 저장하기 전에는 아무것도 남지 않습니다."
        actions={
          <Button variant="outline" onClick={() => navigate('/draw/jig-from-part')}>
            부품에서 지그 생성
          </Button>
        }
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
              // 기존 작업은 **사본**으로 시작한다 — 이름을 미리 「사본」 으로 두어 원본이 남는다는 걸 보인다.
              setOrigin(work ?? null)
              if (work) {
                setName(`${work.name} 사본`)
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
                내 공간에 <b>새 작업</b>이 생기고 버전 1 이 평가됩니다. 남에게는 승격해야 보입니다.
                {origin && ` 불러온 「${origin.name}」 은 그대로 남습니다 — 그것을 고치려면 내 작업에서 「수정」 하세요.`}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="work-name">작업 이름</Label>
              <Input id="work-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
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
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setSaving(false)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy || !name.trim()}>
                {busy ? '저장 중…' : '새 작업으로 저장'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
