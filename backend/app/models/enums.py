import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    business_owner = "business_owner"
    dispatcher = "dispatcher"
    driver = "driver"


class DriverStatus(str, enum.Enum):
    offline = "offline"
    online = "online"
    busy = "busy"


class PaymentMethodType(str, enum.Enum):
    efectivo = "efectivo"
    transferencia = "transferencia"
    pos = "pos"
    online = "online"
    otro = "otro"


class OrderStatus(str, enum.Enum):
    pendiente = "pendiente"
    asignado = "asignado"
    aceptado = "aceptado"
    recogido = "recogido"
    en_ruta = "en_ruta"
    entregado = "entregado"
    cancelado = "cancelado"
    fallido = "fallido"


class ProofType(str, enum.Enum):
    photo = "photo"
    signature = "signature"
