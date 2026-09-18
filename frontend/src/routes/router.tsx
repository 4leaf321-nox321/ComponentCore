/**
 * 라우트 표. 사이드바(navigation.ts)에 있는 항목은 여기에 대응 경로가 있어야 한다 —
 * `router.test.tsx` 가 검사한다. /login · /force-password-change 만 가드 밖이다.
 */

import { lazy } from 'react'
import { Navigate, createBrowserRouter } from 'react-router-dom'

import ForcePasswordChangePage from '@/modules/auth/ForcePasswordChangePage'
import LoginPage from '@/modules/auth/LoginPage'
import { ROUTER_BASENAME } from '@/shared/base'
import { ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { Placeholder } from '@/shared/components/Placeholder'
import { AppShell } from '@/shared/layout/AppShell'

// **매일 밟는 길(로그인 · 내 작업)은 처음에 싣고** 나머지는 나눠 싣는다.
const DrawPage = lazy(() => import('@/modules/works/DrawPage'))
const WorksPage = lazy(() => import('@/modules/works/WorksPage'))
const WorkPage = lazy(() => import('@/modules/works/WorkPage'))
const TemplatesPage = lazy(() => import('@/modules/templates/TemplatesPage'))
const DoeStudiesPage = lazy(() => import('@/modules/doe/DoeStudiesPage'))
const DoeStudyPage = lazy(() => import('@/modules/doe/DoeStudyPage'))
const PartsPage = lazy(() => import('@/modules/parts/PartsPage'))
const PartPage = lazy(() => import('@/modules/parts/PartPage'))
const JigsPage = lazy(() => import('@/modules/jigs/JigsPage'))
const JigPage = lazy(() => import('@/modules/jigs/JigPage'))
const JobsPage = lazy(() => import('@/modules/jobs/JobsPage'))
const ProfilePage = lazy(() => import('@/modules/auth/ProfilePage'))
const AccountsAdminPage = lazy(() => import('@/modules/accounts/AccountsAdminPage'))
const ServerPage = lazy(() => import('@/modules/server/ServerPage'))

export const router = createBrowserRouter(
  [
    { path: '/login', element: <LoginPage /> },
    {
      element: <ProtectedRoute />,
      children: [
        { path: '/force-password-change', element: <ForcePasswordChangePage /> },
        {
          path: '/',
          element: <AppShell />,
          children: [
            { index: true, element: <Navigate to="/works" replace /> },
            { path: 'draw', element: <DrawPage /> },
            { path: 'works', element: <WorksPage /> },
            { path: 'works/:id', element: <WorkPage /> },
            { path: 'templates', element: <TemplatesPage /> },
            { path: 'doe', element: <DoeStudiesPage /> },
            { path: 'doe/:id', element: <DoeStudyPage /> },
            { path: 'parts', element: <PartsPage /> },
            { path: 'parts/:id', element: <PartPage /> },
            { path: 'jigs', element: <JigsPage /> },
            { path: 'jigs/:id', element: <JigPage /> },
            { path: 'jobs', element: <JobsPage /> },
            { path: 'me', element: <ProfilePage /> },
            { path: 'admin/accounts', element: <AccountsAdminPage /> },
            { path: 'admin/server', element: <ServerPage /> },
            {
              path: '*',
              element: (
                <Placeholder title="없는 페이지" phase="—" description="주소를 확인해 주세요." />
              ),
            },
          ],
        },
      ],
    },
  ],
  { basename: ROUTER_BASENAME },
)
