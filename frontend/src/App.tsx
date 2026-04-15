import { Routes, Route } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import Dashboard from './pages/Dashboard/Dashboard';
import Configurations from './pages/Configurations/Configurations';
import ConfigCreate from './pages/Configurations/ConfigCreate';
import ConfigDetail from './pages/Configurations/ConfigDetail';
import ConfigEdit from './pages/Configurations/ConfigEdit';
import Schedules from './pages/Schedules/Schedules';
import ScheduleCreate from './pages/Schedules/ScheduleCreate';
import ScheduleDetail from './pages/Schedules/ScheduleDetail';
import ScrapePlayground from './pages/ScrapePlayground/ScrapePlayground';
import Jobs from './pages/Jobs/Jobs';
import JobDetail from './pages/Jobs/JobDetail';
import Settings from './pages/Settings/Settings';
import './App.css';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="configurations" element={<Configurations />} />
        <Route path="configurations/new" element={<ConfigCreate />} />
        <Route path="configurations/:id" element={<ConfigDetail />} />
        <Route path="configurations/:id/edit" element={<ConfigEdit />} />
        <Route path="schedules" element={<Schedules />} />
        <Route path="schedules/new" element={<ScheduleCreate />} />
        <Route path="schedules/:id" element={<ScheduleDetail />} />
        <Route path="scrape" element={<ScrapePlayground />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:id" element={<JobDetail />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
