/**
 * 코어 구독(SP ADR 0085 를 들인다) — 미리 보기를 먼저 보고 생성한다. 목록은 상태 · 수신 중지 · 정의 검토 대기를
 * 보이고, 검토 대기는 읽은 지문으로 적용한다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CoreSubscription, CoreSubscriptionPlan } from '@/modules/datasources/api'

const datasourceApi = vi.hoisted(() => ({
  coreSubscribe: vi.fn(),
  coreSubscriptions: vi.fn(),
  coreSubscriptionSync: vi.fn(),
  coreHeldApply: vi.fn(),
  coreSubscriptionUpdate: vi.fn(),
  coreSubscriptionRemove: vi.fn(),
  coreTakeOver: vi.fn(),
  coreRelease: vi.fn(),
}))
vi.mock('@/modules/datasources/api', () => ({ datasourceApi }))

function plan(applied: boolean): CoreSubscriptionPlan {
  return {
    system: 'hub',
    applied,
    definitions: true,
    groups: [{ slug: 'plm', label: 'PLM 기준정보', parent_slug: null }],
    types: [
      {
        type_slug: 'part',
        type_label: '부품',
        action: 'define',
        reason: '',
        source_slug: '',
        count: 800000,
      },
      {
        type_slug: 'project',
        type_label: '과제',
        action: 'skip',
        reason: '이 설치가 만든 같은 이름의 타입이 있어 받지 않습니다',
        source_slug: '',
        count: 12,
      },
    ],
    held: [],
    notes: [],
    subscription: null,
    job_id: applied ? 'job-1' : null,
  }
}

function subscription(over: Partial<CoreSubscription> = {}): CoreSubscription {
  return {
    id: 'sub-1',
    base_url: 'https://hub.example/api',
    system: 'hub',
    source_name: 'hub',
    groups: [],
    interval_minutes: 60,
    is_active: true,
    auth_kind: 'bearer',
    auth_user: '',
    has_secret: true,
    checked_at: '2026-11-18T05:00:00Z',
    last_status: 'held',
    last_error: '',
    held: { mark: 'm-1', lines: ['속성 part.color: 고를 값에서 파랑 을(를) 뺍니다.'] },
    notes: [],
    sources: [
      {
        slug: 'part_core',
        name: '부품 (hub)',
        type_slug: 'part',
        is_active: true,
        paused: false,
        last_status: 'ok',
        last_success_at: null,
      },
      {
        slug: 'memo_core',
        name: '메모 (hub)',
        type_slug: 'memo',
        is_active: false,
        paused: true,
        last_status: 'ok',
        last_success_at: null,
      },
    ],
    created_at: '2026-11-18T04:00:00Z',
    ...over,
  }
}

describe('코어 구독 생성', () => {
  beforeEach(() => vi.clearAllMocks())

  it('미리 보기로 받을 것과 받지 않을 것을 까닭과 함께 보이고, 그 뒤에 생성한다', async () => {
    const { CoreSubscribeDialog } = await import('@/modules/datasources/CoreSubscriptions')
    const onCreated = vi.fn()
    datasourceApi.coreSubscribe
      .mockResolvedValueOnce(plan(false))
      .mockResolvedValueOnce(plan(false))
      .mockResolvedValueOnce(plan(true))
    render(<CoreSubscribeDialog onClose={vi.fn()} onCreated={onCreated} />)

    const create = screen.getByRole('button', { name: '생성' })
    expect(create).toBeDisabled()
    await userEvent.type(screen.getByLabelText('허브의 API 주소'), 'https://hub.example/api')
    await userEvent.type(screen.getByLabelText('액세스 토큰(core:read)'), 'secret')
    expect(create).toBeDisabled() // 미리 보기 전
    await userEvent.click(screen.getByRole('button', { name: '미리 보기' }))

    expect(await screen.findByText('800,000')).toBeInTheDocument()
    expect(screen.getByText('정의 생성 후 수신')).toBeInTheDocument()
    expect(screen.getByText(/같은 이름의 타입이 있어 받지 않습니다/)).toBeInTheDocument()
    expect(datasourceApi.coreSubscribe).toHaveBeenLastCalledWith(
      expect.objectContaining({
        apply: false,
        groups: [],
        source_name: 'hub',
        interval_minutes: 60,
        auth_kind: 'bearer',
      }),
    )
    // 허브의 묶음이 범위로 뜬다 — 고르면 계획이 낡아 다시 본다.
    await userEvent.click(screen.getByRole('checkbox', { name: /PLM 기준정보/ }))
    expect(screen.queryByText('800,000')).toBeNull()
    expect(screen.getByRole('button', { name: '생성' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: '미리 보기' }))
    expect(datasourceApi.coreSubscribe).toHaveBeenLastCalledWith(
      expect.objectContaining({ groups: ['plm'], apply: false }),
    )
    await userEvent.click(await screen.findByRole('button', { name: '생성' }))
    await waitFor(() => expect(onCreated).toHaveBeenCalled())
    expect(datasourceApi.coreSubscribe).toHaveBeenLastCalledWith(
      expect.objectContaining({ apply: true, groups: ['plm'] }),
    )
    expect(screen.getByText(/코어 구독을 생성했습니다/)).toBeInTheDocument()
  })
})

describe('코어 구독 목록', () => {
  beforeEach(() => vi.clearAllMocks())

  it('구독이 없으면 아무것도 그리지 않는다', async () => {
    const { CoreSubscriptions } = await import('@/modules/datasources/CoreSubscriptions')
    datasourceApi.coreSubscriptions.mockResolvedValue([])
    const { container } = render(<CoreSubscriptions version={0} onChanged={vi.fn()} />)
    await waitFor(() => expect(datasourceApi.coreSubscriptions).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('정의 검토 대기를 줄과 함께 보이고, 읽은 지문으로 적용한다', async () => {
    const { CoreSubscriptions } = await import('@/modules/datasources/CoreSubscriptions')
    const onChanged = vi.fn()
    datasourceApi.coreSubscriptions
      .mockResolvedValueOnce([subscription()])
      .mockResolvedValue([subscription({ held: null, last_status: 'ok' })])
    datasourceApi.coreHeldApply.mockResolvedValue({
      id: 'job-2',
      status: 'done',
      result: { definitions_applied: 2, created: [], held: 0 },
    })
    render(<CoreSubscriptions version={0} onChanged={onChanged} />)

    expect(await screen.findAllByText('정의 검토 대기')).not.toHaveLength(0)
    expect(screen.getByText(/고를 값에서 파랑/)).toBeInTheDocument()
    expect(screen.getByText(/수신 중지 1개/)).toBeInTheDocument()
    expect(screen.getByText('수신 중지')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '적용' }))
    // 확인 창이 무엇이 바뀌는지 다시 보인다.
    expect(await screen.findByText(/저장된 값이 변환되거나 비워질 수 있고/)).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: '적용' })
    await userEvent.click(buttons[buttons.length - 1])
    await waitFor(() => expect(datasourceApi.coreHeldApply).toHaveBeenCalledWith('sub-1', 'm-1'))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(await screen.findByText(/정의 변경 적용 2/)).toBeInTheDocument()
  })

  it('동기화는 확인 결과를 한 줄로 말한다', async () => {
    const { CoreSubscriptions } = await import('@/modules/datasources/CoreSubscriptions')
    datasourceApi.coreSubscriptions.mockResolvedValue([
      subscription({ held: null, last_status: 'ok' }),
    ])
    datasourceApi.coreSubscriptionSync.mockResolvedValue({
      id: 'job-3',
      status: 'done',
      result: { definitions_applied: 0, created: ['memo_core'], paused: [], restarted: [] },
    })
    render(<CoreSubscriptions version={0} onChanged={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: /동기화/ }))
    expect(await screen.findByText('확인 끝 — 소스 생성 1')).toBeInTheDocument()
    expect(datasourceApi.coreSubscriptionSync).toHaveBeenCalledWith('sub-1')
  })
})

// 허브 관리로 넘기기(CompCore, 2026-11-22) — 이 설치가 만든 같은 이름의 타입을 골라서만 넘긴다.
describe('허브 관리로 넘기기', () => {
  beforeEach(() => vi.clearAllMocks())

  it('생성 창 — 넘길 수 있는 타입을 고르면 계획이 낡고, 다시 본 계획대로 넘겨 생성한다', async () => {
    const { CoreSubscribeDialog } = await import('@/modules/datasources/CoreSubscriptions')
    const local: CoreSubscriptionPlan = {
      ...plan(false),
      types: [
        {
          type_slug: 'part',
          type_label: '부품',
          action: 'skip',
          reason: '이 설치가 만든 같은 이름의 타입이 있어 받지 않습니다',
          source_slug: 'sp_part',
          count: 112,
          adoptable: true,
        },
      ],
    }
    const taking: CoreSubscriptionPlan = {
      ...local,
      types: [{ ...local.types[0], action: 'take', reason: '허브 관리로 넘기고 받습니다' }],
      taken: { types: ['part'], relation_types: ['part_uses'], interfaces: [] },
    }
    datasourceApi.coreSubscribe
      .mockResolvedValueOnce(local)
      .mockResolvedValueOnce(taking)
      .mockResolvedValueOnce({ ...taking, applied: true, job_id: 'job-1' })
    render(<CoreSubscribeDialog onClose={vi.fn()} onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('허브의 API 주소'), 'https://hub.example/api')
    await userEvent.type(screen.getByLabelText('액세스 토큰(core:read)'), 'secret')
    await userEvent.click(screen.getByRole('button', { name: '미리 보기' }))

    await userEvent.click(await screen.findByRole('checkbox', { name: '허브 관리로 넘기기' }))
    expect(screen.getByRole('button', { name: '생성' })).toBeDisabled() // 계획이 낡았다
    await userEvent.click(screen.getByRole('button', { name: '미리 보기' }))
    expect(datasourceApi.coreSubscribe).toHaveBeenLastCalledWith(
      expect.objectContaining({ adopt: ['part'], apply: false }),
    )
    expect(await screen.findByText(/허브 관리로 넘길 것 — 타입 part · 관계 종류 part_uses/)).toBeInTheDocument()
    expect(screen.getByText('허브 관리로 넘기고 수신')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '생성' }))
    await waitFor(() =>
      expect(datasourceApi.coreSubscribe).toHaveBeenLastCalledWith(
        expect.objectContaining({ adopt: ['part'], apply: true }),
      ),
    )
  })

  it('목록 — 고른 타입을 넘기고, 넘긴 것은 되돌린다', async () => {
    const { CoreSubscriptions } = await import('@/modules/datasources/CoreSubscriptions')
    datasourceApi.coreSubscriptions.mockResolvedValue([
      subscription({
        held: null,
        last_status: 'ok',
        adoptable: [
          { type_slug: 'part', type_label: '부품', source_slug: 'sp_part' },
          { type_slug: 'sku', type_label: '모델', source_slug: '' },
        ],
        taken: { types: ['country'], relation_types: [], interfaces: [] },
      }),
    ])
    datasourceApi.coreTakeOver.mockResolvedValue({ id: 'job-4', status: 'done', result: { adopted: ['sp_part'] } })
    datasourceApi.coreRelease.mockResolvedValue({ id: 'job-5', status: 'done', result: {} })
    render(<CoreSubscriptions version={0} onChanged={vi.fn()} />)

    const take = await screen.findByRole('button', { name: '허브 관리로 넘기기' })
    expect(take).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: /부품/ }))
    await userEvent.click(take)
    expect(await screen.findByText(/정의와 객체를 고칠 수 없고/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '넘기기' }))
    await waitFor(() => expect(datasourceApi.coreTakeOver).toHaveBeenCalledWith('sub-1', ['part']))
    expect(await screen.findByText('확인 끝 — 기존 소스 사용 1')).toBeInTheDocument()

    expect(screen.getByText(/허브 관리로 넘긴 것 — 타입 country/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '되돌리기' }))
    const confirm = await screen.findAllByRole('button', { name: '되돌리기' })
    await userEvent.click(confirm[confirm.length - 1])
    await waitFor(() => expect(datasourceApi.coreRelease).toHaveBeenCalledWith('sub-1'))
  })
})
