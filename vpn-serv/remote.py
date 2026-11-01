"""Ubuntu host operations. Sent over SSH; requires only Python's standard library."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

# Only optional desktop/discovery/crash-reporting packages. Never autoremove.
DEBLOAT = frozenset({'avahi-daemon', 'avahi-utils', 'cups', 'cups-daemon',
                     'cups-browsed', 'modemmanager', 'whoopsie', 'apport', 'apport-gtk',
                     'apport-core-dump-handler'})
# These are permitted only as consequences of removing optional packages,
# never selected merely because they are installed.
DEBLOAT_METAPACKAGES = frozenset({'ubuntu-server', 'ubuntu-server-minimal'})
DEBLOAT_ALLOWED = DEBLOAT | DEBLOAT_METAPACKAGES
SYSCTL = {'net.ipv4.tcp_syncookies': '1', 'net.ipv4.tcp_mtu_probing': '1',
          'net.ipv4.tcp_congestion_control': 'bbr',
          'net.core.default_qdisc': 'fq_codel', 'fs.file-max': '2097152'}
JOURNAL = '[Journal]\nSystemMaxUse=128M\nRuntimeMaxUse=32M\nSystemKeepFree=256M\nMaxRetentionSec=14day\n'
# Optional functionality on a dedicated VPN VPS, including activation units.
# Keep security updates, networking and provider/virtualization agents intact.
SERVICES = {
    'avahi-daemon.socket': 'обнаружение устройств',
    'avahi-daemon.service': 'обнаружение устройств',
    'cups.socket': 'печать', 'cups.path': 'печать',
    'cups.service': 'печать', 'cups-browsed.service': 'поиск принтеров',
    'ModemManager.service': 'мобильные модемы',
    'bluetooth.service': 'Bluetooth',
    'apport-autoreport.path': 'отчёты о сбоях',
    'apport-autoreport.service': 'отчёты о сбоях',
    'apport.service': 'отчёты о сбоях', 'whoopsie.service': 'отправка отчётов',
    'packagekit.service': 'пакетный менеджер для desktop',
    'motd-news.timer': 'новости при входе', 'motd-news.service': 'новости при входе',
    'man-db.timer': 'индексация man-страниц', 'man-db.service': 'индексация man-страниц',
}


def emit(status, message, **extra):
    print(json.dumps(dict(status=status, message=message, **extra)), flush=True)


def command(argv, check=True):
    proc = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=180,
                          env={**os.environ, 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive'})
    if check and proc.returncode:
        raise RuntimeError(f'{argv[0]}: {proc.stderr.strip() or proc.stdout.strip()}')
    return proc


def ubuntu(path=Path('/etc/os-release')):
    values = {}
    for line in path.read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            values[key] = value.strip('"\'')
    if values.get('ID') != 'ubuntu':
        raise RuntimeError('Поддерживается только Ubuntu; изменений нет.')
    return values.get('PRETTY_NAME', 'Ubuntu')


def package_plan(installed):
    return sorted(DEBLOAT.intersection(installed))


def simulated_removals(output, approved, *, expand=False):
    removals = []
    for line in output.splitlines():
        if line.startswith(('Remv ', 'Purg ')):
            removals.append(line.split()[1])
        elif line.startswith(('Inst ', 'Conf ')):
            raise RuntimeError('APT предлагает установку/настройку других пакетов; остановка.')
    actual = set(removals)
    requested = set(approved)
    if expand:
        valid = (requested.issubset(actual) and actual.issubset(DEBLOAT_ALLOWED)
                 and bool(requested & DEBLOAT))
    else:
        valid = actual == requested
    if not valid:
        raise RuntimeError('APT изменил список удаления или затрагивает зависимости; остановка: '
                           + ', '.join(removals))
    return removals


class Settings:
    def __init__(self, apply):
        self.apply = apply
        self.backup = None

    def write(self, name, content, label=None):
        path = Path(name)
        label = label or str(path)
        if path.is_symlink():
            raise RuntimeError(f'Отказ заменять symlink: {path}')
        if path.exists() and path.read_text() == content:
            emit('OK', label)
            return False
        if not self.apply:
            emit('PLAN', label)
            emit('DETAIL', f'{path}:\n{content.rstrip()}')
            return True
        if self.backup is None:
            parent = Path('/var/backups/vpn-serv')
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.backup = Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=parent))
            emit('INFO', f'Резервная копия изменяемых файлов: {self.backup}')
        target = self.backup / str(path).lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            shutil.copy2(path, target)
        else:
            target.with_name(target.name + '.absent').touch()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
                if path.exists():
                    original = path.stat()
                    os.fchown(stream.fileno(), original.st_uid, original.st_gid)
                    os.fchmod(stream.fileno(), stat.S_IMODE(original.st_mode))
                else:
                    os.fchmod(stream.fileno(), 0o644)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        emit('CHANGED', label)
        return True


def inspect():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0])
    total = memory['MemTotal']
    available = memory['MemAvailable']
    disk = shutil.disk_usage('/')
    emit('INFO', f"RAM: {(total - available) / 1024:.0f}/{total / 1024:.0f} MiB · "
         f"Диск /: {disk.used / 2**30:.1f}/{disk.total / 2**30:.1f} GiB")
    if available / total < 0.1:
        emit('WARN', 'Доступно менее 10% RAM')
    if disk.free / disk.total < 0.1:
        emit('WARN', 'На / свободно менее 10% места')
    emit('DETAIL', 'Включённые службы:\n' + command([
        'systemctl', 'list-unit-files', '--state=enabled', '--type=service', '--no-pager', '--no-legend']).stdout.strip())
    if shutil.which('docker'):
        result = command(['docker', 'ps', '-a', '--format', '{{.Names}}\t{{.State}}\t{{.Status}}'], check=False)
        if result.returncode:
            emit('WARN', 'Docker недоступен: ' + result.stderr.strip())
        else:
            containers = [line.split('\t', 2) for line in result.stdout.splitlines()]
            amnezia = [row for row in containers if row[0].startswith('amnezia')]
            emit('INFO', f'Docker: {len(containers)} контейнеров · Amnezia: {len(amnezia)}')
            for row in amnezia:
                if len(row) >= 3 and (row[1] != 'running' or '(unhealthy)' in row[2]):
                    emit('WARN', f'{row[0]}: {row[2]}')
            emit('DETAIL', result.stdout.strip())
    else:
        emit('INFO', 'Docker пока не установлен')
    if Path('/var/run/reboot-required').exists():
        emit('WARN', 'Требуется перезагрузка Ubuntu')
    sync = command(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'], check=False)
    emit('OK' if sync.stdout.strip() == 'yes' else 'WARN', 'Синхронизация времени: ' + (sync.stdout.strip() or 'не определена'))


def report_failed_services(cleanup=False, apply=False):
    failed = command(['systemctl', 'list-units', '--failed', '--no-legend', '--plain', '--no-pager']).stdout.strip()
    remaining = []
    for line in failed.splitlines():
        unit = line.split()[0]
        if cleanup and unit in SERVICES:
            result = command(['systemctl', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState'])
            state = dict(row.split('=', 1) for row in result.stdout.splitlines() if '=' in row)
            if state.get('LoadState') in {'not-found', 'masked'} and state.get('ActiveState') == 'failed':
                description = 'удалённой' if state['LoadState'] == 'not-found' else 'заблокированной'
                message = f'{unit}: сбросить старую ошибку {description} службы'
                if apply:
                    command(['systemctl', 'reset-failed', unit])
                    result = command(['systemctl', 'list-units', '--failed', '--no-legend', '--plain', '--no-pager', unit])
                    if result.stdout.strip():
                        raise RuntimeError(f'{unit}: ошибка осталась после reset-failed')
                    emit('CHANGED', f'{unit}: старая ошибка {description} службы сброшена')
                else:
                    emit('PLAN', message)
                continue
        remaining.append(unit)
    if remaining:
        emit('WARN', 'Сбой служб: ' + ', '.join(remaining))
        emit('DETAIL', failed)


def disable_services(apply):
    units = command(['systemctl', 'list-unit-files', '--no-legend', '--no-pager']).stdout
    installed = {line.split()[0] for line in units.splitlines() if line.strip()}
    for unit, reason in SERVICES.items():
        if unit not in installed:
            continue
        def state():
            result = command(['systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'UnitFileState'])
            return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        current = state()
        if current.get('UnitFileState') == 'masked' and current.get('ActiveState') in {'inactive', 'failed'}:
            emit('OK', f'{unit}: заблокирован')
            continue
        message = f'{unit}: остановить и заблокировать ({reason})'
        if not apply:
            emit('PLAN', message)
            continue
        # No --force: never overwrite a local administrator's unit file.
        command(['systemctl', 'mask', '--now', unit])
        after = state()
        if after.get('UnitFileState') != 'masked' or after.get('ActiveState') not in {'inactive', 'failed'}:
            raise RuntimeError(f'{unit}: не удалось подтвердить остановку и блокировку')
        emit('CHANGED', f'{unit}: остановлен и заблокирован ({reason})')


def resolve_sysctl_conflicts(settings, supported, etc=Path('/etc')):
    managed = (etc / 'sysctl.d/90-vpn-serv.conf').resolve()
    seen = {managed}
    paths = sorted((etc / 'sysctl.d').glob('*.conf')) + [etc / 'sysctl.conf']
    for alias in paths:
        path = alias.resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        lines = path.read_text().splitlines(keepends=True)
        changed = []
        result = []
        for line in lines:
            match = re.match(r'\s*(-?[^#;=\s]+)\s*=\s*([^#;]+)', line)
            key = match[1].lstrip('-').replace('/', '.') if match else None
            if key in supported and match[2].strip() != supported[key]:
                changed.append(key)
                result.append('# vpn-serv: перенесено в 90-vpn-serv.conf: ' + line)
            else:
                result.append(line)
        if changed:
            if not path.is_relative_to(etc.resolve()):
                emit('WARN', f'{alias}: конфликт вне /etc, требуется ручная проверка ({path})')
                continue
            settings.write(str(path), ''.join(result),
                           f'{path}: убрать конфликт ' + ', '.join(sorted(set(changed))))


def configure(apply):
    settings = Settings(apply)
    # Load before setting sysctls, and before systemd-sysctl on future boots.
    for module in ('tcp_bbr', 'sch_fq_codel'):
        command(['modprobe', module] if apply else ['modprobe', '--dry-run', module])
    settings.write('/etc/modules-load.d/90-vpn-serv.conf', 'tcp_bbr\nsch_fq_codel\n',
                   'BBR и fq_codel: загрузка модулей при старте')
    if settings.write('/etc/systemd/journald.conf.d/90-vpn-serv.conf', JOURNAL, 'Журнал: лимит 128 MiB на диске, 32 MiB в RAM, хранение 14 дней') and apply:
        command(['systemctl', 'restart', 'systemd-journald'])
    supported = {}
    for key, desired in SYSCTL.items():
        current = command(['sysctl', '-n', key], check=False)
        if current.returncode:
            emit('WARN', f'{key}: недоступен, пропуск')
            continue
        supported[key] = desired
    content = '# Managed by vpn-serv/setup\n' + ''.join(f'{k} = {v}\n' for k, v in supported.items())
    settings.write('/etc/sysctl.d/90-vpn-serv.conf', content, 'Sysctl: сохранить профиль VPN')
    resolve_sysctl_conflicts(settings, supported)
    for key, desired in supported.items():
        current = command(['sysctl', '-n', key]).stdout.strip()
        if current == desired:
            emit('OK', f'{key} = {desired}')
        elif apply:
            command(['sysctl', '-w', f'{key}={desired}'])
            if command(['sysctl', '-n', key]).stdout.strip() != desired:
                raise RuntimeError(f'{key}: проверка после записи не прошла')
            emit('CHANGED', f'{key}: {current} → {desired}')
        else:
            emit('PLAN', f'{key}: {current} → {desired}')
    configure_qdisc(apply)


def configure_qdisc(apply):
    # default_qdisc only affects newly activated devices. Update existing uplinks
    # too, but preserve any custom hierarchy (CAKE/HTB/mq/etc.).
    devices = set()
    for family in ('-4', '-6'):
        routes = json.loads(command(['ip', '-j', family, 'route', 'show', 'default']).stdout)
        for route in routes:
            if route.get('dev'):
                devices.add(route['dev'])
            devices.update(hop['dev'] for hop in route.get('nexthops', []) if hop.get('dev'))
    for device in sorted(devices):
        def roots():
            return [q for q in json.loads(command(['tc', '-j', 'qdisc', 'show', 'dev', device]).stdout)
                    if q.get('root')]
        current = roots()
        if len(current) == 1 and current[0]['kind'] == 'fq_codel':
            emit('OK', f'{device}: fq_codel')
        elif len(current) != 1 or current[0]['kind'] not in {'fq', 'pfifo_fast'}:
            emit('WARN', f'{device}: нестандартная очередь, оставлена без изменений')
        elif apply:
            command(['tc', 'qdisc', 'replace', 'dev', device, 'root', 'fq_codel'])
            after = roots()
            if len(after) != 1 or after[0]['kind'] != 'fq_codel':
                raise RuntimeError(f'{device}: fq_codel не применился')
            emit('CHANGED', f'{device}: {current[0]["kind"]} → fq_codel')
        else:
            emit('PLAN', f'{device}: {current[0]["kind"]} → fq_codel')


def main(config):
    emit('INFO', ubuntu())  # Reject other distributions before any writes.
    if os.geteuid() != 0:
        raise RuntimeError('Нужен root или sudo без пароля (sudo -n).')
    if not Path('/run/systemd/system').is_dir():
        raise RuntimeError('Требуется Ubuntu с systemd на хосте VPS.')
    mode = config['mode']
    if mode not in {'apply', 'check', 'audit', 'purge'}:
        raise RuntimeError('Неизвестный режим')
    # /run already exists; lock directory descriptor without creating a file.
    lock = os.open('/run', os.O_RDONLY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if mode == 'purge':
            packages = config['packages']
            if (not set(packages).intersection(DEBLOAT)
                    or not set(packages).issubset(DEBLOAT_ALLOWED)):
                raise RuntimeError('Пакеты вне разрешённого списка')
            simulation = command(['apt-get', '-s', '--no-auto-remove', 'purge', '--', *packages]).stdout
            simulated_removals(simulation, packages)
            command(['apt-get', '-y', '--no-auto-remove', 'purge', '--', *packages])
            emit('CHANGED', 'Удалены: ' + ', '.join(packages))
            report_failed_services(cleanup=True, apply=True)
            return
        inspect()
        configure(mode == 'apply')
        if config.get('debloat') or mode == 'audit':
            disable_services(mode == 'apply')
            data = command(['dpkg-query', '-W', '-f=${binary:Package}\t${db:Status-Status}\n']).stdout
            installed = [line.split('\t')[0] for line in data.splitlines() if line.endswith('\tinstalled')]
            packages = package_plan(installed)
            if packages:
                simulation = command(['apt-get', '-s', '--no-auto-remove', 'purge', '--', *packages]).stdout
                emit('DETAIL', 'APT preview:\n' + simulation.strip())
                packages = simulated_removals(simulation, packages, expand=True)
                emit('PLAN', 'Удалить пакеты: ' + ', '.join(packages))
                if DEBLOAT_METAPACKAGES.intersection(packages):
                    emit('WARN', 'APT также удалит метапакеты Ubuntu Server. Их зависимости '
                         'не удаляются автоматически сейчас, но стандартный набор зависимостей '
                         'больше не поддерживается этими метапакетами. Проверяйте будущий '
                         'apt autoremove перед выполнением.')
            else:
                emit('OK', 'Пакетов из списка debloat нет')
            emit('PACKAGES', '', packages=packages)
        report_failed_services(cleanup=config.get('debloat') or mode == 'audit', apply=mode == 'apply')
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        main(json.loads(sys.argv[1]))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        emit('ERROR', str(exc))
        sys.exit(1)
