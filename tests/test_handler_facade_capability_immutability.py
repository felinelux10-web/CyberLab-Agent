from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from lab_v4_dev.core.orchestrator_handlers.context import HandlerContext, HandlerFacade
from lab_v4_dev.core.orchestrator_handlers.services import HandlerServices


def test_handler_services_container_is_frozen_but_state_capabilities_remain_mutable():
    analyzed = set()
    services = HandlerServices(analyzed_files=analyzed, db=object())

    with pytest.raises(FrozenInstanceError):
        services.db = object()

    services.analyzed_files.add("src/module.py")
    assert analyzed == {"src/module.py"}


def test_handler_facade_is_frozen_and_still_caches_its_pipeline():
    pipeline = object()
    services = HandlerServices(pipeline_factory=lambda: pipeline)
    facade = HandlerFacade(
        context=SimpleNamespace(current_file=None),
        services=services,
        request=HandlerContext(intent="modify_code"),
    )

    with pytest.raises(FrozenInstanceError):
        facade.services = HandlerServices()

    assert facade._get_pipeline() is pipeline
    assert facade.pipeline is pipeline
    with pytest.raises(FrozenInstanceError):
        facade.pipeline = object()

    # The facade reference is immutable, while the intentionally shared
    # operational context remains writable for legacy handler behavior.
    facade.context.current_file = "src/module.py"
    assert facade.context.current_file == "src/module.py"
