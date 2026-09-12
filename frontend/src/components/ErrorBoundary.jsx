import { Component } from 'react'

// Last-resort catch-all: without this, any render error anywhere in the tree
// unmounts the whole app to a blank page with nothing in the DOM to tell the
// user (or a screenshot) what happened. This turns that into a recoverable
// screen instead.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled render error:', error, info)
  }

  reset = () => {
    // A stale/corrupt localStorage entry is the most common cause of a crash
    // this early -- clearing session state before retrying gives the user a
    // real second chance instead of reloading straight back into the same crash.
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('user')
    window.location.href = '/login'
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', padding: '2rem',
          fontFamily: 'system-ui, sans-serif', textAlign: 'center', gap: '1rem',
          background: '#04070d', color: '#e2e8f0',
        }}>
          <div style={{ fontSize: '2.5rem' }}>⚠️</div>
          <h1 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Something went wrong</h1>
          <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: 480 }}>
            {this.state.error.message || 'The app hit an unexpected error and could not render.'}
          </p>
          <button onClick={this.reset}
            style={{
              background: '#0284c7', color: 'white', fontWeight: 600, fontSize: '0.85rem',
              padding: '0.5rem 1.25rem', borderRadius: '0.5rem', border: 'none', cursor: 'pointer',
            }}>
            Reset & go to login
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
