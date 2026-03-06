import { useState } from "react";
import { HelpCircle, X } from "lucide-react";

/**
 * Contextual explainer overlay for charts.
 * Two modes:
 *  - bullets: compact bullet list (default)
 *  - children of `content` prop: rich custom JSX (for diagrams, annotated examples)
 *
 * @param {string} title
 * @param {string[]} [bullets]
 * @param {React.ReactNode} [content] - rich explainer JSX (used instead of bullets when provided)
 * @param {React.ReactNode} children - the chart to wrap
 * @param {"top-right"|"top-left"} [position]
 * @param {boolean} [wide] - wider panel (for rich content)
 */
export function ChartExplainer({
  title,
  bullets = [],
  content,
  children,
  position = "top-right",
  wide = false,
}) {
  const [open, setOpen] = useState(false);

  const hasContent = content || bullets.length > 0;
  if (!hasContent) return children;

  const posClass =
    position === "top-left" ? "left-2 right-auto" : "right-2 left-auto";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`absolute top-1 z-10 flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium transition-all ${posClass} ${
          open
            ? "bg-muted text-muted-foreground"
            : "text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted"
        }`}
        aria-label={`How to read: ${title}`}
      >
        <HelpCircle className="w-3.5 h-3.5" />
        {!open && <span className="hidden sm:inline">How to read</span>}
      </button>

      {open && (
        <div
          className={`absolute top-8 z-20 bg-card border border-border rounded-xl shadow-lg p-4 ${posClass} ${wide ? "w-[420px]" : "w-72"}`}
        >
          <div className="flex items-start justify-between mb-2">
            <h4 className="text-xs font-bold text-foreground uppercase tracking-wide">
              {title}
            </h4>
            <button
              onClick={() => setOpen(false)}
              className="text-muted-foreground/60 hover:text-muted-foreground -mt-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {content ? (
            <div className="text-xs text-muted-foreground leading-relaxed">{content}</div>
          ) : (
            <ul className="space-y-1.5">
              {bullets.map((b, i) => (
                <li key={i} className="flex gap-2 text-xs text-muted-foreground leading-relaxed">
                  <span className="text-accent mt-0.5 shrink-0">&bull;</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {children}
    </div>
  );
}

/**
 * Annotated mini bubble diagram explaining the product portfolio chart.
 * Pure SVG — no data dependencies.
 */
export function BubbleChartGuide() {
  return (
    <div className="space-y-3">
      <svg viewBox="0 0 280 180" className="w-full" aria-hidden>
        {/* axes */}
        <line x1="40" y1="155" x2="270" y2="155" stroke="#e2e8f0" strokeWidth="1" />
        <line x1="40" y1="10" x2="40" y2="155" stroke="#e2e8f0" strokeWidth="1" />

        {/* axis labels */}
        <text x="155" y="175" textAnchor="middle" fontSize="9" fill="#94a3b8">
          Sell-through % →
        </text>
        <text x="12" y="85" textAnchor="middle" fontSize="9" fill="#94a3b8" transform="rotate(-90 12 85)">
          Margin % →
        </text>

        {/* quadrant labels */}
        <text x="70" y="25" fontSize="8" fill="#fca5a5" fontWeight="600">Slow Movers</text>
        <text x="210" y="25" fontSize="8" fill="#86efac" fontWeight="600">★ Stars</text>
        <text x="60" y="148" fontSize="8" fill="#fca5a5">Review</text>
        <text x="190" y="148" fontSize="8" fill="#cbd5e1">Volume Drivers</text>

        {/* quadrant dividers (dashed) */}
        <line x1="155" y1="10" x2="155" y2="155" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4 3" />
        <line x1="40" y1="82" x2="270" y2="82" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="4 3" />

        {/* example bubbles */}
        <circle cx="220" cy="35" r="18" fill="#10b981" opacity="0.6" />
        <circle cx="100" cy="50" r="10" fill="#f59e0b" opacity="0.6" />
        <circle cx="80" cy="120" r="7" fill="#ef4444" opacity="0.5" />
        <circle cx="200" cy="115" r="13" fill="#3b82f6" opacity="0.6" />
        <circle cx="240" cy="60" r="9" fill="#8b5cf6" opacity="0.6" />
        <circle cx="130" cy="80" r="11" fill="#fb923c" opacity="0.5" />

        {/* annotation lines */}
        <line x1="220" y1="53" x2="220" y2="68" stroke="#475569" strokeWidth="0.7" />
        <text x="222" y="78" fontSize="7.5" fill="#475569" fontWeight="600">Big bubble</text>
        <text x="222" y="87" fontSize="7" fill="#94a3b8">= high revenue</text>

        <line x1="80" y1="127" x2="80" y2="140" stroke="#475569" strokeWidth="0.7" />
        <text x="58" y="138" fontSize="7" fill="#94a3b8">needs attention</text>
      </svg>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 pt-1 border-t border-border/50">
        <div className="flex items-start gap-2">
          <span className="text-accent mt-0.5 shrink-0">&bull;</span>
          <span><b className="text-muted-foreground">Position</b> — right = selling fast, top = high margin</span>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-accent mt-0.5 shrink-0">&bull;</span>
          <span><b className="text-muted-foreground">Size</b> — bigger bubble = more revenue generated</span>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-accent mt-0.5 shrink-0">&bull;</span>
          <span><b className="text-muted-foreground">Color</b> — each color is a department</span>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-accent mt-0.5 shrink-0">&bull;</span>
          <span><b className="text-muted-foreground">Click</b> — tap any bubble to see full product details</span>
        </div>
      </div>

      <p className="text-[10px] text-muted-foreground pt-1">
        Top-right products are your <b className="text-success">stars</b>. Bottom-left products need <b className="text-destructive">review</b> — low sales and low margin.
      </p>
    </div>
  );
}
