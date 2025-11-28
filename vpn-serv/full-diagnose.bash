#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Universal System Diagnostic for VPN / Network Servers
# Works on: Bare metal, KVM, VMware, Hyper-V, WSL2, LXC
# Run as root: sudo bash diagnose.sh 2>&1 | tee /tmp/diag.txt
# ═══════════════════════════════════════════════════════════

set -uo pipefail

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

section() { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}"; }
ok() { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
bad() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${BOLD}→${NC} $1"; }
dim() { echo -e "  ${DIM}  $1${NC}"; }

# ── Safe command execution with timeout ──
# Prevents hangs on commands that block in certain virtualization environments
run_safe() {
    local timeout_sec="${1:-3}"
    shift
    timeout "$timeout_sec" "$@" 2>/dev/null
    return $?
}

# ── Safe sysctl read ──
sysctl_val() {
    sysctl -n "$1" 2>/dev/null || echo "N/A"
}

# ── Check if command exists ──
has_cmd() {
    command -v "$1" &>/dev/null
}

# ── Detect environment once ──
detect_environment() {
    VIRT="none"
    if has_cmd systemd-detect-virt; then
        VIRT=$(systemd-detect-virt 2>/dev/null || echo "none")
    fi

    IS_WSL=false
    IS_KVM=false
    IS_VMWARE=false
    IS_HYPERV=false
    IS_LXC=false
    IS_DOCKER=false
    IS_BAREMETAL=false

    case "$VIRT" in
    wsl) IS_WSL=true ;;
    kvm) IS_KVM=true ;;
    vmware) IS_VMWARE=true ;;
    microsoft) IS_HYPERV=true ;;
    lxc*) IS_LXC=true ;;
    docker) IS_DOCKER=true ;;
    none) IS_BAREMETAL=true ;;
    esac

    # WSL detection fallback
    if grep -qi microsoft /proc/version 2>/dev/null; then
        IS_WSL=true
        VIRT="wsl"
    fi
}

detect_environment

# ── Get default network interface ──
get_default_iface() {
    ip route show default 2>/dev/null | awk '/default/ {print $5}' | head -1
}

IFACE=$(get_default_iface)

# ─────────────────────────────────────────────────────────
section "VIRTUALIZATION ENVIRONMENT"
# ─────────────────────────────────────────────────────────

info "Virtualization: $VIRT"

if $IS_WSL; then
    info "Platform: WSL2 (Windows Subsystem for Linux)"
    info "Note: Many hardware tunings are not applicable in WSL2"
elif $IS_KVM; then
    info "Platform: KVM Virtual Machine"
elif $IS_VMWARE; then
    info "Platform: VMware Virtual Machine"
elif $IS_HYPERV; then
    info "Platform: Hyper-V Virtual Machine"
elif $IS_LXC; then
    info "Platform: LXC/LXD Container"
    info "Note: Kernel is shared with host — sysctl changes may be restricted"
elif $IS_BAREMETAL; then
    info "Platform: Bare Metal (or undetected virtualization)"
fi

# CPU info
if [ -f /proc/cpuinfo ]; then
    CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2 | xargs)
    info "CPU Model: ${CPU_MODEL:-unknown}"
fi

VCPUS=$(nproc 2>/dev/null || echo 1)
info "vCPUs: $VCPUS"

# CPU flags
CPU_FLAGS=$(grep -m1 "flags" /proc/cpuinfo 2>/dev/null | cut -d: -f2 || echo "")
for flag in aes avx avx2 avx512f; do
    if echo "$CPU_FLAGS" | grep -qw "$flag"; then
        ok "CPU flag '$flag' available"
    else
        warn "CPU flag '$flag' not available"
    fi
done

# Virtio devices (skip on WSL — lspci may hang or not exist)
if ! $IS_WSL && has_cmd lspci; then
    VIRTIO_DEVS=$(run_safe 5 lspci 2>/dev/null | grep -i virtio || true)
    if [ -n "$VIRTIO_DEVS" ]; then
        info "Virtio devices:"
        echo "$VIRTIO_DEVS" | while IFS= read -r line; do
            dim "$line"
        done
    fi
elif $IS_WSL; then
    info "Virtio detection skipped (WSL2 environment)"
fi

# ─────────────────────────────────────────────────────────
section "KERNEL"
# ─────────────────────────────────────────────────────────

KERNEL=$(uname -r)
info "Kernel: $KERNEL"
info "Architecture: $(uname -m)"

# Parse kernel version
KMAJOR=$(echo "$KERNEL" | cut -d. -f1)
KMINOR=$(echo "$KERNEL" | cut -d. -f2)

if [ "$KMAJOR" -ge 6 ] && [ "$KMINOR" -ge 8 ]; then
    ok "Kernel $KERNEL — BBRv3 available in mainline"
elif [ "$KMAJOR" -ge 5 ]; then
    ok "Kernel $KERNEL — BBRv1/v2 available"
elif [ "$KMAJOR" -ge 4 ] && [ "$KMINOR" -ge 9 ]; then
    ok "Kernel $KERNEL — BBR available"
else
    bad "Kernel $KERNEL — may lack modern networking features"
fi

# Congestion control
AVAIL_CC=$(sysctl_val net.ipv4.tcp_available_congestion_control)
CURRENT_CC=$(sysctl_val net.ipv4.tcp_congestion_control)
info "Available congestion control: $AVAIL_CC"
info "Current congestion control: $CURRENT_CC"

if echo "$AVAIL_CC" | grep -qw bbr; then
    ok "BBR is available"
