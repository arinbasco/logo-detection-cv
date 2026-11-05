import { useCallback, useState } from "react"
import { createBrowserRouter, Navigate } from "react-router"
import { RouterProvider } from "react-router/dom"

import type { Configuracion } from "@/api/cliente"
import { Marco } from "@/components/Marco"
import { PantallaCarga } from "@/components/PantallaCarga"
import { ProveedorApp } from "@/estado/app"
import { conTransicion } from "@/hooks/sistema"
import { Analisis } from "@/paginas/Analisis"
import { EnVivo } from "@/paginas/EnVivo"
import { Informe } from "@/paginas/Informe"
import { NoEncontrada } from "@/paginas/NoEncontrada"

const router = createBrowserRouter([
  {
    path: "/",
    element: <Marco />,
    children: [
      { index: true, element: <Navigate to="/analisis" replace /> },
      { path: "analisis", element: <Analisis /> },
      { path: "en-vivo", element: <EnVivo /> },
      { path: "informe/:id", element: <Informe /> },
      { path: "*", element: <NoEncontrada /> },
    ],
  },
])

interface Arranque {
  config: Configuracion
  marcas: string[]
}

export default function App() {
  const [arranque, setArranque] = useState<Arranque | null>(null)
  const alTerminar = useCallback((config: Configuracion, marcas: string[]) => {
    conTransicion(() => setArranque({ config, marcas }))
  }, [])

  // La pantalla de carga aparece una vez al abrir la web, sea cual sea la dirección
  if (!arranque) return <PantallaCarga alTerminar={alTerminar} />

  return (
    <ProveedorApp config={arranque.config} marcas={arranque.marcas}>
      <RouterProvider router={router} />
    </ProveedorApp>
  )
}
