import React from "react";

type Props = {
  children: React.ReactNode;
};

type State = {
  hasError: boolean;
  errorMessage: string;
};

export class AppErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      errorMessage: "",
    };
  }

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      errorMessage: error instanceof Error ? error.message : String(error),
    };
  }

  componentDidCatch(error: unknown, errorInfo: React.ErrorInfo) {
    console.error("AppErrorBoundary", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
          <div className="w-full max-w-2xl rounded-xl border border-destructive/30 bg-card p-6 space-y-3">
            <h1 className="text-xl font-semibold">La app encontró un error</h1>
            <p className="text-sm text-muted-foreground">
              Ya no debería quedar una pantalla negra. Este es el error capturado:
            </p>
            <pre className="overflow-auto rounded-md bg-muted p-4 text-sm whitespace-pre-wrap break-words">
              {this.state.errorMessage || "Error desconocido"}
            </pre>
            <button
              className="rounded-md border border-border px-3 py-2 text-sm hover:bg-muted"
              onClick={() => window.location.reload()}
            >
              Recargar
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