else
    bad "BBR is NOT available — try: modprobe tcp_bbr"
fi

# Qdisc
CURRENT_QDISC=$(sysctl_val net.core.default_qdisc)
info "Current qdisc: $CURRENT_QDISC"
if [ "$CURRENT_QDISC" = "fq" ]; then
    ok "Using 'fq' qdisc (optimal for BBR)"
else
    warn "Not using 'fq' qdisc — BBR works best with fq"
fi

# Kernel mitigations
CMDLINE=$(cat /proc/cmdline 2>/dev/null || echo "")
if echo "$CMDLINE" | grep -q "mitigations=off"; then
    ok "CPU mitigations are OFF (maximum performance)"
else
    warn "CPU mitigations are ON (performance penalty)"
    info "Kernel cmdline: $CMDLINE"

    if [ -d /sys/devices/system/cpu/vulnerabilities ]; then
        info "Vulnerability mitigations:"
        for vuln in /sys/devices/system/cpu/vulnerabilities/*; do
            [ -f "$vuln" ] || continue
            status=$(cat "$vuln" 2>/dev/null || echo "unknown")
            name=$(basename "$vuln")
            if echo "$status" | grep -qi "not affected"; then
                ok "  $name: $status"
            elif echo "$status" | grep -qi "mitigat"; then
                warn "  $name: $status"
            elif echo "$status" | grep -qi "vulnerable"; then
                bad "  $name: $status"
            else
                info "  $name: $status"
            fi
        done
    fi
fi

# Bootloader detection
if [ -f /etc/default/grub ]; then
    ok "GRUB config exists — can modify kernel cmdline"
    info "GRUB_CMDLINE_LINUX: $(grep '^GRUB_CMDLINE_LINUX=' /etc/default/grub 2>/dev/null | cut -d'"' -f2)"
elif $IS_WSL; then
    info "WSL2: kernel cmdline managed via .wslconfig or wsl.conf"
else
    warn "No GRUB config found — check bootloader"
    [ -d /etc/cloud ] && info "Cloud-init detected — cmdline may be managed by provider"
fi

# ─────────────────────────────────────────────────────────
section "MEMORY"
# ─────────────────────────────────────────────────────────

TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_MEM_MB=$((TOTAL_MEM_KB / 1024))
AVAIL_MEM_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
AVAIL_MEM_MB=$((AVAIL_MEM_KB / 1024))
USED_MEM_MB=$((TOTAL_MEM_MB - AVAIL_MEM_MB))
USED_PCT=0
[ "$TOTAL_MEM_MB" -gt 0 ] && USED_PCT=$((USED_MEM_MB * 100 / TOTAL_MEM_MB))

info "Total: ${TOTAL_MEM_MB}MB | Available: ${AVAIL_MEM_MB}MB | Used: ${USED_MEM_MB}MB (${USED_PCT}%)"

# Compact free output
free -h 2>/dev/null | while IFS= read -r line; do dim "$line"; done

# Swap
SWAP_TOTAL=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
if [ "$SWAP_TOTAL" -gt 0 ]; then
    SWAP_FREE=$(grep SwapFree /proc/meminfo | awk '{print $2}')
    SWAP_USED_MB=$(((SWAP_TOTAL - SWAP_FREE) / 1024))
    SWAP_TOTAL_MB=$((SWAP_TOTAL / 1024))
    if [ "$SWAP_USED_MB" -gt 0 ]; then
        warn "Swap: ${SWAP_TOTAL_MB}MB total, ${SWAP_USED_MB}MB in use"
    else
        ok "Swap: ${SWAP_TOTAL_MB}MB total, not in use"
    fi
else
    if [ "$TOTAL_MEM_MB" -le 4096 ]; then
        bad "No swap configured with only ${TOTAL_MEM_MB}MB RAM — OOM risk"
    else
        warn "No swap configured"
    fi
fi

# THP
THP_FILE="/sys/kernel/mm/transparent_hugepage/enabled"
if [ -f "$THP_FILE" ]; then
    THP_STATUS=$(cat "$THP_FILE")
    if echo "$THP_STATUS" | grep -q "\[never\]"; then
        ok "THP: disabled"
    elif echo "$THP_STATUS" | grep -q "\[madvise\]"; then
        ok "THP: madvise (acceptable)"
    elif echo "$THP_STATUS" | grep -q "\[always\]"; then
        warn "THP: always — can cause latency spikes on low-RAM systems"
    fi
else
    info "THP: not available"
fi

# zswap
if [ -f /sys/module/zswap/parameters/enabled ]; then
    ZSWAP_EN=$(cat /sys/module/zswap/parameters/enabled)
    if [ "$ZSWAP_EN" = "Y" ]; then
        ZCOMP=$(cat /sys/module/zswap/parameters/compressor 2>/dev/null || echo "?")
        ZPOOL_PCT=$(cat /sys/module/zswap/parameters/max_pool_percent 2>/dev/null || echo "?")
        ok "zswap: enabled (compressor: $ZCOMP, max pool: ${ZPOOL_PCT}%)"
    else
        warn "zswap: disabled — enable for effective memory expansion"
    fi
else
    info "zswap: not available in this kernel"
fi

# NUMA
NUMA_NODES=$(ls -d /sys/devices/system/node/node* 2>/dev/null | wc -l)
[ "$NUMA_NODES" -gt 1 ] && info "NUMA nodes: $NUMA_NODES" || info "NUMA: single node"

# ─────────────────────────────────────────────────────────
section "STORAGE"
# ─────────────────────────────────────────────────────────

# Block devices
if has_cmd lsblk; then
    info "Block devices:"
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,ROTA 2>/dev/null | while IFS= read -r line; do
        dim "$line"
    done
fi

# Root device detection
ROOT_SOURCE=$(findmnt -n -o SOURCE / 2>/dev/null || echo "")
if [ -n "$ROOT_SOURCE" ]; then
    # Extract base device name
    ROOT_DEV=$(echo "$ROOT_SOURCE" | sed 's|/dev/||' | sed 's/[0-9]*$//' | sed 's/p$//')

    # Identify driver type
    case "$ROOT_DEV" in
    vd*) ok "Disk driver: virtio-blk" ;;
    nvme*) ok "Disk driver: NVMe" ;;
    sd*)
        if $IS_WSL; then
            info "Disk driver: Hyper-V virtual SCSI (WSL2)"
        else
            info "Disk driver: SCSI/SATA (check if virtio-scsi)"
        fi
        ;;
    *) info "Disk driver: $ROOT_DEV" ;;
    esac

    # I/O scheduler
    SCHED_FILE="/sys/block/${ROOT_DEV}/queue/scheduler"
    if [ -f "$SCHED_FILE" ]; then
        SCHED=$(cat "$SCHED_FILE")
        info "I/O scheduler: $SCHED"
        if echo "$SCHED" | grep -q "\[none\]\|\[mq-deadline\]"; then
            ok "Good I/O scheduler for SSD/VPS"
        elif echo "$SCHED" | grep -q "\[bfq\]"; then
            warn "BFQ scheduler — consider 'none' or 'mq-deadline' for server workloads"
        fi
    fi

    # Rotational
    ROTA_FILE="/sys/block/${ROOT_DEV}/queue/rotational"
    if [ -f "$ROTA_FILE" ]; then
        ROTA=$(cat "$ROTA_FILE")
        if [ "$ROTA" = "0" ]; then
            ok "Disk: non-rotational (SSD/NVMe)"
        else
            if $IS_WSL || $IS_KVM; then
                info "Disk reports rotational=1 (likely incorrect in VM)"
            else
                warn "Disk reports rotational (HDD)"
            fi
        fi
    fi
fi

# Mount options
MOUNT_OPTS=$(findmnt -n -o OPTIONS / 2>/dev/null || echo "")
if [ -n "$MOUNT_OPTS" ]; then
    info "Root mount options: $MOUNT_OPTS"
    echo "$MOUNT_OPTS" | grep -q "noatime" && ok "noatime: set" || warn "noatime: NOT set — unnecessary write overhead"
    echo "$MOUNT_OPTS" | grep -q "discard" && ok "discard: enabled" || {
        if systemctl is-active fstrim.timer &>/dev/null; then
            ok "fstrim.timer: active (periodic TRIM)"
        else
            info "No TRIM configured"
        fi
    }
fi

# ─────────────────────────────────────────────────────────
section "NETWORK INTERFACES"
# ─────────────────────────────────────────────────────────

info "Default interface: ${IFACE:-none}"

if [ -n "$IFACE" ]; then
    # Driver detection with timeout (ethtool -i can hang on some virtual NICs)
    DRIVER=""
    if has_cmd ethtool && ! $IS_WSL; then
        DRIVER=$(run_safe 3 ethtool -i "$IFACE" 2>/dev/null | grep "^driver:" | awk '{print $2}')
    fi

    # Fallback: check sysfs
    if [ -z "$DRIVER" ] && [ -L "/sys/class/net/$IFACE/device/driver" ]; then
        DRIVER=$(basename "$(readlink -f /sys/class/net/$IFACE/device/driver 2>/dev/null)" 2>/dev/null)
    fi

    if [ -n "$DRIVER" ]; then
        info "Driver: $DRIVER"
        case "$DRIVER" in
        virtio_net | virtio-net) ok "Using virtio-net (optimal for KVM)" ;;
        hv_netvsc) ok "Using Hyper-V netvsc (optimal for Hyper-V/WSL2)" ;;
        vmxnet3) ok "Using vmxnet3 (optimal for VMware)" ;;
        e1000* | rtl* | r8169) warn "Using $DRIVER — consider virtio-net for better performance" ;;
        *) info "Driver: $DRIVER" ;;
        esac
    else
        info "Driver: could not determine"
    fi

    # Link speed (with timeout)
    if has_cmd ethtool && ! $IS_WSL; then
        SPEED=$(run_safe 3 ethtool "$IFACE" 2>/dev/null | grep "Speed:" | awk '{print $2}')
        [ -n "$SPEED" ] && info "Link speed: $SPEED"
    fi

    # Ring buffers (with timeout — this is where it commonly hangs)
    if has_cmd ethtool && ! $IS_WSL; then
        RING_INFO=$(run_safe 3 ethtool -g "$IFACE" 2>/dev/null)
        if [ -n "$RING_INFO" ]; then
            RX_MAX=$(echo "$RING_INFO" | awk '/Pre-set/,/Current/' | grep "^RX:" | head -1 | awk '{print $2}')
            RX_CUR=$(echo "$RING_INFO" | awk '/Current/,0' | grep "^RX:" | head -1 | awk '{print $2}')
            TX_MAX=$(echo "$RING_INFO" | awk '/Pre-set/,/Current/' | grep "^TX:" | head -1 | awk '{print $2}')
            TX_CUR=$(echo "$RING_INFO" | awk '/Current/,0' | grep "^TX:" | head -1 | awk '{print $2}')
            info "Ring buffers: RX=$RX_CUR/$RX_MAX TX=$TX_CUR/$TX_MAX"
            if [ -n "$RX_CUR" ] && [ -n "$RX_MAX" ] && [ "$RX_CUR" -lt "$RX_MAX" ] 2>/dev/null; then
                warn "RX ring buffer not at maximum ($RX_CUR < $RX_MAX)"
            fi
        else
            info "Ring buffers: not available (normal for some virtual NICs)"
        fi
    else
        info "Ring buffers: skipped ($($IS_WSL && echo "WSL2" || echo "ethtool not available"))"
    fi

    # Offload features (with timeout)
    if has_cmd ethtool && ! $IS_WSL; then
        OFFLOAD_INFO=$(run_safe 3 ethtool -k "$IFACE" 2>/dev/null)
        if [ -n "$OFFLOAD_INFO" ]; then
            info "Offload features:"
            for feat in rx-checksumming tx-checksumming tcp-segmentation-offload generic-segmentation-offload generic-receive-offload scatter-gather; do
                STATUS=$(echo "$OFFLOAD_INFO" | grep "^${feat}:" | awk '{print $2}')
                if [ "$STATUS" = "on" ]; then
                    ok "  $feat: on"
                elif [ "$STATUS" = "off" ]; then
                    warn "  $feat: off"
                elif [ -n "$STATUS" ]; then
                    info "  $feat: $STATUS"
                fi
            done
        fi
    elif $IS_WSL; then
        info "Offload features: managed by Hyper-V host (not tunable from WSL2)"
    fi

    # Interrupt coalescing (with timeout)
    if has_cmd ethtool && ! $IS_WSL; then
        COAL_INFO=$(run_safe 3 ethtool -c "$IFACE" 2>/dev/null)
        if [ -n "$COAL_INFO" ]; then
            RX_USECS=$(echo "$COAL_INFO" | grep "^rx-usecs:" | awk '{print $2}')
            [ -n "$RX_USECS" ] && info "Interrupt coalescing: rx-usecs=$RX_USECS"
        fi
    fi

    # Queue info from sysfs (safe, no ethtool)
    if [ -d "/sys/class/net/$IFACE/queues" ]; then
        RX_Q=$(ls -d /sys/class/net/"$IFACE"/queues/rx-* 2>/dev/null | wc -l)
        TX_Q=$(ls -d /sys/class/net/"$IFACE"/queues/tx-* 2>/dev/null | wc -l)
        info "Queues: RX=$RX_Q TX=$TX_Q"
    fi

    # MTU and txqueuelen from ip (always safe)
    LINK_INFO=$(ip link show "$IFACE" 2>/dev/null)
    MTU=$(echo "$LINK_INFO" | grep -o "mtu [0-9]*" | awk '{print $2}')
    TXQLEN=$(echo "$LINK_INFO" | grep -o "qlen [0-9]*" | awk '{print $2}')
    [ -n "$MTU" ] && info "MTU: $MTU"
    if [ -n "$TXQLEN" ]; then
        info "TX queue length: $TXQLEN"
        [ "$TXQLEN" -lt 1000 ] 2>/dev/null && warn "TX queue length is low ($TXQLEN)"
    fi
fi

# VPN interfaces
for vpn_iface in wg0 awg0 tun0 tun1; do
    if ip link show "$vpn_iface" &>/dev/null; then
        VPN_MTU=$(ip link show "$vpn_iface" 2>/dev/null | grep -o "mtu [0-9]*" | awk '{print $2}')
        VPN_TXQLEN=$(ip link show "$vpn_iface" 2>/dev/null | grep -o "qlen [0-9]*" | awk '{print $2}')
        VPN_STATE=$(ip link show "$vpn_iface" 2>/dev/null | grep -o "state [A-Z]*" | awk '{print $2}')
        ok "VPN interface $vpn_iface: state=${VPN_STATE:-unknown} mtu=${VPN_MTU:-?} txqlen=${VPN_TXQLEN:-not set}"
        [ -n "$VPN_TXQLEN" ] && [ "$VPN_TXQLEN" -lt 1000 ] 2>/dev/null &&
            warn "  $vpn_iface txqueuelen is low ($VPN_TXQLEN) — consider 1000"
    fi
done

# ─────────────────────────────────────────────────────────
section "NETWORK STACK STATUS"
# ─────────────────────────────────────────────────────────

# Conntrack
CT_COUNT_FILE="/proc/sys/net/netfilter/nf_conntrack_count"
if [ -f "$CT_COUNT_FILE" ]; then
    CT_COUNT=$(cat "$CT_COUNT_FILE")
    CT_MAX=$(sysctl_val net.netfilter.nf_conntrack_max)
    if [ "$CT_MAX" != "N/A" ] && [ "$CT_MAX" -gt 0 ] 2>/dev/null; then
        CT_PCT=$((CT_COUNT * 100 / CT_MAX))
        info "Conntrack: $CT_COUNT / $CT_MAX ($CT_PCT%)"
        if [ "$CT_PCT" -gt 80 ]; then
            bad "Conntrack >80% full!"
        elif [ "$CT_PCT" -gt 50 ]; then
            warn "Conntrack >50% full"
        else
            ok "Conntrack utilization healthy"
        fi
    fi
else
    info "Conntrack: not loaded"
fi

# Socket stats
if [ -f /proc/net/sockstat ]; then
    info "Socket statistics:"
    while IFS= read -r line; do dim "$line"; done </proc/net/sockstat
fi

# TCP memory
TCP_MEM=$(sysctl_val net.ipv4.tcp_mem)
info "TCP memory limits (pages): $TCP_MEM"

# Network drops per interface
info "Interface drops/errors:"
for iface_dir in /sys/class/net/*/statistics; do
    [ -d "$iface_dir" ] || continue
    iface_name=$(echo "$iface_dir" | rev | cut -d/ -f2 | rev)
    [ "$iface_name" = "lo" ] && continue

    RX_DROP=$(cat "$iface_dir/rx_dropped" 2>/dev/null || echo 0)
    TX_DROP=$(cat "$iface_dir/tx_dropped" 2>/dev/null || echo 0)
    RX_ERR=$(cat "$iface_dir/rx_errors" 2>/dev/null || echo 0)
    TX_ERR=$(cat "$iface_dir/tx_errors" 2>/dev/null || echo 0)

    if [ "$RX_DROP" -gt 0 ] || [ "$TX_DROP" -gt 0 ] || [ "$RX_ERR" -gt 0 ] || [ "$TX_ERR" -gt 0 ]; then
        warn "  $iface_name: rx_drop=$RX_DROP tx_drop=$TX_DROP rx_err=$RX_ERR tx_err=$TX_ERR"
    else
        ok "  $iface_name: clean"
    fi
