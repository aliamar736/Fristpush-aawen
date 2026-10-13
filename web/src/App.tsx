import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { CitizenShell, StaffShell } from "./components/Shell";
import { ErrorState, Loading, ToastProvider } from "./components/ui";
import { I18nProvider } from "./lib/i18n";
import { ApiError } from "./api/client";
import Home from "./pages/citizen/Home";

const MapPage = lazy(() => import("./pages/citizen/MapPage"));
const ReportWizard = lazy(() => import("./pages/citizen/ReportWizard"));
const ReportDetail = lazy(() => import("./pages/citizen/ReportDetail"));
const Aawen = lazy(() => import("./pages/citizen/Aawen"));
const InitiativeDetail = lazy(() => import("./pages/citizen/Initiative"));
const Contribute = lazy(() => import("./pages/citizen/Contribute"));
const Impact = lazy(() => import("./pages/citizen/Impact"));
const Login = lazy(() => import("./pages/citizen/Login"));
const Simulator = lazy(() => import("./pages/citizen/Simulator"));
const RoadNew = lazy(() => import("./pages/citizen/Road").then((m) => ({ default: m.RoadNew })));
const RoadDetail = lazy(() => import("./pages/citizen/Road").then((m) => ({ default: m.RoadDetail })));
const Notifications = lazy(() => import("./pages/citizen/Misc").then((m) => ({ default: m.Notifications })));
const PlaceProfile = lazy(() => import("./pages/citizen/Misc").then((m) => ({ default: m.PlaceProfile })));
const Proposals = lazy(() => import("./pages/citizen/Misc").then((m) => ({ default: m.Proposals })));
const ReportWorkbench = lazy(() => import("./pages/admin/ReportWorkbench"));
const ops = () => import("./pages/admin/Operations");
const Dashboard = lazy(() => ops().then((m) => ({ default: m.Dashboard })));
const Queue = lazy(() => ops().then((m) => ({ default: m.Queue })));
const Moderation = lazy(() => ops().then((m) => ({ default: m.Moderation })));
const Followups = lazy(() => ops().then((m) => ({ default: m.Followups })));
const Bundles = lazy(() => ops().then((m) => ({ default: m.Bundles })));
const InitiativesAdmin = lazy(() => ops().then((m) => ({ default: m.InitiativesAdmin })));
const ProposalsAdmin = lazy(() => ops().then((m) => ({ default: m.ProposalsAdmin })));
const Coverage = lazy(() => ops().then((m) => ({ default: m.Coverage })));
const Directory = lazy(() => ops().then((m) => ({ default: m.Directory })));
const Finance = lazy(() => import("./pages/admin/Finance"));
const sys = () => import("./pages/admin/System");
const Categories = lazy(() => sys().then((m) => ({ default: m.Categories })));
const Geo = lazy(() => sys().then((m) => ({ default: m.Geo })));
const Users = lazy(() => sys().then((m) => ({ default: m.Users })));
const Settings = lazy(() => sys().then((m) => ({ default: m.Settings })));
const Audit = lazy(() => sys().then((m) => ({ default: m.Audit })));
const ag = () => import("./pages/agency/Agency");
const AgencyInbox = lazy(() => ag().then((m) => ({ default: m.AgencyInbox })));
const AgencyAnnouncements = lazy(() => ag().then((m) => ({ default: m.AgencyAnnouncements })));
const FieldTasks = lazy(() => ag().then((m) => ({ default: m.FieldTasks })));

/** Client-side gate for a nicer experience; the server enforces every permission independently. */
function RequireRole({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { me, loading, hasRole } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname)}`} replace />;
  if (roles.length && !hasRole(...roles)) return <ErrorState error={new ApiError(403, "forbidden", "")} />;
  return <>{children}</>;
}

const STAFF = ["reviewer", "coordinator", "sysadmin", "accountant", "financial_auditor", "ambassador"];

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <Suspense fallback={<div style={{ padding: 24 }}><Loading /></div>}>
              <Routes>
                <Route element={<CitizenShell />}>
                  <Route index element={<Home />} />
                  <Route path="map" element={<MapPage />} />
                  <Route path="report/new" element={<ReportWizard />} />
                  <Route path="reports/:id" element={<ReportDetail />} />
                  <Route path="aawen" element={<Aawen />} />
                  <Route path="initiatives/:id" element={<InitiativeDetail />} />
                  <Route path="contribute" element={<Contribute />} />
                  <Route path="contribute/simulator/:pid" element={<Simulator />} />
                  <Route path="me" element={<Impact />} />
                  <Route path="login" element={<Login />} />
                  <Route path="road/new" element={<RoadNew />} />
                  <Route path="road/:id" element={<RoadDetail />} />
                  <Route path="notifications" element={<RequireRole roles={[]}><Notifications /></RequireRole>} />
                  <Route path="place" element={<PlaceProfile />} />
                  <Route path="proposals" element={<Proposals />} />
                  <Route path="*" element={<ErrorState error={new ApiError(404, "not_found", "")} />} />
                </Route>
                <Route path="staff" element={<RequireRole roles={STAFF}><StaffShell /></RequireRole>}>
                  <Route index element={<Dashboard />} />
                  <Route path="queue" element={<Queue />} />
                  <Route path="reports/:id" element={<ReportWorkbench />} />
                  <Route path="moderation" element={<Moderation />} />
                  <Route path="followups" element={<Followups />} />
                  <Route path="bundles" element={<Bundles />} />
                  <Route path="initiatives" element={<InitiativesAdmin />} />
                  <Route path="proposals" element={<ProposalsAdmin />} />
                  <Route path="coverage" element={<Coverage />} />
                  <Route path="directory" element={<Directory />} />
                  <Route path="finance" element={<Finance />} />
                  <Route path="categories" element={<Categories />} />
                  <Route path="geo" element={<Geo />} />
                  <Route path="users" element={<Users />} />
                  <Route path="settings" element={<Settings />} />
                  <Route path="audit" element={<Audit />} />
                </Route>
                <Route path="agency" element={<RequireRole roles={["agency_staff"]}><StaffShell kind="agency" /></RequireRole>}>
                  <Route index element={<AgencyInbox />} />
                  <Route path="reports/:id" element={<ReportWorkbench />} />
                  <Route path="announcements" element={<AgencyAnnouncements />} />
                </Route>
                <Route path="field" element={<RequireRole roles={[]}><StaffShell kind="field" /></RequireRole>}>
                  <Route index element={<FieldTasks />} />
                  <Route path="reports/:id" element={<ReportWorkbench />} />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
