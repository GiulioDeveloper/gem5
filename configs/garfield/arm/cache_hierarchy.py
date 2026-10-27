# Copyright (c) 2025 Technical University of Munich
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Neoverse V2 classic cache hierarchy for the garfield ARM SE config.

Per core: private L1I (with FDP + tagged instruction prefetch), L1D (with
the Stride+SMS stack from the L1D class), a private L2 (with the BOP
prefetcher from the L2 class), and an MMU/page-table-walker cache, all
behind a per-core L2 crossbar. Prefetching is controlled by the three
constructor flags (enable_fdp / enable_l1d_prefetch / enable_l2_prefetch).
"""

from m5.objects import (
    FetchDirectedPrefetcher,
    L2XBar,
    MultiPrefetcher,
    TaggedPrefetcher,
)
from m5.params import NULL
from m5.util.convert import toMemorySize

from gem5.components.boards.abstract_board import AbstractBoard
from gem5.components.cachehierarchies.classic.caches.mmu_cache import (
    MMUCache,
)
from gem5.components.cachehierarchies.classic.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)

from . import neoverse_v2


class NeoverseV2CacheHierarchy(PrivateL1PrivateL2CacheHierarchy):
    """Neoverse V2 private L1/L2 hierarchy with prefetcher toggles."""

    def __init__(
        self,
        enable_fdp: bool = True,
        enable_l1d_prefetch: bool = True,
        enable_l2_prefetch: bool = True,
        cache_scale: int = 1,
    ) -> None:
        # Sizes here are unused (incorporate_cache builds the real caches
        # from the neoverse_v2 classes); passed for documentation only.
        super().__init__(l1d_size="64KiB", l1i_size="64KiB", l2_size="2MiB")
        self._enable_fdp = enable_fdp
        self._enable_l1d_prefetch = enable_l1d_prefetch
        self._enable_l2_prefetch = enable_l2_prefetch
        self._cache_scale = cache_scale

    def incorporate_cache(self, board: AbstractBoard) -> None:
        num_cores = board.get_processor().get_num_cores()

        board.connect_system_port(self.membus.cpu_side_ports)
        for _, port in board.get_memory().get_mem_ports():
            self.membus.mem_side_ports = port

        self.l1icaches = [neoverse_v2.L1I() for _ in range(num_cores)]
        self.l1dcaches = [neoverse_v2.L1D() for _ in range(num_cores)]
        self.l2buses = [L2XBar() for _ in range(num_cores)]
        self.l2caches = [neoverse_v2.L2() for _ in range(num_cores)]
        self.mmucaches = [MMUCache(size="8KiB") for _ in range(num_cores)]

        # Capacity limit study: more sets, same associativity and latency.
        if self._cache_scale != 1:
            for cache in self.l1icaches + self.l1dcaches + self.l2caches:
                size = toMemorySize(str(cache.size))
                cache.size = f"{size * self._cache_scale}B"
        self.mmubuses = [L2XBar(width=64) for _ in range(num_cores)]

        for i in range(num_cores):
            cpu = board.get_processor().get_cores()[i].core

            # L1I: optional FDP (decoupled front-end) + baseline tagged pf.
            self.l1icaches[i].prefetcher = MultiPrefetcher()
            if self._enable_fdp:
                fdp = FetchDirectedPrefetcher(
                    use_virtual_addresses=True, cpu=cpu
                )
                fdp.registerCache(self.l1icaches[i])
                self.l1icaches[i].prefetcher.prefetchers.append(fdp)
            self.l1icaches[i].prefetcher.prefetchers.append(
                TaggedPrefetcher(use_virtual_addresses=True)
            )
            for pf in self.l1icaches[i].prefetcher.prefetchers:
                pf.registerMMU(cpu.mmu)

            # L1D Stride+SMS stack is defined on the L1D class; detach it
            # for ablation.
            if not self._enable_l1d_prefetch:
                self.l1dcaches[i].prefetcher = NULL

            # L2 BOP prefetcher is defined on the L2 class; detach it for
            # ablation.
            if not self._enable_l2_prefetch:
                self.l2caches[i].prefetcher = NULL

        if board.has_coherent_io():
            self._setup_io_cache(board)

        for i, cpu in enumerate(board.get_processor().get_cores()):
            cpu.connect_icache(self.l1icaches[i].cpu_side)
            self.l1icaches[i].mem_side = self.l2buses[i].cpu_side_ports

            cpu.connect_dcache(self.l1dcaches[i].cpu_side)
            self.l1dcaches[i].mem_side = self.l2buses[i].cpu_side_ports

            self.mmucaches[i].mem_side = self.l2buses[i].cpu_side_ports
            self.mmubuses[i].mem_side_ports = self.mmucaches[i].cpu_side

            self.l2buses[i].mem_side_ports = self.l2caches[i].cpu_side
            self.membus.cpu_side_ports = self.l2caches[i].mem_side

            cpu.connect_walker_ports(
                self.mmubuses[i].cpu_side_ports,
                self.mmubuses[i].cpu_side_ports,
            )
            cpu.connect_interrupt()
