import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Catches render-time errors in the page area so a single broken screen shows a
// readable message instead of blanking the whole app (React unmounts the tree
// on an uncaught render error). Reset by navigating or reloading.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the details in the console for debugging.
    console.error("Page render error:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, maxWidth: 800 }}>
          <h2 style={{ marginTop: 0 }}>Something went wrong on this screen</h2>
          <p style={{ color: "var(--slate-600)" }}>
            The page hit an error and couldn't render. Try reloading; if it persists, share the
            message below.
          </p>
          <pre
            style={{
              background: "var(--slate-50, #f8fafc)",
              border: "1px solid var(--color-separator, #e2e8f0)",
              borderRadius: 8,
              padding: 12,
              fontSize: 12,
              whiteSpace: "pre-wrap",
              overflowX: "auto",
            }}
          >
            {this.state.error.message}
            {"\n\n"}
            {this.state.error.stack}
          </pre>
          <button onClick={() => this.setState({ error: null })} style={{ marginTop: 8 }}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
