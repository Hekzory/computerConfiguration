# Stdout callback: ansible.posix.debug, minus the noise. With -v the stock
# callback prints the full result dict for every task: for an unchanged
# service_facts or systemd that is pages that say nothing new. Here 'ok'
# results print one line, and for everything else fields whose JSON is bigger
# than TRIM_AT (the systemd 'status' blob, service_facts' unit list, find's
# file list) are replaced by a size note. stdout/stderr/msg/diff are never
# trimmed and -vvv shows everything, so nothing is lost for debugging.
import json

from ansible_collections.ansible.posix.plugins.callback.debug import CallbackModule as DebugCallback

DOCUMENTATION = """
    name: quiet_ok
    type: stdout
    short_description: debug callback that stays quiet on unchanged results
    description:
      - Same output as ansible.posix.debug, but unchanged (ok) results print a one-liner
        and oversized result fields are trimmed to a size note below -vvv.
    extends_documentation_fragment:
      - default_callback
      - result_format_callback
"""

TRIM_AT = 1500
KEEP_WHOLE = ("stdout", "stdout_lines", "stderr", "stderr_lines", "msg", "module_stdout", "module_stderr", "diff")


class CallbackModule(DebugCallback):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "quiet_ok"

    def _run_is_verbose(self, result, verbosity=0):
        if not (result.is_changed() or result.is_failed() or result.is_unreachable() or result.is_skipped()):
            return False
        return super()._run_is_verbose(result, verbosity)

    def _dump_results(self, result, indent=None, sort_keys=True, keep_invocation=False):
        if self._display.verbosity < 3:
            trimmed = {}
            for key, value in result.items():
                if key == "ansible_facts":
                    continue
                if key not in KEEP_WHOLE and not key.startswith("_"):
                    size = len(json.dumps(value, default=str))
                    if size > TRIM_AT:
                        value = "<%d chars trimmed, -vvv shows it>" % size
                trimmed[key] = value
            result = trimmed
        return super()._dump_results(result, indent, sort_keys, keep_invocation)
