from traceback import format_exception
from typing import Any, Dict, Set, Union

from rich.style import Style
from vedro._core import Dispatcher, ScenarioResult
from vedro._events import ScenarioFailEvent, ScenarioRunEvent, StepFailEvent, StepPassEvent
from vedro.plugins.director import RichReporter
from vedro.plugins.director.rich.utils import format_scope

__all__ = ("GitlabReporter",)


class GitlabReporter(RichReporter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._scenario_result: Union[ScenarioResult, None] = None
        self._scenario_steps: Dict[str, Set[str]] = {}
        self._prev_step_name: Union[str, None] = None

    def subscribe(self, dispatcher: Dispatcher) -> None:
        super().subscribe(dispatcher)
        dispatcher.listen(StepPassEvent, self.on_step_end) \
                  .listen(StepFailEvent, self.on_step_end)

    def on_scenario_run(self, event: ScenarioRunEvent) -> None:
        super().on_scenario_run(event)
        self._scenario_result = event.scenario_result
        self._scenario_steps = {}
        self._prev_step_name = None

    def on_step_end(self, event: StepPassEvent) -> None:
        assert isinstance(self._scenario_result, ScenarioResult)

        step_scope = self._scenario_result.scope.keys() if self._scenario_result.scope else set()
        step_name = event.step_result.step_name
        if self._prev_step_name is not None:
            prev_step_scope = self._scenario_steps[self._prev_step_name]
            self._scenario_steps[step_name] = set(step_scope) - set(prev_step_scope)
        else:
            self._scenario_steps[step_name] = set(step_scope)
        self._prev_step_name = step_name

    def on_scenario_fail(self, event: ScenarioFailEvent) -> None:
        subject = event.scenario_result.scenario_subject
        self._console.print(f" ✗ {subject}", style=Style(color="red"))

        if self._verbosity == 1:
            self._print_steps(event.scenario_result)

        if self._verbosity > 1:
            self._print_exceptions(event.scenario_result)

    def _print_section_start(self, name: str, started_at: int, is_collapsed: bool = True) -> None:
        collapsed = "true" if is_collapsed else "false"
        output = f'\033[0Ksection_start:{started_at}:{name}[collapsed={collapsed}]\r\033[0K'
        self._console.print(output, end="")

    def _print_section_end(self, name: str, ended_at: int) -> None:
        output = f'\033[0Ksection_end:{ended_at}:{name}\r\033[0K'
        self._console.print(output)

    def _print_steps(self, scenario_result: ScenarioResult) -> None:
        for step_result in scenario_result.step_results:
            if step_result.is_passed():
                section_name = f"    ✔ {step_result.step_name}"
            elif step_result.is_failed():
                section_name = f"    ✗ {step_result.step_name}"
            else:
                continue
            started_at = int(step_result.started_at) if step_result.started_at else 0
            self._print_section_start(section_name, started_at)

            scope = scenario_result.scope if scenario_result.scope else {}
            for key, val in format_scope(scope):
                if key in self._scenario_steps[step_result.step_name]:
                    self._console.print(f"       {key}: ", style=Style(color="blue"))
                    self._console.print(val)

            ended_at = int(step_result.ended_at) if step_result.ended_at else 0
            self._print_section_end(section_name, ended_at)

    def _print_exceptions(self, scenario_result: ScenarioResult) -> None:
        for step_result in scenario_result.step_results:
            if step_result.exc_info is None:
                continue
            exc_info = step_result.exc_info
            tb = format_exception(exc_info.type, exc_info.value, exc_info.traceback)
            self._console.print("".join(tb), style=Style(color="yellow"))
