"""Exercise shipped shell startup with agent markers, without accounts or network."""
import base64
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FISH = shutil.which("fish")
POWERSHELL = shutil.which("pwsh") or shutil.which("pwsh.exe")
MARKERS = ("CLAUDECODE", "CURSOR_TRACE_ID", "CODEX_THREAD_ID", "CODEX_CI")


@unittest.skipUnless(FISH, "fish is not installed")
class FishStartup(unittest.TestCase):
    def run_fish(self, marker, interactive):
        with tempfile.TemporaryDirectory() as directory:
            env = {k: v for k, v in os.environ.items() if k not in MARKERS}
            env.update(HOME=directory, XDG_CONFIG_HOME=directory, TERM="xterm-256color", SHLVL="0")
            if marker:
                env[marker] = "1"
            else:
                # Human startup should initialize the existing theme without downloading it.
                Path(directory, "tokyofine.omp.toml").touch()
            script = r"""
function tput
    switch $argv[1]
        case colors
            echo 256
        case lines
            echo 40
    end
end
function fastfetch
    echo BANNER
end
function curl
    echo DOWNLOAD
end
function oh-my-posh
    echo 'echo THEME'
end
function zoxide
    echo 'echo ZOXIDE'
end
function eza
    printf '%s\n' $argv
end
set -e TERM_PROGRAM
set -e TERMINAL_EMULATOR
"""
            for path in ("conf.d/git-helpers.fish", "config.fish"):
                script += "\nsource " + shlex.quote(str(ROOT / "user_home/.config/fish" / path))
            script += r"""
if functions -q fish_greeting
    fish_greeting
end
for name in rm cp mv cat df top pacman sctl gfuck gpshf
    if functions -q $name
        echo WRAPPER_$name
    end
end
printf 'PAGER=%s\nGIT_PAGER=%s\nSYSTEMD_PAGER=%s\nMANPAGER=%s\nGIT_TERMINAL_PROMPT=%s\n' "$PAGER" "$GIT_PAGER" "$SYSTEMD_PAGER" "$MANPAGER" "$GIT_TERMINAL_PROMPT"
if functions -q ls
    ls
end
"""
            args = [FISH, "--no-config"]
            if interactive:
                args.append("--interactive")
            return subprocess.run([*args, "-c", script], env=env, capture_output=True,
                                  text=True, check=True, timeout=5).stdout

    def test_agents_skip_startup_prompts_and_pagers(self):
        for marker in MARKERS:
            for interactive in (False, True):
                with self.subTest(marker=marker, interactive=interactive):
                    output = self.run_fish(marker, interactive)
                    for forbidden in ("BANNER", "DOWNLOAD", "THEME", "ZOXIDE", "WRAPPER_"):
                        self.assertNotIn(forbidden, output)
                    for expected in ("PAGER=cat", "GIT_PAGER=cat", "SYSTEMD_PAGER=cat",
                                     "MANPAGER=col -bx", "GIT_TERMINAL_PROMPT=0",
                                     "--icons=never", "--color=never"):
                        self.assertIn(expected, output)

    def test_human_interactive_shell_keeps_theme_and_confirmations(self):
        output = self.run_fish(None, True)
        for expected in ("BANNER", "THEME", "ZOXIDE", "WRAPPER_rm", "WRAPPER_gfuck",
                         "WRAPPER_gpshf", "PAGER=less -R", "--icons=auto"):
            self.assertIn(expected, output)

    def test_ordinary_script_does_not_load_interactive_wrappers(self):
        output = self.run_fish(None, False)
        for forbidden in ("BANNER", "THEME", "ZOXIDE", "WRAPPER_"):
            self.assertNotIn(forbidden, output)


@unittest.skipUnless(POWERSHELL, "PowerShell is not installed")
class PowerShellStartup(unittest.TestCase):
    def test_agent_environment_and_quiet_command_startup(self):
        profile = (ROOT.parents[1] / "windows/home/Documents/PowerShell/Microsoft.PowerShell_profile.ps1").read_text()
        for marker in (*MARKERS, None):
            with self.subTest(marker=marker):
                script = "$ErrorActionPreference = 'Stop'\n"
                for name in MARKERS:
                    script += f"Remove-Item Env:{name} -ErrorAction Ignore\n"
                if marker:
                    script += f"$env:{marker} = '1'\n"
                for name in ("PAGER", "GIT_PAGER", "SYSTEMD_PAGER", "GIT_TERMINAL_PROMPT"):
                    script += f"$env:{name} = 'original'\n"
                script += "function fastfetch { throw 'Unexpected banner' }\n"
                script += "function oh-my-posh { throw 'Unexpected theme initialization' }\n"
                script += profile
                expected = "cat" if marker else "original"
                prompt = "0" if marker else "original"
                script += f"""
if ($env:PAGER -ne '{expected}' -or $env:GIT_PAGER -ne '{expected}' -or
    $env:SYSTEMD_PAGER -ne '{expected}' -or $env:GIT_TERMINAL_PROMPT -ne '{prompt}') {{
    throw 'Incorrect agent environment'
}}
Write-Output 'PASS'
"""
                encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
                result = subprocess.run(
                    [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "PASS")


if __name__ == "__main__":
    unittest.main()
