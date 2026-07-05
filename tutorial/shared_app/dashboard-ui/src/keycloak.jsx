import { createContext, useContext, useState, useEffect, useRef } from 'react'
import Keycloak from 'keycloak-js'

const defaultState = {
  keycloak: null,
  authenticated: false,
  token: null,
  username: null,
}

const KeycloakContext = createContext(defaultState)

export function useKeycloak() {
  return useContext(KeycloakContext)
}

export function KeycloakProvider({ config, children }) {
  const [state, setState] = useState(defaultState)
  const [ready, setReady] = useState(false)
  const initRef = useRef(false)

  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    const kc = new Keycloak({
      url: config.url,
      realm: config.realm,
      clientId: config.clientId,
    })

    kc.onTokenExpired = () => {
      kc.updateToken(30)
        .then(() => {
          setState(prev => ({
            ...prev,
            token: kc.token || null,
          }))
        })
        .catch(() => {
          kc.login()
        })
    }

    kc.init({ onLoad: 'login-required' })
      .then((authenticated) => {
        setState({
          keycloak: kc,
          authenticated,
          token: kc.token || null,
          username: kc.tokenParsed?.preferred_username || null,
        })
        setReady(true)
      })
      .catch(() => {
        setReady(true)
      })
  }, [config])

  if (!ready) {
    return (
      <div className="flex items-center justify-center min-h-screen text-muted-foreground">
        Connecting to authentication server...
      </div>
    )
  }

  return (
    <KeycloakContext.Provider value={state}>
      {children}
    </KeycloakContext.Provider>
  )
}
