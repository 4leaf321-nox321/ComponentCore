/**
 * 내 작업 하나.
 *
 * **부품이든 지그든 그리는 방법은 같다** — 도면 한 줄기다. 다른 것은 작업의 **종류**뿐이고,
 * 그것이 「탭」 과 「어디로 승격하나」 와 「덤으로 무엇을 쓸 수 있나」 를 정한다:
 *
 * - 부품: 탭 = 도면, 승격 = **공용 부품**, 덤 = 지그 생성기(이 부품을 잡는 지그를 규칙으로
 *   만들어 준다).
 * - 지그: 탭 = 도면, 승격 = **공용 지그**.
 * - 조립: 탭 = 조립. 부품 · 지그를 가져다 놓는다(승격은 없다).
 *
 * 여러 벌을 만드는 일(실험계획)은 **여기서 하지 않는다** — 실험계획 공간이 이 도면을 대상으로
 * 고른다. 도면을 저장할 때까지 하는 일은 그리기와 변수 심기뿐이다.
 *
 * 그래서 「이 도면을 무엇으로 올릴까」 를 물을 일이 없다 — 종류가 이미 답이다.
 */

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import type { Recipe } from '@/modules/cad/api'
import { AssemblyEditor } from '@/modules/works/AssemblyEditor'
import { GeometryJobView } from '@/modules/cad/GeometryJobView'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'
import { ConditionsPanel } from '@/modules/conditions/ConditionsPanel'
import { conditionsApi } from '@/modules/conditions/api'
import { saveRecipeAs } from '@/modules/cad/download'
import { SaveTemplateDialog } from '@/modules/templates/SaveTemplateDialog'
import { JigResultView } from '@/modules/jigs/JigResultView'
import { jobsApi } from '@/modules/jobs/api'
import { worksApi } from '@/modules/works/api'
import type { WorkVersion } from '@/modules/works/api'
import { ApiError, downloadFile } from '@/shared/api/client'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { TagEditor } from '@/modules/works/TagEditor'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

const SOURCE_LABELS: Record<string, string> = {
  template: '템플릿',
  manual: '직접',
  ai: 'AI',
  import: 'STEP',
  restore: '되돌림',
  copy: '복사',
  generated: '생성기',
}

