import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Scout UI crashed", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="fatal">
        <p className="eyebrow">UI error</p>
        <h1>页面出错了</h1>
        <p className="muted">
          渲染时发生异常。运行数据仍保存在后端，刷新页面不会丢。
        </p>
        <pre className="fatal-detail">{this.state.error.message}</pre>
        <div className="fatal-actions">
          <button type="button" onClick={() => window.location.reload()}>
            重新加载
          </button>
          <a href="/task">回到任务页</a>
        </div>
      </div>
    );
  }
}
