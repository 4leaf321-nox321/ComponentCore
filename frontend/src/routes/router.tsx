/**
 * 라우트 표. 사이드바(navigation.ts)에 있는 항목은 여기에 대응 경로가 있어야 한다 —
 * `router.test.tsx` 가 검사한다. /login · /force-password-change 만 가드 밖이다.
 */

import { lazy } from 'react'
import { Navigate, createBrowserRouter } from 'react-router-dom'

import ForcePasswordChangePage from '@/modules/auth/ForcePasswordChangePage'
import { ById } from '@/routes/ById'
import LoginPage from '@/modules/auth/LoginPage'
import { ROUTER_BASENAME } from '@/shared/base'
import { ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { Placeholder } from '@/shared/components/Placeholder'
import { AppShell } from '@/shared/layout/AppShell'

// **매일 밟는 길(로그인 · 내 작업)은 처음에 싣고** 나머지는 나눠 싣는다.
const DrawPage = lazy(() => import('@/modules/works/DrawPage'))
const JigFromPartPage = lazy(() => import('@/modules/works/JigFromPartPage'))
const WorksPage = lazy(() => import('@/modules/works/WorksPage'))
const WorkPage = lazy(() => import('@/modules/works/WorkPage'))
const TemplatesPage = lazy(() => import('@/modules/templates/TemplatesPage'))
const SpecimensPage = lazy(() => import('@/modules/specimens/SpecimensPage'))
const DoeStudiesPage = lazy(() => import('@/modules/doe/DoeStudiesPage'))
const DoeStudyPage = lazy(() => import('@/modules/doe/DoeStudyPage'))
const NewDoePage = lazy(() => import('@/modules/doe/NewDoePage'))
const PartsPage = lazy(() => import('@/modules/parts/PartsPage'))
const PartPage = lazy(() => import('@/modules/parts/PartPage'))
const JigsPage = lazy(() => import('@/modules/jigs/JigsPage'))
const JigPage = lazy(() => import('@/modules/jigs/JigPage'))
const JobsPage = lazy(() => import('@/modules/jobs/JobsPage'))
const ProfilePage = lazy(() => import('@/modules/auth/ProfilePage'))
const AccountsAdminPage = lazy(() => import('@/modules/accounts/AccountsAdminPage'))
const AllWorksPage = lazy(() => import('@/modules/works/AllWorksPage'))
const ServerPage = lazy(() => import('@/modules/server/ServerPage'))
const VocPage = lazy(() => import('@/modules/voc/VocPage'))
const VocDetailPage = lazy(() => import('@/modules/voc/VocDetailPage'))

// StandardPlatform 에서 들인 화면(ADR 0008) — 경로는 SP 와 같다. SP 의 `/jobs`(데이터 작업)만
// `/tasks` 다 — `/jobs` 는 CompCore 의 실행 기록이다.
const TasksPage = lazy(() => import('@/modules/tasks/JobsPage'))
const NotificationsPage = lazy(() => import('@/modules/notifications/NotificationsPage'))
const GraphPage = lazy(() => import('@/modules/graph/GraphPage'))
const MetricsPage = lazy(() => import('@/modules/metrics/MetricsPage'))
const MetricDetailPage = lazy(() => import('@/modules/metrics/MetricDetailPage'))
const SearchPage = lazy(() => import('@/modules/objectsearch/SearchPage'))
const AuditPage = lazy(() => import('@/modules/audit/AuditPage'))
const QualityPage = lazy(() => import('@/modules/objects/QualityPage'))
const ReviewPage = lazy(() => import('@/modules/review/ReviewPage'))
const ObjectTypesPage = lazy(() => import('@/modules/objects/ObjectTypesPage'))
const ObjectListPage = lazy(() => import('@/modules/objects/ObjectListPage'))
const ObjectProfilePage = lazy(() => import('@/modules/objects/ObjectProfilePage'))
// 차트 층 자신의 문서다 — 도메인 모듈이 아니라 `shared/charts` 에 산다.
const ChartGalleryPage = lazy(() => import('@/shared/charts/GalleryPage'))
const OntologyLayout = lazy(() => import('@/modules/ontology/OntologyLayout'))
const OntologyGroupsPage = lazy(() => import('@/modules/ontology/OntologyGroupsPage'))
const OntologyTypesPage = lazy(() => import('@/modules/ontology/OntologyTypesPage'))
const OntologyInterfacesPage = lazy(() => import('@/modules/ontology/OntologyInterfacesPage'))
const OntologyRelationsPage = lazy(() => import('@/modules/ontology/OntologyRelationsPage'))
const OntologyImportPage = lazy(() => import('@/modules/ontology/OntologyImportPage'))
const OntologyCorePage = lazy(() => import('@/modules/ontology/OntologyCorePage'))
const OntologyTagsPage = lazy(() => import('@/modules/ontology/OntologyTagsPage'))
const WorkspacesAdminPage = lazy(() => import('@/modules/workspaces/WorkspacesAdminPage'))
const WorkspaceHomePage = lazy(() => import('@/modules/workspaces/WorkspaceHomePage'))
const MembersPage = lazy(() => import('@/modules/workspaces/MembersPage'))
const WebhooksPage = lazy(() => import('@/modules/webhooks/WebhooksPage'))
const DataSourcesPage = lazy(() => import('@/modules/datasources/DataSourcesPage'))

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
            { path: 'draw/jig-from-part', element: <JigFromPartPage /> },
            { path: 'works', element: <WorksPage /> },
            { path: 'works/:id', element: <ById><WorkPage /></ById> },
            { path: 'templates', element: <TemplatesPage /> },
            { path: 'specimens', element: <SpecimensPage /> },
            { path: 'doe', element: <DoeStudiesPage /> },
            { path: 'doe/new', element: <NewDoePage /> },
            { path: 'doe/:id', element: <ById><DoeStudyPage /></ById> },
            { path: 'parts', element: <PartsPage /> },
            { path: 'parts/:id', element: <ById><PartPage /></ById> },
            { path: 'jigs', element: <JigsPage /> },
            { path: 'jigs/:id', element: <ById><JigPage /></ById> },
            { path: 'jobs', element: <JobsPage /> },
            { path: 'me', element: <ProfilePage /> },
            { path: 'voc', element: <VocPage /> },
            { path: 'voc/:id', element: <ById><VocDetailPage /></ById> },
            { path: 'tasks', element: <TasksPage /> },
            { path: 'notifications', element: <NotificationsPage /> },

            // 기준정보 — **정의가 만드는 화면.** 타입이 늘어도 라우트는 안 늘어난다.
            { path: 'search', element: <SearchPage /> },
            { path: 'o', element: <ObjectTypesPage /> },
            { path: 'o/:typeSlug', element: <ObjectListPage /> },
            { path: 'o/:typeSlug/:objectId', element: <ObjectProfilePage /> },
            { path: 'graph', element: <GraphPage /> },
            { path: 'metrics', element: <MetricsPage /> },
            { path: 'metrics/:slug', element: <MetricDetailPage /> },
            { path: 'audit', element: <AuditPage /> },
            { path: 'quality', element: <QualityPage /> },
            { path: 'review', element: <ReviewPage /> },

            // 부서 스코프
            {
              path: 'w/:slug',
              children: [
                { index: true, element: <WorkspaceHomePage /> },
                { path: 'members', element: <MembersPage /> },
              ],
            },

            { path: 'admin/works', element: <AllWorksPage /> },
            { path: 'admin/accounts', element: <AccountsAdminPage /> },
            { path: 'admin/workspaces', element: <WorkspacesAdminPage /> },
            {
              // **두 번째 사이드바.** 묶음과 타입을 각각 제 화면에서 본다.
              path: 'admin/ontology',
              element: <OntologyLayout />,
              children: [
                { index: true, element: <Navigate to="groups" replace /> },
                { path: 'groups', element: <OntologyGroupsPage /> },
                { path: 'types', element: <OntologyTypesPage /> },
                { path: 'interfaces', element: <OntologyInterfacesPage /> },
                { path: 'relations', element: <OntologyRelationsPage /> },
                { path: 'tags', element: <OntologyTagsPage /> },
                { path: 'import', element: <OntologyImportPage /> },
                { path: 'core', element: <OntologyCorePage /> },
              ],
            },
            { path: 'admin/server', element: <ServerPage /> },
            { path: 'admin/charts', element: <ChartGalleryPage /> },
            { path: 'admin/webhooks', element: <WebhooksPage /> },
            { path: 'admin/datasources', element: <DataSourcesPage /> },
            {
              path: '*',
              element: (
                <Placeholder title="페이지를 찾을 수 없습니다" phase="—" description="주소를 확인하십시오." />
              ),
            },
          ],
        },
      ],
    },
  ],
  { basename: ROUTER_BASENAME },
)