export default function WorkPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const work = useResource(() => worksApi.get(id), [id])
  const versions = useResource(() => worksApi.versions(id), [id])
  /** 지그 작업이 부품에서 생성됐으면 그 생성 기록 — 계획 · 간섭 검사를 되짚어 본다. */
  const runs = useResource(() => worksApi.jigRuns(id), [id])
  const allTags = useResource(() => worksApi.tags(), [])

  const [tab, setTab] = useState('geometry')
  const [selectedVersion, setSelectedVersion] = useState<WorkVersion | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Recipe | null>(null)
  const [note, setNote] = useState('')
  const [promoting, setPromoting] = useState<'part' | 'jig-recipe' | null>(null)
  const [promoteName, setPromoteName] = useState('')
  const [promoteNote, setPromoteNote] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [savingTemplate, setSavingTemplate] = useState(false)
  /** 저장 갈림길 — 이 작업에 새 버전으로, 또는 새 작업으로 따로. */
  const [saveChoice, setSaveChoice] = useState(false)
  const [saveAsName, setSaveAsName] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  const w = work.data

  useEffect(() => {
    if (!selectedVersion && w?.current) setSelectedVersion(w.current)
  }, [w, selectedVersion])

  function reloadAll() {
    work.reload()
    versions.reload()
    runs.reload()
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  function startEditing() {
    setDraft(structuredClone(selectedVersion?.recipe ?? w?.current?.recipe ?? { version: 1, nodes: [] }))
    setEditing(true)
  }

  async function downloadDraft(format: 'step' | 'stl' | 'dxf' | 'svg') {
    if (!draft) return
    setError(null)
    try {
      await saveRecipeAs(draft, format, w?.name ?? 'model')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  async function saveVersion() {
    if (!draft) return
    await act(async () => {
      const made = await worksApi.addVersion(id, {
        recipe: draft,
        source: 'manual',
        note,
      })
      setEditing(false)
      setNote('')
      setSelectedVersion(made)
      reloadAll()
    })
  }

  /** 고친 도면을 **새 작업**으로 — 원본은 그대로 둔다. 종류는 따라간다. */
  async function saveAsNew() {
    if (!draft || !w) return
    await act(async () => {
      const made = await worksApi.create({
        name: saveAsName.trim() || `${w.name} 사본`,
        description: w.description,
        recipe: draft,
        kind: w.kind,
        source: 'copy',
        note: `${w.name} v${w.current_version} 에서`,
      })
      setSaveChoice(false)
      setEditing(false)
      navigate(`/works/${made.id}`)
    })
  }

  async function promote() {
    await act(async () => {
      if (promoting === 'part') {
        const made = await worksApi.promotePart(id, {
          name: promoteName || undefined,
          note: promoteNote,
        })
        setPromoting(null)
        reloadAll()
        navigate(`/parts/${made.part_id}`)
      } else if (promoting === 'jig-recipe') {
        const made = await worksApi.promoteJigRecipe(id, {
          name: promoteName || undefined,
          note: promoteNote,
        })
        setPromoting(null)
        reloadAll()
        navigate(`/jigs/${made.jig_id}`)
      }
    })
  }

  if (work.error) return <ErrorNotice error={work.error} />
  if (!w) return null

  /** 이 작업이 만드는 것 — 화면의 말과 갈 곳이 여기서 갈린다. */
  const isJig = w.kind === 'jig'
  const isAssembly = w.kind === 'assembly'

  const currentPromoted = w.current?.promoted_part_id != null
  /** 붙어 있는 조건 수 — 탭에 숫자로 보여 「있다/없다」 를 열어 보지 않게. */
  const conditions = (w.current?.conditions ?? {}) as Record<string, unknown[]>
  const conditionCount = ['constraints', 'loads', 'contacts', 'initial'].reduce(
    (sum, key) => sum + (Array.isArray(conditions[key]) ? conditions[key].length : 0),
    0,
  )
  const latestRun = runs.data?.[0] ?? null
  /** 고른 버전의 STEP — 평가가 끝나야 있다. */
  const selectedStep = selectedVersion?.job?.artifacts.find((one) => one.kind === 'model_step')

  return (
    <div className="space-y-4">
      <PageHeader
        title={w.name}
        description={w.description || `v${w.current_version} · ${shownDateTime(w.updated_at)}`}
        back={{ to: '/works', label: '내 작업' }}
        actions={
          <>
            {/* 여러 벌 만드는 일은 실험계획 공간에서 — 여기서는 이 도면을 대상으로 넘겨 줄 뿐이다. */}
            <Button variant="outline" onClick={() => navigate(`/doe/new?work=${id}`)} disabled={w.current_version === 0}>
              DOE 만들기
            </Button>
            {!isAssembly && (
              <Button
                variant="outline"
                disabled={busy || w.current_version === 0 || (!isJig && currentPromoted)}
                onClick={() => {
                  setPromoteName(w.name)
                  setPromoteNote('')
                  setPromoting(isJig ? 'jig-recipe' : 'part')
                }}
                title={isJig ? '이 지그 도면을 공용 지그에 올립니다' : currentPromoted ? '현재 버전은 이미 공용 부품에 올라가 있습니다' : undefined}
              >
                {isJig ? '공용 지그로 승격' : currentPromoted ? `부품 v${w.current?.promoted_part_version} 으로 올라감` : '공용 부품으로 승격'}
              </Button>
            )}
            {w.promoted_part_id && (
              <Link to={`/parts/${w.promoted_part_id}`} className="text-muted-foreground text-xs hover:underline">
                부품으로 올라감
              </Link>
            )}
            {w.promoted_jig_id && (
              <Link to={`/jigs/${w.promoted_jig_id}`} className="text-muted-foreground text-xs hover:underline">
                지그로 올라감
              </Link>
            )}
            <Button
              variant="ghost"
              disabled={busy}
              title="현재 도면으로 새 작업 — 종류 · 꼬리표가 따라갑니다"
              onClick={() =>
                void act(async () => {
                  const made = await worksApi.duplicate(id)
                  navigate(`/works/${made.id}`)
                })
              }
            >
              복제
            </Button>
            <Button variant="ghost" onClick={() => setDeleting(true)} disabled={busy}>
              지우기
            </Button>
          </>
        }
      />
      <ErrorNotice error={error} />

      {/* 꼬리표 — 프로젝트 · 제품군으로 묶는다. 내 작업 목록이 이것으로 거른다. */}
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-xs">꼬리표</span>
        <TagEditor
          tags={w.tags}
          suggestions={allTags.data ?? []}
          busy={busy}
          onChange={(next) =>
            void act(async () => {
              await worksApi.update(id, { tags: next })
              work.reload()
              allTags.reload()
            })
          }
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="geometry">
            {/* 버전은 탭 이름에 두지 않는다 — 「도면 v3」 이 버전을 고르는 것처럼 읽혀 헷갈렸다. 버전은 머리말에. */}
            {isAssembly ? '조립' : '도면'}
          </TabsTrigger>
          {/* **둘째 탭이 곧 시뮬레이션 모드다.** 도면은 형상을 만들고, 여기서는 그 위에
              조건을 붙인다 — 형상을 안 바꾸므로 새 버전이 생기지 않는다. */}
          <TabsTrigger value="conditions" disabled={w.current_version === 0}>
            시뮬레이션 조건
            {conditionCount > 0 && <span className="text-muted-foreground ml-1 text-xs">{conditionCount}</span>}
          </TabsTrigger>
        </TabsList>

        {/* ---------------- 부품 ---------------- */}
        <TabsContent value="geometry" className="space-y-4 pt-4">
          {editing && draft ? (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>새 버전 (v{w.current_version + 1})</CardTitle>
                  <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="무엇을 바꿨나" className="h-8 w-56" />
                  <span className="text-muted-foreground text-xs">저장은 「파일」 탭에서.</span>
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setEditing(false)} disabled={busy}>
                    고치기 취소
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {isAssembly ? (
                  <AssemblyEditor value={draft} onChange={setDraft} />
                ) : (
                <RecipeEditor
                  value={draft}
                  onChange={setDraft}
                  file={{
                    save: {
                      label: '저장',
                      run: () => setSaveChoice(true),
                      disabled: busy,
                    },
                    saveTemplate: () => setSavingTemplate(true),
                    download: (format) => void downloadDraft(format),
                    // 올린 STEP 이 곧 새 버전이다 — 지금 고치던 것은 버리고 그 버전을 보여 준다.
                    importStep: {
                      label: 'STEP 올리기',
                      title: `STEP 을 올려 새 버전(v${w.current_version + 1})으로 — 지금 고치던 것은 버립니다`,
                      busy,
                      run: (file) =>
                        void act(async () => {
                          const made = await worksApi.importStep(id, file)
                          setEditing(false)
                          setSelectedVersion(made)
                          reloadAll()
                        }),
                    },
                    onLoaded: (label, source) => setNote(source === 'copy' ? `${label} 에서 복사` : `${label} 템플릿에서`),
                    currentWorkId: id,
                  }}
                />
                )}
                {isAssembly && (
                  <div className="mt-3 flex items-center gap-2">
                    <Button size="sm" onClick={() => setSaveChoice(true)} disabled={busy}>
                      저장
                    </Button>
                    <span className="text-muted-foreground text-xs">저장해야 3D 와 DOE 에 반영됩니다.</span>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <>
              {/* 이 도면을 어떻게 — 한 줄에 모은다. 작업 자체의 일(실험계획 · 승격 · 지우기)은 머리에 있다. */}
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={startEditing} disabled={busy}>
                  {w.current_version === 0 ? '그리기 시작' : '수정'}
                </Button>
                <Button
                  variant="outline"
                  disabled={!selectedStep}
                  title={selectedStep ? undefined : '아직 평가된 STEP 이 없습니다'}
                  onClick={() => selectedStep && selectedVersion && downloadFile(jobsApi.artifactPath(selectedStep.id), `${w.name}-v${selectedVersion.number}.step`)}
                >
                  STEP 받기{selectedVersion && selectedVersion.number !== w.current_version ? ` (v${selectedVersion.number})` : ''}
                </Button>
                <Button variant="outline" onClick={() => setSavingTemplate(true)} disabled={busy || !selectedVersion}>
                  템플릿으로 저장
                  {selectedVersion && selectedVersion.number !== w.current_version ? ` (v${selectedVersion.number})` : ''}
                </Button>
              </div>

              {w.current_version === 0 && isAssembly ? (
                <EmptyState
                  title="빈 조립입니다"
                  hint="「구성품 놓기」 를 누르면 왼쪽 라이브러리에서 부품 · 지그를 가져와 놓을 수 있습니다."
                  action={
                    <Button
                      onClick={() => {
                        setDraft({ version: 1, nodes: [] })
                        setEditing(true)
                      }}
                    >
                      구성품 놓기
                    </Button>
                  }
                />
              ) : w.current_version === 0 ? (
                <EmptyState
                  title="아직 도면이 없습니다"
                  hint="「그리기 시작」 으로 들어가 그리거나, 그 안 「파일」 탭에서 STEP 을 올리세요."
                  action={<Button onClick={startEditing}>그리기 시작</Button>}
                />
              ) : (
                <div className="grid gap-4 lg:grid-cols-4">
                  <Card className="lg:col-span-1">
                    <CardHeader>
                      <CardTitle>버전</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-1">
                        {(versions.data ?? []).map((one) => (
                          <li key={one.id}>
                            <button
                              type="button"
                              onClick={() => setSelectedVersion(one)}
                              className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${selectedVersion?.id === one.id ? 'bg-accent' : 'hover:bg-accent/60'}`}
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-medium">
                                  v{one.number}
                                  {one.number === w.current_version && <span className="text-muted-foreground ml-1 text-xs">현재</span>}
                                  {one.promoted_part_id && <span className="ml-1 rounded border px-1 text-[10px]">부품 v{one.promoted_part_version}</span>}
                                </span>
                                {one.job && <StatusBadge kind="run" value={one.job.status} />}
                              </div>
                              <p className="text-muted-foreground truncate text-xs">
                                {SOURCE_LABELS[one.source] ?? one.source} · {one.note || '—'}
                              </p>
                              <p className="text-muted-foreground text-xs">{shownDateTime(one.created_at)}</p>
                            </button>
                            {one.number !== w.current_version && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-2 text-xs"
                                disabled={busy}
                                onClick={() =>
                                  act(async () => {
                                    const made = await worksApi.restore(id, one.number)
                                    setSelectedVersion(made)
                                    reloadAll()
                                  })
                                }
                              >
                                이 버전으로 되돌리기
                              </Button>
                            )}
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                  <div className="lg:col-span-3">
                    {selectedVersion && (
                      <GeometryJobView
                        key={selectedVersion.id}
                        job={selectedVersion.job}
                        title={`v${selectedVersion.number}`}
                        onFinished={reloadAll}
                      />
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {/* 부품에서 생성한 지그 — 계획 · 간섭 검사를 되짚어 본다. 결과를 아직 도면으로 안 가져왔으면 여기서. */}
          {isJig && latestRun && (
            <Card>
              <CardHeader>
                <CardTitle>생성기 결과 — 계획 · 간섭</CardTitle>
              </CardHeader>
              <CardContent>
                <JigResultView
                  key={latestRun.id}
                  job={latestRun}
                  onFinished={reloadAll}
                  actions={
                    w.current_version === 0 &&
                    latestRun.status === 'done' && (
                      <Button
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          void act(async () => {
                            await worksApi.adoptJigRun(id, latestRun.id)
                            reloadAll()
                          })
                        }
                      >
                        도면으로 가져오기
                      </Button>
                    )
                  }
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ---------------- 해석 조건 ---------------- */}
        <TabsContent value="conditions" className="pt-4">
          {w.current ? (
            <ConditionsPanel
              recipe={w.current.recipe}
              value={w.current.conditions}
              saving={busy}
              onSave={(next) => {
                setBusy(true)
                setError(null)
                conditionsApi
                  .save(id, w.current_version, next)
                  .then(() => reloadAll())
                  .catch((failure) => setError(failure as ApiError))
                  .finally(() => setBusy(false))
              }}
            />
          ) : (
            <EmptyState title="도면이 먼저입니다" hint="「도면」 탭에서 그리고 저장한 뒤 조건을 붙이세요." />
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={saveChoice} onOpenChange={(open) => !open && !busy && setSaveChoice(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>저장</DialogTitle>
            <DialogDescription>이 작업에 덮어 저장할지, 새 작업으로 따로 저장할지 고릅니다.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <button
              type="button"
              className="hover:bg-accent rounded-md border px-3 py-2 text-left"
              disabled={busy}
              onClick={() => {
                setSaveChoice(false)
                void saveVersion()
              }}
            >
              <div className="text-sm font-medium">
                「{w.name}」 에 덮어 저장 (v{w.current_version} → v{w.current_version + 1})
              </div>
              <div className="text-muted-foreground text-xs">새 버전이 붙습니다. 옛 버전은 남아 되돌릴 수 있습니다.</div>
            </button>
            <div className="rounded-md border px-3 py-2">
              <div className="text-sm font-medium">새 작업으로 저장</div>
              <div className="text-muted-foreground mb-2 text-xs">원본 「{w.name}」 은 그대로 두고 다른 이름의 작업을 만듭니다.</div>
              <div className="flex items-center gap-2">
                <Input value={saveAsName} onChange={(e) => setSaveAsName(e.target.value)} placeholder={`${w.name} 사본`} className="h-8" aria-label="새 작업 이름" />
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void saveAsNew()}>
                  새 작업으로
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={promoting !== null} onOpenChange={(open) => !open && !busy && setPromoting(null)}>
        <DialogContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void promote()
            }}
            className="space-y-4"
          >
            <DialogHeader>
              <DialogTitle>{promoting === 'part' ? '공용 부품으로 승격' : '공용 지그로 승격'}</DialogTitle>
              <DialogDescription>
                {promoting === 'part'
                  ? `부품 v${w.current_version} 이 공용 부품으로 올라갑니다. 올라간 버전은 바뀌지 않습니다 — 고치려면 여기서 고쳐 다시 승격합니다.`
                  : `지금 도면(v${w.current_version})을 공용 지그로 올립니다. 형상과 STEP 이 올라가고, 잡는 부품이 이어져 있으면 함께 적힙니다.`}
              </DialogDescription>
            </DialogHeader>
            {!(promoting === 'part' ? w.promoted_part_id : w.promoted_jig_id) && (
              <div className="space-y-2">
                <Label htmlFor="promote-name">카탈로그 이름</Label>
                <Input id="promote-name" value={promoteName} onChange={(e) => setPromoteName(e.target.value)} />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="promote-note">메모</Label>
              <Input id="promote-note" value={promoteNote} onChange={(e) => setPromoteNote(e.target.value)} placeholder="무엇이 바뀌었나" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setPromoting(null)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? '올리는 중…' : '승격'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {selectedVersion && (
        <SaveTemplateDialog
          key={String(savingTemplate)}
          open={savingTemplate}
          recipe={editing && draft ? draft : selectedVersion.recipe}
          defaultName={w.name}
          onClose={() => setSavingTemplate(false)}
        />
      )}

      <ConfirmDialog
        open={deleting}
        title="작업을 지웁니다"
        description={`「${w.name}」 이 내 작업에서 사라집니다. 이미 승격한 부품 · 지그는 남습니다.`}
        confirmLabel="지우기"
        destructive
        onConfirm={async () => {
          await worksApi.remove(id)
          navigate('/works')
        }}
        onClose={() => setDeleting(false)}
      />
    </div>
  )
}
