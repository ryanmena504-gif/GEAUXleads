import "@/App.css";
import { lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";

import AppLayout from "@/layouts/AppLayout";
import CommandCenter from "@/pages/CommandCenter";

// Home loads eagerly; every other page is split into its own chunk so the
// phone only downloads the screen Ryan actually opens.
const Opportunities = lazy(() => import("@/pages/Opportunities"));
const OpportunityDetail = lazy(() => import("@/pages/OpportunityDetail"));
const Missions = lazy(() => import("@/pages/Missions"));
const Relationships = lazy(() => import("@/pages/Relationships"));
const Intelligence = lazy(() => import("@/pages/Intelligence"));
const ReviewQueue = lazy(() => import("@/pages/ReviewQueue"));
const Settings = lazy(() => import("@/pages/Settings"));
const Lookup = lazy(() => import("@/pages/Lookup"));
const DebugPanel = lazy(() => import("@/pages/DebugPanel"));
const DiscoveryPropertyManagers = lazy(() => import("@/pages/DiscoveryPropertyManagers"));
const DiscoveryRealEstateAgents = lazy(() => import("@/pages/DiscoveryRealEstateAgents"));
const DiscoveryLandlords = lazy(() => import("@/pages/DiscoveryLandlords"));
const LandlordLetterPrint = lazy(() => import("@/pages/LandlordLetterPrint"));
const DiscoveryInvestors = lazy(() => import("@/pages/DiscoveryInvestors"));
const PassReasons = lazy(() => import("@/pages/PassReasons"));

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<CommandCenter />} />
            <Route path="/opportunities" element={<Opportunities />} />
            <Route path="/opportunities/:id" element={<OpportunityDetail />} />
            <Route path="/missions" element={<Missions />} />
            <Route path="/relationships" element={<Relationships />} />
            <Route path="/intelligence" element={<Intelligence />} />
            <Route path="/review-queue" element={<ReviewQueue />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/lookup" element={<Lookup />} />
            <Route path="/debug" element={<DebugPanel />} />
            <Route path="/discovery/property-managers" element={<DiscoveryPropertyManagers />} />
            <Route path="/discovery/real-estate-agents" element={<DiscoveryRealEstateAgents />} />
            <Route path="/discovery/landlords" element={<DiscoveryLandlords />} />
            <Route path="/discovery/landlords/print" element={<LandlordLetterPrint />} />
            <Route path="/discovery/investors" element={<DiscoveryInvestors />} />
            <Route path="/pass-reasons" element={<PassReasons />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" theme="light" />
    </div>
  );
}

export default App;
