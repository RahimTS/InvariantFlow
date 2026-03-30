from app.eval.condition_parser import can_evaluate, evaluate


def test_can_evaluate_supported_patterns() -> None:
    assert can_evaluate("entities.shipment.dispatched_at != null")
    assert can_evaluate("entities.shipment.status in ['CREATED', 'ASSIGNED']")
    assert can_evaluate("entities.shipment.status == 'ASSIGNED'")
    assert can_evaluate("scenario.shipment_weight <= entities.vehicle.capacity")


def test_evaluate_numeric_comparison() -> None:
    context = {
        "scenario": {"shipment_weight": 1200},
        "entities": {"vehicle": {"capacity": 1000}},
    }
    assert evaluate("scenario.shipment_weight <= entities.vehicle.capacity", context) is False


def test_evaluate_equality_and_null_and_membership() -> None:
    context = {
        "entities": {
            "shipment": {
                "status": "ASSIGNED",
                "dispatched_at": None,
            }
        }
    }
    assert evaluate("entities.shipment.status == 'ASSIGNED'", context) is True
    assert evaluate("entities.shipment.dispatched_at == null", context) is True
    assert evaluate("entities.shipment.status in ['CREATED', 'ASSIGNED']", context) is True


def test_evaluate_returns_none_for_unsupported_condition() -> None:
    context = {"entities": {"shipment": {"status": "ASSIGNED"}}}
    assert evaluate("delivery address must be serviceable", context) is None