done

# Softnet stats
if [ -f /proc/net/softnet_stat ]; then
    info "Softnet (per-CPU packet processing):"
    CPU_IDX=0
    while read -r line; do
        # Fields are hex: processed dropped squeezed ...
        PROCESSED_HEX=$(echo "$line" | awk '{print $1}')
        DROPPED_HEX=$(echo "$line" | awk '{print $2}')
        SQUEEZED_HEX=$(echo "$line" | awk '{print $3}')

        PROCESSED=$((16#$PROCESSED_HEX)) 2>/dev/null || PROCESSED=0
        DROPPED=$((16#$DROPPED_HEX)) 2>/dev/null || DROPPED=0
        SQUEEZED=$((16#$SQUEEZED_HEX)) 2>/dev/null || SQUEEZED=0

        if [ "$DROPPED" -gt 0 ]; then
            bad "  CPU$CPU_IDX: processed=$PROCESSED dropped=$DROPPED squeezed=$SQUEEZED"
        elif [ "$SQUEEZED" -gt 0 ]; then
            warn "  CPU$CPU_IDX: processed=$PROCESSED dropped=$DROPPED squeezed=$SQUEEZED"
        else
            ok "  CPU$CPU_IDX: processed=$PROCESSED dropped=$DROPPED squeezed=$SQUEEZED"
        fi
        CPU_IDX=$((CPU_IDX + 1))
    done </proc/net/softnet_stat
fi

# TCP retransmissions
info "TCP retransmissions:"
if has_cmd nstat; then
    RETRANS=$(run_safe 3 nstat -az TcpRetransSegs 2>/dev/null | awk 'NR==2 {print $2}')
    FAST_RETRANS=$(run_safe 3 nstat -az TcpExtTCPFastRetrans 2>/dev/null | awk 'NR==2 {print $2}')
    info "  Retransmit segments: ${RETRANS:-0}"
    info "  Fast retransmits: ${FAST_RETRANS:-0}"
elif has_cmd netstat; then
    run_safe 3 netstat -s 2>/dev/null | grep -i "retransmit" | while IFS= read -r line; do
        dim "$line"
    done
fi

# ─────────────────────────────────────────────────────────
section "FILE DESCRIPTORS"
# ─────────────────────────────────────────────────────────

if [ -f /proc/sys/fs/file-nr ]; then
    FD_INFO=$(cat /proc/sys/fs/file-nr)
    FD_USED=$(echo "$FD_INFO" | awk '{print $1}')
    FD_MAX=$(echo "$FD_INFO" | awk '{print $3}')
    FD_PCT=0
    [ "$FD_MAX" -gt 0 ] 2>/dev/null && FD_PCT=$((FD_USED * 100 / FD_MAX))
    info "File descriptors: $FD_USED / $FD_MAX ($FD_PCT%)"
fi

# Check VPN process limits
for proc_name in xray wg amneziawg sing-box v2ray; do
    PIDS=$(pgrep -f "$proc_name" 2>/dev/null || true)
    for pid in $PIDS; do
        [ -f "/proc/$pid/limits" ] || continue
        NOFILE=$(grep "Max open files" "/proc/$pid/limits" 2>/dev/null | awk '{print $4}')
        CMDLINE=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | cut -c1-60)
        if [ -n "$NOFILE" ]; then
            if [ "$NOFILE" -lt 65536 ] 2>/dev/null; then
                warn "PID $pid ($proc_name) NOFILE: $NOFILE — too low!"
            else
                ok "PID $pid ($proc_name) NOFILE: $NOFILE"
            fi
        fi
    done
done

# ─────────────────────────────────────────────────────────
section "RUNNING SERVICES"
# ─────────────────────────────────────────────────────────

# Top processes by memory
info "Top processes by memory:"
ps aux --sort=-%mem 2>/dev/null | head -12 | while IFS= read -r line; do
    dim "$line"
done

# Unnecessary services check
echo ""
info "Checking for unnecessary services:"
WASTEFUL=(
    "snapd:Snap package manager"
    "ModemManager:Modem management"
    "avahi-daemon:mDNS/DNS-SD"
    "cups:Printing"
    "bluetooth:Bluetooth"
    "whoopsie:Crash reporting"
    "kerneloops:Kernel crash reporting"
    "apport:Crash reporting"
    "udisks2:Disk management"
    "accounts-daemon:User accounts"
    "multipathd:SAN multipath"
    "fwupd:Firmware updates"
    "power-profiles-daemon:Power profiles"
    "thermald:Thermal management"
    "upower:Power management"
    "packagekit:Package management daemon"
    "bolt:Thunderbolt security"
    "colord:Color management"
    "switcheroo-control:GPU switching"
)

WASTEFUL_FOUND=0
for entry in "${WASTEFUL[@]}"; do
    svc="${entry%%:*}"
    desc="${entry#*:}"
    if systemctl is-enabled "$svc" 2>/dev/null | grep -q "enabled" ||
        systemctl is-active "$svc" 2>/dev/null | grep -q "^active"; then
        warn "  $svc ($desc) — not needed for VPN server"
        WASTEFUL_FOUND=$((WASTEFUL_FOUND + 1))
    fi
done
[ "$WASTEFUL_FOUND" -eq 0 ] && ok "No obvious unnecessary services found"

# Total running services
TOTAL_SVC=$(systemctl list-units --type=service --state=running --no-legend 2>/dev/null | wc -l)
info "Total running services: $TOTAL_SVC"

# List all
info "All running services:"
systemctl list-units --type=service --state=running --no-legend 2>/dev/null | awk '{print $1}' | while read -r svc; do
    dim "$svc"
done

# ─────────────────────────────────────────────────────────
section "TIMERS"
# ─────────────────────────────────────────────────────────

info "Active timers:"
systemctl list-timers --no-legend 2>/dev/null | while IFS= read -r line; do
    dim "$line"
done

# ─────────────────────────────────────────────────────────
section "CPU & CLOCK"
# ─────────────────────────────────────────────────────────

# CPU governor
if [ -d /sys/devices/system/cpu/cpu0/cpufreq ]; then
    GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "N/A")
    AVAIL_GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors 2>/dev/null || echo "N/A")
    CUR_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || echo 0)
    MAX_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null || echo 0)
    info "Governor: $GOV (available: $AVAIL_GOV)"
    info "Frequency: $((CUR_FREQ / 1000))MHz / $((MAX_FREQ / 1000))MHz"
    if [ "$GOV" != "performance" ] && echo "$AVAIL_GOV" | grep -q "performance"; then
        warn "Governor is '$GOV' — 'performance' recommended"
    fi
else
    info "CPU frequency scaling: not available (managed by hypervisor)"
    ok "Normal for KVM/Hyper-V guests"
fi

# Clocksource
CS_CURRENT=$(cat /sys/devices/system/clocksource/clocksource0/current_clocksource 2>/dev/null || echo "unknown")
CS_AVAIL=$(cat /sys/devices/system/clocksource/clocksource0/available_clocksource 2>/dev/null || echo "unknown")
info "Clocksource: $CS_CURRENT (available: $CS_AVAIL)"

case "$CS_CURRENT" in
kvm-clock) ok "kvm-clock: optimal for KVM" ;;
tsc) ok "TSC: fast, good for most systems" ;;
hyperv_clocksource*) ok "Hyper-V clock: optimal for Hyper-V/WSL2" ;;
acpi_pm) warn "acpi_pm: slow clocksource — consider switching to TSC" ;;
esac

