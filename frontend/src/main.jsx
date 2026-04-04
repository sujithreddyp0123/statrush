import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{background:"#090909",color:"#FF6B00",padding:40,fontFamily:"monospace",minHeight:"100vh"}}>
          <h2>⚡ StatRush — Render Error</h2>
          <pre style={{color:"#ff6b6b",fontSize:13,marginTop:20,whiteSpace:"pre-wrap"}}>{this.state.error?.toString()}</pre>
          <pre style={{color:"rgba(255,255,255,0.5)",fontSize:11,marginTop:10,whiteSpace:"pre-wrap"}}>{this.state.error?.stack}</pre>
          <button onClick={() => window.location.reload()} style={{marginTop:20,padding:"8px 16px",background:"#FF6B00",color:"#fff",border:"none",borderRadius:8,cursor:"pointer"}}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
)
