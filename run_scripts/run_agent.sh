set -o pipefail   # keep gem5's exit status through the tee

CFG=./configs/garfield/arm/virt_run.py          # in the fork, not in gem5-infra
AGENTIC=./gem5-ckpts/rpoint_ckpts/agentic                     # this directory
IMG=$AGENTIC/images/rpoint-ubuntu-24.04-v21.img
KERNEL=$AGENTIC/kernel/arm64-linux-kernel-6.8.12-1.0.0   # the vmlinux, NOT the -Image
BOOTLOADER=$AGENTIC/bootloader/boot_v2_qemu_virt.arm64

# Extra args go straight to virt_run.py, e.g. ./run_scripts/run_agent.sh --disable-fdp
OUTDIR=runs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUTDIR"
echo "Output dir: $OUTDIR"

./build/ARM/gem5.opt --outdir=$OUTDIR $CFG \
    --restore-dir $AGENTIC/checkpoints/agentic-gin-2121/cpt.0 \
    --disk-img $IMG \
    --kernel $KERNEL \
    --bootloader $BOOTLOADER \
    --release kvm-host \
    --progress-interval 10kHz \
    --settle-insts 0 --warmup-insts 10000000 --detailed-insts 50000000 \
    "$@" \
    2>&1 | tee "$OUTDIR/run.log"