# constant_tsc
grep -q "constant_tsc" /proc/cpuinfo 2>/dev/null && ok "constant_tsc: available" || info "constant_tsc: not available"

# ─────────────────────────────────────────────────────────
section "KERNEL MODULES"
# ─────────────────────────────────────────────────────────

info "Key modules:"
MODULES=(
    "wireguard:WireGuard VPN"
    "tcp_bbr:BBR congestion control"
    "nf_conntrack:Connection tracking"
    "nft_chain_nat:nftables NAT"
    "tun:TUN/TAP device"
    "vhost_net:Virtio host networking"
)

for entry in "${MODULES[@]}"; do
    mod="${entry%%:*}"
    desc="${entry#*:}"
    if lsmod 2>/dev/null | grep -qw "$mod"; then
        ok "  $mod ($desc): loaded"
    else
        info "  $mod ($desc): not loaded"
    fi
done

# BPF JIT
BPF_JIT=$(sysctl_val net.core.bpf_jit_enable)
if [ "$BPF_JIT" = "1" ]; then
    ok "BPF JIT: enabled"
else
    warn "BPF JIT: disabled — enable for better packet processing performance"
fi

# ─────────────────────────────────────────────────────────
section "KEY SYSCTL VALUES"
# ─────────────────────────────────────────────────────────

