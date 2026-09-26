import React from "react";

/**
 * RouteErrorBoundary — catches a render error in one page so it can't blank
 * the whole app. Sidebar and bottom nav stay usable; AppLayout keys this by
 * pathname so navigating away clears the error.
 */
class RouteErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("Page crashed:", error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="px-4 lg:px-8 py-10" role="alert" data-testid="route-error">
        <div className="bh-surface rounded-md border-t-2 border-t-red-500/60 p-5 max-w-xl">
          <div className="text-[15px] font-semibold text-[var(--bh-ink)]">
            This page hit an error and couldn&rsquo;t load.
          </div>
          <p className="mt-2 text-[13px] text-[var(--bh-ink-3)]">
            The rest of GEAUXleads still works — pick another page from the menu,
            or reload to try again.
          </p>
          <pre className="mt-3 text-[11px] text-[var(--bh-ink-mute)] whitespace-pre-wrap break-words">
            {String(error?.message || error)}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 inline-flex items-center h-9 px-3 rounded-md text-[13px] font-semibold border"
            style={{ borderColor: "var(--bh-hair)", color: "var(--bh-ink)" }}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}

export default RouteErrorBoundary;
