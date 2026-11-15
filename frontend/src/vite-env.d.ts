/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** where the API lives when it is not proxied at /api, e.g. https://api.example.org/api */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