# Group related parameters
info "─ Forwarding ─"
for p in net.ipv4.ip_forward net.ipv6.conf.all.forwarding; do
    val=$(sysctl_val "$p")
    [ "$val" = "1" ] && ok "  $p = $val" || warn "  $p = $val"
done

info "─ Buffers ─"
for p in net.core.rmem_default net.core.wmem_default net.core.rmem_max net.core.wmem_max; do
    info "  $p = $(sysctl_val "$p")"
done
info "  net.ipv4.tcp_rmem = $(sysctl_val net.ipv4.tcp_rmem)"
info "  net.ipv4.tcp_wmem = $(sysctl_val net.ipv4.tcp_wmem)"

info "─ Congestion & Queueing ─"
info "  tcp_congestion_control = $(sysctl_val net.ipv4.tcp_congestion_control)"
info "  default_qdisc = $(sysctl_val net.core.default_qdisc)"
info "  netdev_max_backlog = $(sysctl_val net.core.netdev_max_backlog)"
info "  netdev_budget = $(sysctl_val net.core.netdev_budget)"
info "  somaxconn = $(sysctl_val net.core.somaxconn)"

info "─ TCP Optimization ─"
for p in tcp_fastopen tcp_tw_reuse tcp_slow_start_after_idle tcp_mtu_probing tcp_no_metrics_save tcp_fin_timeout tcp_max_tw_buckets; do
    info "  $p = $(sysctl_val "net.ipv4.$p")"
