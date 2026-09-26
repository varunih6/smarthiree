import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout, ProtectedRoute } from "./components/Layout";
import ApplicationDetail from "./pages/admin/ApplicationDetail";
import Jobs, { JobDetail } from "./pages/admin/Jobs";
import Overview from "./pages/admin/Overview";
import { AuditLogs, Candidates, Interviewers } from "./pages/admin/People";
import Pipeline from "./pages/admin/Pipeline";
import Schedule from "./pages/admin/Schedule";
import Assessment from "./pages/candidate/Assessment";
import { CandidateDashboard, CandidateJobs } from "./pages/candidate/Candidate";
import { Availability, InterviewDetail, Interviews } from "./pages/interviewer/Interviewer";
import { Landing, Login, Register, ResetPassword } from "./pages/public/Public";

export default function App() {
  return (
    <Routes>
      {/* public */}
      <Route path="/" element={<Landing />} />
      <Route path="/login/:role" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/reset-password/:role" element={<ResetPassword />} />

      {/* admin */}
      <Route element={<ProtectedRoute role="admin" />}>
        <Route path="/admin" element={<AppLayout role="admin" />}>
          <Route index element={<Overview />} />
          <Route path="pipeline" element={<Pipeline />} />
          <Route path="applications/:id" element={<ApplicationDetail />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="schedule" element={<Schedule />} />
          <Route path="interviewers" element={<Interviewers />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="audit" element={<AuditLogs />} />
        </Route>
      </Route>

      {/* interviewer */}
      <Route element={<ProtectedRoute role="interviewer" />}>
        <Route path="/interviewer" element={<AppLayout role="interviewer" />}>
          <Route index element={<Interviews />} />
          <Route path="availability" element={<Availability />} />
          <Route path="interviews/:id" element={<InterviewDetail />} />
        </Route>
      </Route>

      {/* candidate */}
      <Route element={<ProtectedRoute role="candidate" />}>
        <Route path="/candidate" element={<AppLayout role="candidate" />}>
          <Route index element={<CandidateDashboard />} />
          <Route path="jobs" element={<CandidateJobs />} />
        </Route>
        <Route path="/candidate/assessment/:appId" element={<Assessment />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
