/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Dirección del backend, por ejemplo http://127.0.0.1:8001 */
  readonly VITE_API_URL?: string
  /** Vídeo grabado de la demo para la página En vivo de la versión nube. Opcional */
  readonly VITE_VIDEO_DEMO_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
