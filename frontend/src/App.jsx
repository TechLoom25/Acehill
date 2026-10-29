import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import { Spinner } from "./components/ui.jsx";
import Account from "./pages/Account.jsx";
import BulkSms from "./pages/BulkSms.jsx";
import Customers from "./pages/Customers.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Finance from "./pages/Finance.jsx";
import Login from "./pages/Login.jsx";
import NewRepair from "./pages/NewRepair.jsx";
import RepairDetail from "./pages/RepairDetail.jsx";
import Repairs from "./pages/Repairs.jsx";
import Setup from "./pages/Setup.jsx";
import Staff from "./pages/Staff.jsx";
import Track from "./pages/Track.jsx";

function Splash() {
  const { bootError, retryBoot } = useAuth();
  return (
    <div className="splash">
      {bootError ? (
        <div className="card stack" style={{ maxWidth: 420 }}>
          <h2>Can't reach the server</h2>
          <p className="muted">{bootError}</p>
          <button className="btn" onClick={retryBoot}>Try again</button>
        </div>
      ) : <Spinner />}
    </div>
  );
}

/** Signed-in area: sends visitors to first-run setup or login as needed. */
function RequireAuth() {
  const { user, booting, bootError, needsSetup } = useAuth();
  const location = useLocation();
  if (booting || bootError) return <Splash />;
  if (needsSetup) return <Navigate to="/setup" replace />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Layout />;
}

function RequireAccess({ action, children }) {
  const { can } = useAuth();
  return can(action) ? children : <Navigate to="/" replace />;
}

/** Login and setup screens: bounce away if they no longer apply. */
function PublicOnly({ page }) {
  const { user, booting, bootError, needsSetup } = useAuth();
  if (booting || bootError) return <Splash />;
  if (user) return <Navigate to="/" replace />;
  if (page === "login" && needsSetup) return <Navigate to="/setup" replace />;
  if (page === "setup" && !needsSetup) return <Navigate to="/login" replace />;
  return page === "setup" ? <Setup /> : <Login />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/track" element={<Track />} />
      <Route path="/login" element={<PublicOnly page="login" />} />
      <Route path="/setup" element={<PublicOnly page="setup" />} />

      <Route element={<RequireAuth />}>
        <Route index element={<Dashboard />} />
        <Route path="repairs" element={<Repairs />} />
        <Route path="repairs/new" element={<RequireAccess action="intake"><NewRepair /></RequireAccess>} />
        <Route path="repairs/:id" element={<RepairDetail />} />
        <Route path="customers" element={<RequireAccess action="money"><Customers /></RequireAccess>} />
        <Route path="finance" element={<RequireAccess action="finance"><Finance /></RequireAccess>} />
        <Route path="sms" element={<RequireAccess action="sms"><BulkSms /></RequireAccess>} />
        <Route path="staff" element={<RequireAccess action="staff"><Staff /></RequireAccess>} />
        <Route path="account" element={<Account />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
