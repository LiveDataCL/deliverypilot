// Todo el texto visible al usuario vive aca (espanol de Chile), nunca suelto en
// JSX (CLAUDE.md SS4). Los componentes importan de este archivo.
export const strings = {
  app: {
    name: 'DeliveryPilot',
  },
  auth: {
    loginTitle: 'Iniciar sesion',
    email: 'Correo electronico',
    password: 'Contrasena',
    submit: 'Entrar',
    invalidCredentials: 'Correo o contrasena incorrectos',
    genericError: 'No se pudo iniciar sesion. Intenta nuevamente.',
    logout: 'Cerrar sesion',
  },
  nav: {
    pedidos: 'Pedidos',
    mapa: 'Mapa',
    clientes: 'Clientes',
    repartidores: 'Repartidores',
    ventas: 'Ventas',
    configuracion: 'Configuracion',
  },
  placeholder: {
    comingInPhase1: 'Esta seccion se construye en la Fase 1.',
  },
  tracking: {
    title: 'Seguimiento de tu pedido',
    comingInPhase2: 'El seguimiento publico en vivo se construye en la Fase 2.',
  },
} as const