done

info "─ TCP Keepalive ─"
for p in tcp_keepalive_time tcp_keepalive_intvl tcp_keepalive_probes; do
    info "  $p = $(sysctl_val "net.ipv4.$p")"
done

info "─ Conntrack ─"
for p in nf_conntrack_max nf_conntrack_buckets nf_conntrack_tcp_timeout_established nf_conntrack_udp_timeout; do
    val=$(sysctl_val "net.netfilter.$p")
    [ "$val" != "N/A" ] && info "  $p = $val"
done

info "─ Port Range ─"
info "  ip_local_port_range = $(sysctl_val net.ipv4.ip_local_port_range)"

info "─ VM ─"
for p in vm.swappiness vm.vfs_cache_pressure vm.dirty_ratio vm.dirty_background_ratio; do
    info "  $p = $(sysctl_val "$p")"
done

info "─ File Limits ─"
info "  fs.file-max = $(sysctl_val fs.file-max)"
info "  fs.nr_open = $(sysctl_val fs.nr_open)"

# ─────────────────────────────────────────────────────────
section "VPN PROCESSES"
# ─────────────────────────────────────────────────────────

# Xray
XRAY_PIDS=$(pgrep -f "xray" 2>/dev/null || true)
if [ -n "$XRAY_PIDS" ]; then
    for pid in $XRAY_PIDS; do
        [ -d "/proc/$pid" ] || continue
        RSS=$(ps -o rss= -p "$pid" 2>/dev/null | xargs)
        FDS=$(ls /proc/"$pid"/fd 2>/dev/null | wc -l)
        ok "Xray (PID $pid): RSS=${RSS:+$((RSS / 1024))MB} FDs=$FDS"
    done

    # Check for REALITY
    for cfg in /usr/local/etc/xray/config.json /etc/xray/config.json /opt/*/xray/*.json; do
        [ -f "$cfg" ] || continue
        if grep -q "reality" "$cfg" 2>/dev/null; then
            ok "REALITY protocol detected in $cfg"
        elif grep -q '"tls"' "$cfg" 2>/dev/null; then
            warn "Using TLS (not REALITY) in $cfg — REALITY has less overhead"
        fi
        if grep -q '"vision"\|xtls' "$cfg" 2>/dev/null; then
            ok "XTLS-Vision flow detected (zero-copy)"
        fi
        break
    done
else
    info "Xray: not running"
fi

# WireGuard / AmneziaWG
for wg_name in wg amneziawg; do
    WG_PIDS=$(pgrep -f "${wg_name}" 2>/dev/null || true)
    for pid in $WG_PIDS; do
        [ -d "/proc/$pid" ] || continue
        CMDLINE=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | cut -c1-80)
        RSS=$(ps -o rss= -p "$pid" 2>/dev/null | xargs)
        ok "$wg_name (PID $pid): RSS=${RSS:+$((RSS / 1024))MB} — $CMDLINE"

        # Check if userspace
        if echo "$CMDLINE" | grep -qi "\-go\|userspace"; then
            warn "  Running in USERSPACE mode (Go implementation) — kernel module is faster"
        fi
    done
done

# WireGuard kernel interface check
if has_cmd wg; then
    WG_IFACES=$(wg show interfaces 2>/dev/null || true)
    if [ -n "$WG_IFACES" ]; then
        ok "WireGuard interfaces: $WG_IFACES"
        wg show 2>/dev/null | head -20 | while IFS= read -r line; do dim "$line"; done
    fi
fi

# ─────────────────────────────────────────────────────────
section "FIREWALL"
# ─────────────────────────────────────────────────────────

if has_cmd nft && nft list ruleset &>/dev/null; then
    RULE_COUNT=$(nft list ruleset 2>/dev/null | grep -c "rule" || echo 0)
    ok "nftables active ($RULE_COUNT rules)"

    # Check for NOTRACK rules
    if nft list ruleset 2>/dev/null | grep -qi "notrack"; then
        ok "NOTRACK rules found (conntrack bypass)"
    else
        info "No NOTRACK rules — consider adding for WireGuard UDP port"
    fi
elif has_cmd iptables; then
    IPT_VER=$(iptables --version 2>/dev/null || echo "unknown")
    info "iptables: $IPT_VER"
    if echo "$IPT_VER" | grep -q "nf_tables"; then
        ok "Using iptables-nft backend"
    else
        warn "Using legacy iptables — nftables is faster"
    fi
fi

# Listening ports
info "Listening ports:"
if has_cmd ss; then
    info "  TCP:"
    ss -tlnp 2>/dev/null | tail -n +2 | while IFS= read -r line; do dim "  $line"; done
    info "  UDP:"
    ss -ulnp 2>/dev/null | tail -n +2 | while IFS= read -r line; do dim "  $line"; done
fi

# ─────────────────────────────────────────────────────────
section "ENTROPY"
# ─────────────────────────────────────────────────────────

ENTROPY=$(cat /proc/sys/kernel/random/entropy_avail 2>/dev/null || echo 0)
if [ "$ENTROPY" -ge 1000 ]; then
    ok "Entropy: $ENTROPY (healthy)"
elif [ "$ENTROPY" -ge 256 ]; then
    ok "Entropy: $ENTROPY (sufficient)"
else
    bad "Entropy: $ENTROPY (LOW — crypto operations may block)"
fi

[ -c /dev/hwrng ] && ok "Hardware RNG: available" || info "Hardware RNG: not available"

# ─────────────────────────────────────────────────────────
section "JOURNAL"
# ─────────────────────────────────────────────────────────

if has_cmd journalctl; then
    JOURNAL_SIZE=$(journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+\s*[KMGT]i?B?' || echo "unknown")
    info "Journal disk usage: $JOURNAL_SIZE"
fi

JOURNAL_STORAGE=$(grep -E "^Storage=" /etc/systemd/journald.conf 2>/dev/null | cut -d= -f2)
if [ "$JOURNAL_STORAGE" = "volatile" ]; then
    ok "Journal: volatile (RAM only)"
else
    info "Journal storage: ${JOURNAL_STORAGE:-auto (persistent)}"
fi

# ─────────────────────────────────────────────────────────
section "DOCKER (if present)"
# ─────────────────────────────────────────────────────────

if has_cmd docker && systemctl is-active docker &>/dev/null; then
    DOCKER_MEM=0
    for pid in $(pgrep -f "dockerd|containerd" 2>/dev/null); do
        RSS=$(ps -o rss= -p "$pid" 2>/dev/null | xargs)
        DOCKER_MEM=$((DOCKER_MEM + ${RSS:-0}))
    done

    info "Docker infrastructure memory: $((DOCKER_MEM / 1024))MB"

    CONTAINERS=$(docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}" 2>/dev/null)
    if [ -n "$CONTAINERS" ]; then
        info "Running containers:"
        echo "$CONTAINERS" | while IFS= read -r line; do dim "$line"; done
    else
        info "No running containers"
    fi
else
    info "Docker: not active"
fi

# ─────────────────────────────────────────────────────────
section "RECOMMENDATIONS"
# ─────────────────────────────────────────────────────────

echo ""
RECS=0

# Platform-specific note
if $IS_WSL; then
    info "WSL2 NOTE: Many hardware-level optimizations cannot be applied from within WSL2."
    info "Network performance is limited by Hyper-V virtual switch and NAT layer."
    info "For best VPN performance, run directly on Linux (bare metal or KVM)."
    echo ""
fi

# Memory
if [ "$SWAP_TOTAL" -eq 0 ] 2>/dev/null && [ "$TOTAL_MEM_MB" -le 4096 ] 2>/dev/null; then
    bad "[CRITICAL] Create swap file for OOM protection"
    RECS=$((RECS + 1))
fi

# THP
if [ -f "$THP_FILE" ] && ! cat "$THP_FILE" 2>/dev/null | grep -q "\[never\]"; then
    if [ "$TOTAL_MEM_MB" -le 4096 ] 2>/dev/null; then
        warn "[PERF] Disable THP: echo never > $THP_FILE"
        RECS=$((RECS + 1))
    fi
fi

# BBR
if ! echo "$AVAIL_CC" | grep -qw bbr; then
    bad "[PERF] Enable BBR: modprobe tcp_bbr"
    RECS=$((RECS + 1))
fi

# BPF JIT
if [ "$BPF_JIT" != "1" ]; then
    warn "[PERF] Enable BPF JIT: sysctl -w net.core.bpf_jit_enable=1"
    RECS=$((RECS + 1))
fi

# noatime
if [ -n "$MOUNT_OPTS" ] && ! echo "$MOUNT_OPTS" | grep -q "noatime"; then
    warn "[IO] Add noatime to root mount in /etc/fstab"
    RECS=$((RECS + 1))
fi

# Journal
if [ "$JOURNAL_STORAGE" != "volatile" ] && ! $IS_WSL; then
    info "[IO] Consider volatile journal: Storage=volatile in journald.conf"
    RECS=$((RECS + 1))
fi

# Mitigations
if ! echo "$CMDLINE" | grep -q "mitigations=off"; then
    if ! $IS_WSL; then
        warn "[PERF] Disable CPU mitigations: add 'mitigations=off' to kernel cmdline"
        RECS=$((RECS + 1))
    else
        info "[INFO] CPU mitigations are managed by Windows host in WSL2"
    fi
fi

# Wasteful services
if [ "$WASTEFUL_FOUND" -gt 0 ]; then
    warn "[MEM] Disable $WASTEFUL_FOUND unnecessary services (see above)"
    RECS=$((RECS + 1))
fi

# zswap
if [ -f /sys/module/zswap/parameters/enabled ]; then
    ZSWAP_EN=$(cat /sys/module/zswap/parameters/enabled)
    if [ "$ZSWAP_EN" != "Y" ] && [ "$TOTAL_MEM_MB" -le 4096 ] 2>/dev/null; then
        warn "[MEM] Enable zswap for effective memory expansion"
        RECS=$((RECS + 1))
    fi
fi

echo ""
if [ "$RECS" -eq 0 ]; then
    ok "No critical recommendations — system looks well-tuned!"
else
    info "$RECS recommendations found"
fi

# ─────────────────────────────────────────────────────────
section "DIAGNOSTIC COMPLETE"
# ─────────────────────────────────────────────────────────
echo -e "  Platform: ${BOLD}$VIRT${NC} | Kernel: ${BOLD}$KERNEL${NC} | RAM: ${BOLD}${TOTAL_MEM_MB}MB${NC} | vCPUs: ${BOLD}$VCPUS${NC}"
echo -e "  Save: ${DIM}sudo bash diagnose.sh 2>&1 | tee /tmp/diag-\$(date +%Y%m%d-%H%M).txt${NC}"
