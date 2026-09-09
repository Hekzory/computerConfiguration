# Stdout callback: ansible.posix.debug, minus the result dump for unchanged
# tasks. With -v the stock callback prints the full result dict for every
# 'ok' too, which for service_facts or systemd is pages of noise that says
# nothing new. Changed, failed, unreachable and skipped keep the verbose dump.
from ansible_collections.ansible.posix.plugins.callback.debug import CallbackModule as DebugCallback

DOCUMENTATION = """
    name: quiet_ok
    type: stdout
    short_description: debug callback that stays quiet on unchanged results
    description:
      - Same output as ansible.posix.debug, but unchanged (ok) results print a one-liner instead of the full result dict under -v.
    extends_documentation_fragment:
      - default_callback
      - result_format_callback
"""


class CallbackModule(DebugCallback):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "quiet_ok"

    def _run_is_verbose(self, result, verbosity=0):
        if not (result.is_changed() or result.is_failed() or result.is_unreachable() or result.is_skipped()):
            return False
        return super()._run_is_verbose(result, verbosity)
