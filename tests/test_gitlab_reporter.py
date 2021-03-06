from argparse import Namespace
from contextlib import contextmanager
from typing import Optional, Union
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
from baby_steps import given, then, when
from rich.console import Console
from rich.style import Style
from vedro.core import Dispatcher
from vedro.events import ArgParsedEvent, ScenarioFailedEvent, ScenarioRunEvent, StepFailedEvent
from vedro.plugins.director import DirectorPlugin, Reporter
from vedro.plugins.director.rich.test_utils import (
    chose_reporter,
    console_,
    director,
    dispatcher,
    make_scenario_result,
    make_step_result,
)

from vedro_gitlab_reporter import GitlabCollapsableMode, GitlabReporter, GitlabReporterPlugin

__all__ = ("dispatcher", "console_", "director", "chose_reporter",)


@pytest.fixture()
def reporter(dispatcher: Dispatcher, console_: Console) -> GitlabReporterPlugin:
    reporter = GitlabReporterPlugin(GitlabReporter, console_factory=lambda: console_)
    reporter.subscribe(dispatcher)
    return reporter


@contextmanager
def patch_uuid(uuid: Optional[str] = None):
    if uuid is None:
        uuid = str(uuid4())
    with patch("uuid.uuid4", Mock(return_value=uuid)):
        yield uuid


def make_parsed_args(*,
                     verbose: int = 0,
                     gitlab_collapsable: Union[GitlabCollapsableMode, None] = None) -> Namespace:
    return Namespace(
        verbose=verbose,
        gitlab_collapsable=gitlab_collapsable,
        show_timings=False,
        show_paths=False,
        tb_show_internal_calls=False,
        tb_show_locals=False,
        reruns=0,
    )


def test_gitlab_reporter():
    with when:
        reporter = GitlabReporterPlugin(GitlabReporter)

    with then:
        assert isinstance(reporter, Reporter)


@pytest.mark.asyncio
async def test_reporter_scenario_run_event(*, dispatcher: Dispatcher,
                                           director: DirectorPlugin,
                                           reporter: GitlabReporterPlugin, console_: Mock):
    with given:
        await chose_reporter(dispatcher, director, reporter)

        scenario_result = make_scenario_result()
        event = ScenarioRunEvent(scenario_result)

    with when:
        await dispatcher.fire(event)

    with then:
        assert console_.mock_calls == [
            call.out(f"* {scenario_result.scenario.namespace}", style=Style.parse("bold"))
        ]


@pytest.mark.parametrize("args", [
    make_parsed_args(verbose=0),  # backward compatibility
    make_parsed_args(gitlab_collapsable=None),
])
@pytest.mark.asyncio
async def test_reporter_scenario_failed_event_verbose0(args: Namespace, *,
                                                       dispatcher: Dispatcher,
                                                       director: DirectorPlugin,
                                                       reporter: GitlabReporterPlugin,
                                                       console_: Mock):
    with given:
        await chose_reporter(dispatcher, director, reporter)
        await dispatcher.fire(ArgParsedEvent(args))

        scenario_result = make_scenario_result().mark_failed()
        event = ScenarioFailedEvent(scenario_result)

    with when:
        await dispatcher.fire(event)

    with then:
        assert console_.mock_calls == [
            call.out(f" ??? {scenario_result.scenario.subject}", style=Style.parse("red"))
        ]


@pytest.mark.parametrize("args", [
    make_parsed_args(verbose=1),  # backward compatibility
    make_parsed_args(gitlab_collapsable=GitlabCollapsableMode.STEPS),
])
@pytest.mark.asyncio
async def test_reporter_scenario_failed_event_verbose1(args: Namespace, *,
                                                       dispatcher: Dispatcher,
                                                       director: DirectorPlugin,
                                                       reporter: GitlabReporterPlugin,
                                                       console_: Mock):
    with given:
        await chose_reporter(dispatcher, director, reporter)
        await dispatcher.fire(ArgParsedEvent(args))

        step_result = make_step_result().mark_failed().set_started_at(1.0).set_ended_at(3.0)
        scenario_result = make_scenario_result(step_results=[step_result]).mark_failed()
        event = ScenarioFailedEvent(scenario_result)

    with when, patch_uuid() as uuid:
        await dispatcher.fire(event)

    with then:
        assert console_.mock_calls == [
            call.out(f" ??? {scenario_result.scenario.subject}", style=Style.parse("red")),
            call.file.write(f"\x1b[0Ksection_start:{int(step_result.started_at)}:{uuid}"
                            "[collapsed=true]\r\x1b[0K"),
            call.out(f"    ??? {step_result.step_name}", style=Style.parse("red")),
            call.file.write(f"\x1b[0Ksection_end:{int(step_result.ended_at)}:{uuid}\r\x1b[0K")
        ]


@pytest.mark.parametrize("args", [
    make_parsed_args(verbose=2),  # backward compatibility
    make_parsed_args(gitlab_collapsable=GitlabCollapsableMode.VARS),
])
@pytest.mark.asyncio
async def test_reporter_scenario_failed_event_verbose2(args: Namespace, *,
                                                       dispatcher: Dispatcher,
                                                       director: DirectorPlugin,
                                                       reporter: GitlabReporterPlugin,
                                                       console_: Mock):
    with given:
        await chose_reporter(dispatcher, director, reporter)
        await dispatcher.fire(ArgParsedEvent(args))

        scenario_result = make_scenario_result()
        await dispatcher.fire(ScenarioRunEvent(scenario_result))
        console_.reset_mock()

        scenario_result.set_scope({"key": "val"})
        step_result = make_step_result().mark_failed()
        await dispatcher.fire(StepFailedEvent(step_result))

        scenario_result = scenario_result.mark_failed()
        scenario_result.add_step_result(step_result)
        event = ScenarioFailedEvent(scenario_result)

    with when, patch_uuid() as uuid:
        await dispatcher.fire(event)

    with then:
        assert console_.mock_calls == [
            call.out(f" ??? {scenario_result.scenario.subject}", style=Style.parse("red")),
            call.out(f"    ??? {step_result.step_name}", style=Style.parse("red")),
            call.file.write(f"\x1b[0Ksection_start:0:{uuid}[collapsed=true]\r\x1b[0K"),
            call.out("      key: ", style=Style.parse("blue")),
            call.out("\"val\""),
            call.file.write(f"\x1b[0Ksection_end:0:{uuid}\r\x1b[0K")
        ]
