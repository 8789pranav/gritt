"""
Engine registry.

Maps a :class:`~app.domain.enums.TestType` to its engine instance. Callers ask
the registry for an engine rather than importing a concrete class, so adding a
fifth assessment means writing the engine package and registering it here -
no changes to services or routers.

Engines are instantiated lazily and then reused, because each one caches its
question bank in memory after the first read.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Iterator, List, Optional

from app.core.exceptions import ValidationError
from app.domain.enums import TestType
from app.engines.base import AssessmentEngine
from app.engines.comprehension import ComprehensionEngine
from app.engines.logic import LogicEngine
from app.engines.speaking import SpeakingEngine
from app.engines.spelling import SpellingEngine

logger = logging.getLogger(__name__)

EngineFactory = Callable[[], AssessmentEngine]

#: Every assessment the platform knows how to run.
_FACTORIES: Dict[TestType, EngineFactory] = {
    TestType.LOGIC: LogicEngine,
    TestType.SPELLING: SpellingEngine,
    TestType.SPEAKING: SpeakingEngine,
    TestType.COMPREHENSION: ComprehensionEngine,
}

_instances: Dict[TestType, AssessmentEngine] = {}
_lock = threading.Lock()


class UnknownTestError(ValidationError):
    """Raised when a caller asks for an assessment that is not registered."""

    error_code = "unknown_test"

    def __init__(self, value: str) -> None:
        super().__init__(
            f"Unknown assessment: {value!r}",
            details={"supported": [test.value for test in _FACTORIES]},
        )


def register(test: TestType, factory: EngineFactory) -> None:
    """Register (or replace) the engine factory for an assessment."""
    with _lock:
        _FACTORIES[test] = factory
        _instances.pop(test, None)
    logger.debug("Registered engine for %s", test.value)


def get_engine(test: TestType) -> AssessmentEngine:
    """Return the shared engine instance for ``test``."""
    engine = _instances.get(test)
    if engine is not None:
        return engine

    factory = _FACTORIES.get(test)
    if factory is None:
        raise UnknownTestError(test.value if isinstance(test, TestType) else str(test))

    with _lock:
        # Another thread may have built it while we waited for the lock.
        engine = _instances.get(test)
        if engine is None:
            engine = factory()
            _instances[test] = engine
            logger.debug("Instantiated %s engine", test.value)

    return engine


def resolve(value: str) -> AssessmentEngine:
    """Return the engine for a test name supplied by a client."""
    try:
        test = TestType(str(value).strip().lower())
    except ValueError as exc:
        raise UnknownTestError(str(value)) from exc
    return get_engine(test)


def logic_engine() -> LogicEngine:
    """Typed accessor for the Logic Quest engine."""
    engine = get_engine(TestType.LOGIC)
    assert isinstance(engine, LogicEngine)
    return engine


def spelling_engine() -> SpellingEngine:
    """Typed accessor for the spelling engine."""
    engine = get_engine(TestType.SPELLING)
    assert isinstance(engine, SpellingEngine)
    return engine


def speaking_engine() -> SpeakingEngine:
    """Typed accessor for the speaking engine."""
    engine = get_engine(TestType.SPEAKING)
    assert isinstance(engine, SpeakingEngine)
    return engine


def comprehension_engine() -> ComprehensionEngine:
    """Typed accessor for the comprehension engine."""
    engine = get_engine(TestType.COMPREHENSION)
    assert isinstance(engine, ComprehensionEngine)
    return engine


def registered_tests() -> List[TestType]:
    """Every assessment currently registered."""
    return list(_FACTORIES)


def all_engines() -> Iterator[AssessmentEngine]:
    """Iterate over every registered engine, instantiating as needed."""
    for test in _FACTORIES:
        yield get_engine(test)


def reset() -> None:
    """Drop cached engine instances. Intended for tests."""
    with _lock:
        _instances.clear()
