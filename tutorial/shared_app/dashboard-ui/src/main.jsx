import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { KeycloakProvider } from './keycloak'
import './globals.css'

function Root() {
  const [keycloakConfig, setKeycloakConfig] = useState(undefined)

  useEffect(() => {
    fetch('/keycloak-config.json')
      .then(res => {
        if (res.ok) return res.json()
        return null
      })
      .then(config => {
        setKeycloakConfig(config?.url ? config : null)
      })
      .catch(() => {
        setKeycloakConfig(null)
      })
  }, [])

  if (keycloakConfig === undefined) return null

  if (keycloakConfig) {
    return (
      <KeycloakProvider config={keycloakConfig}>
        <App />
      </KeycloakProvider>
    )
  }

  return <App />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
)
