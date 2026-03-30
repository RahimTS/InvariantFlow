from pydantic import BaseModel


class CreateShipmentRequest(BaseModel):
    weight: int
    origin: str
    destination: str


class AssignVehicleRequest(BaseModel):
    vehicle_id: str
