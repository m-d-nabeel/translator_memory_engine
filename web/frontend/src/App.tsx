import { Routes, Route } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { NovelView } from "./pages/NovelView";
import { Reader } from "./pages/Reader";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/novels/:id" element={<NovelView />} />
      <Route path="/read/:chapterId" element={<Reader />} />
    </Routes>
  );
}
