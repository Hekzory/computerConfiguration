"""Test the stdout callback's verbosity choice without installing Ansible."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class DebugCallback:
    def _run_is_verbose(self, result, verbosity=0):
        return self._display.verbosity > verbosity


def load_callback():
    module_name = 'ansible_collections.ansible.posix.plugins.callback.debug'
    packages = [module_name.rsplit('.', n)[0] for n in range(1, 6)]
    modules = {name: ModuleType(name) for name in (*packages, module_name)}
    modules[module_name].CallbackModule = DebugCallback
    path = Path(__file__).resolve().parents[1] / 'callback_plugins/quiet_ok.py'
    spec = importlib.util.spec_from_file_location('quiet_ok_under_test', path)
    plugin = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(plugin)
    return plugin.CallbackModule


class QuietOkTest(unittest.TestCase):
    def setUp(self):
        self.callback = load_callback()()
        self.callback._display = SimpleNamespace(verbosity=1)

    @staticmethod
    def result(state):
        return SimpleNamespace(
            is_changed=lambda: state == 'changed',
            is_failed=lambda: state == 'failed',
            is_unreachable=lambda: state == 'unreachable',
            is_skipped=lambda: state == 'skipped',
        )

    def test_unchanged_and_skipped_are_compact_at_every_verbosity(self):
        for verbosity in (1, 2, 3):
            self.callback._display.verbosity = verbosity
            for state in ('ok', 'skipped'):
                with self.subTest(state=state, verbosity=verbosity):
                    self.assertFalse(self.callback._run_is_verbose(self.result(state)))

    def test_changed_failed_and_unreachable_stay_verbose(self):
        for state in ('changed', 'failed', 'unreachable'):
            with self.subTest(state=state):
                self.assertTrue(self.callback._run_is_verbose(self.result(state)))

    def test_verbosity_threshold_still_delegates_to_parent(self):
        self.assertFalse(self.callback._run_is_verbose(self.result('changed'), verbosity=1))
        self.assertTrue(self.callback._run_is_verbose(self.result('changed'), verbosity=0))


if __name__ == '__main__':
    unittest.main()
