import { Routes, Route } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import Dashboard from './pages/Dashboard/Dashboard';
import Configurations from './pages/Configurations/Configurations';
import ScrapePlayground from './pages/ScrapePlayground/ScrapePlayground';
import Jobs from './pages/Jobs/Jobs';
import Settings from './pages/Settings/Settings';
import './App.css';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="configurations" element={<Configurations />} />
        <Route path="scrape" element={<ScrapePlayground />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
