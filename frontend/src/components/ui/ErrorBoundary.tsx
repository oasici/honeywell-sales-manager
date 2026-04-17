import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from './Button';
import { AlertTriangle } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const errorMessage = this.state.error?.message ?? 'Bilinmeyen hata';
      const errorStack = this.state.error?.stack ?? '';
      return (
        <div className="flex min-h-[400px] flex-col items-center justify-center px-4 text-center">
          <div className="mb-4"><AlertTriangle size={48} className="text-red-400" /></div>
          <h2 className="mb-2 text-xl font-semibold text-gray-900">
            Bir hata oluştu
          </h2>
          <p className="mb-4 max-w-md text-sm text-gray-500">
            Beklenmeyen bir hata meydana geldi. Lütfen tekrar deneyin.
          </p>
          <details className="mb-6 w-full max-w-lg text-left">
            <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-600">
              Hata detaylari
            </summary>
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-gray-100 p-3 text-xs text-red-600 whitespace-pre-wrap break-all">
              {errorMessage}
              {errorStack && `\n\n${errorStack}`}
            </pre>
          </details>
          <Button variant="primary" onClick={this.handleRetry}>
            Tekrar Dene
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
