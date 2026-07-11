import { Library, Compass, Cpu, Settings } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

export type NavTab = "bookshelf" | "explore" | "memory" | "settings";

interface BottomNavProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
}

export function BottomNav({ activeTab, onSelectTab }: BottomNavProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // If inside reader mode (/read/:id), auto-hide bottom dock
  const isReader = location.pathname.startsWith("/read/");
  if (isReader) return null;

  const items = [
    { id: "bookshelf" as NavTab, label: "Bookshelf", icon: Library },
    { id: "explore" as NavTab, label: "Explore", icon: Compass },
    { id: "memory" as NavTab, label: "Memory Engine", icon: Cpu },
    { id: "settings" as NavTab, label: "Settings", icon: Settings },
  ];

  const handleNav = (tab: NavTab) => {
    onSelectTab(tab);
    if (location.pathname !== "/") {
      navigate("/");
    }
  };

  return (
    <>
      {/* Mobile Bottom Dock (fixed at bottom on < md screens) */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-40 md:hidden glass-surface border-t py-1.5 px-3 flex justify-around items-center transition-all duration-200"
        style={{ borderColor: "var(--color-border)" }}
      >
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id && location.pathname === "/";
          return (
            <button
              key={item.id}
              onClick={() => handleNav(item.id)}
              className={`flex flex-col items-center justify-center py-1 px-3 rounded-xl transition-all duration-150 cursor-pointer ${
                isActive ? "scale-105" : "opacity-60 hover:opacity-90"
              }`}
              style={{
                color: isActive
                  ? "var(--color-accent)"
                  : "var(--color-text-muted)",
              }}
            >
              <div className="relative">
                <Icon
                  className="w-5 h-5 mb-0.5"
                  strokeWidth={isActive ? 2.5 : 1.8}
                />
                {isActive && (
                  <span
                    className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: "var(--color-accent)" }}
                  />
                )}
              </div>
              <span className="text-[10px] font-medium tracking-tight mt-1">
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Desktop / Tablet Vertical Side Dock (hidden on < md screens) */}
      <aside
        className="hidden md:flex flex-col fixed left-0 top-0 bottom-0 w-64 z-30 glass-surface border-r py-6 px-4 justify-between"
        style={{ borderColor: "var(--color-border)" }}
      >
        <div>
          {/* Brand Logo */}
          <div
            className="flex items-center gap-3 px-3 mb-8 cursor-pointer"
            onClick={() => handleNav("bookshelf")}
          >
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-white shadow-lg glow-accent"
              style={{
                background:
                  "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
              }}
            >
              TN
            </div>
            <div>
              <h1
                className="text-base font-bold tracking-tight leading-none"
                style={{ color: "var(--color-text)" }}
              >
                Webnovel{" "}
                <span style={{ color: "var(--color-accent)" }}>AI</span>
              </h1>
              <p
                className="text-[10px] mt-0.5 tracking-wider uppercase font-semibold opacity-60"
                style={{ color: "var(--color-text-muted)" }}
              >
                Memory Engine
              </p>
            </div>
          </div>

          {/* Nav Items */}
          <div className="space-y-1.5">
            {items.map((item) => {
              const Icon = item.icon;
              const isActive =
                activeTab === item.id && location.pathname === "/";
              return (
                <button
                  key={item.id}
                  onClick={() => handleNav(item.id)}
                  className={`w-full flex items-center gap-3.5 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 cursor-pointer ${
                    isActive
                      ? "shadow-md glow-accent"
                      : "hover:bg-white/5 opacity-70 hover:opacity-100"
                  }`}
                  style={{
                    backgroundColor: isActive
                      ? "var(--color-surface-hover)"
                      : "transparent",
                    color: isActive
                      ? "var(--color-accent)"
                      : "var(--color-text)",
                    border: isActive
                      ? "1px solid var(--color-border)"
                      : "1px solid transparent",
                  }}
                >
                  <Icon
                    className="w-4 h-4"
                    strokeWidth={isActive ? 2.5 : 1.8}
                  />
                  <span>{item.label}</span>
                  {isActive && (
                    <div
                      className="ml-auto w-1.5 h-4 rounded-full"
                      style={{ backgroundColor: "var(--color-accent)" }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* AI Engine Status Indicator at bottom of sidebar */}
        <div
          className="p-3.5 rounded-xl border space-y-2"
          style={{
            backgroundColor: "var(--color-surface)",
            borderColor: "var(--color-border)",
          }}
        >
          <div className="flex items-center justify-between">
            <span
              className="text-xs font-semibold flex items-center gap-1.5"
              style={{ color: "var(--color-text)" }}
            >
              <span
                className="w-2 h-2 rounded-full animate-pulse"
                style={{ backgroundColor: "var(--color-success)" }}
              />
              AI Memory Engine
            </span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium"
              style={{
                backgroundColor: "var(--color-ai-glow)",
                color: "var(--color-ai)",
              }}
            >
              v1.0
            </span>
          </div>
          <p
            className="text-[11px] leading-tight opacity-75"
            style={{ color: "var(--color-text-muted)" }}
          >
            Real-time translation refinement & policy injection active.
          </p>
        </div>
      </aside>
    </>
  );
}
