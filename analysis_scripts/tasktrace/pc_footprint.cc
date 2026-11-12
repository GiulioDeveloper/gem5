// Instruction footprint, LRU stack distances and branches per process and
// per thread, in one pass over a PC trace (pc_trace.py's format) read from
// stdin.
// Built and driven by pc_footprint.py, which prepares the side files and
// formats the results; see there for the definitions. Two address views:
// per process instance (a tgid between execs) and per process name (every
// process of a name shares one address space, so code at the same address
// in two git runs counts once). Per thread, the thread's whole stream (its
// user code and the kernel code run while it was current) on its own, with
// stack distances per instruction address as well as per line, and its
// footprint per bin: distinct instructions, lines and branches in each N
// instructions, cut either by the thread's own instruction count or by
// the run's (global windows).
//
//
// Code versions. A PC can hold different instructions over time (a JIT
// writing code, the kernel patching itself). With encodings in the trace
// (pc_trace v2), each address space (a process instance's user code, or
// the kernel) keeps the encodings seen at each PC, in first-seen order: the
// first is the PC itself, every later one a new instruction with its own
// key. A line's version goes up when one of its PCs shows an encoding it
// never had, at most once per visit (until the stream leaves the line: one
// visit reads one snapshot of the line); each line version is a line of
// its own. So distinct
// instructions, lines and branches, the LRU stacks, repeat distances and
// bins all count rewritten code as new code; pages (TLB reach) and the
// kernel code counted on behalf of a group do not. The rw_ columns give the
// part that comes from versions after the first.
//
// usage: zstd -dc pc_trace.zst | pc_footprint [--bins=N1,N2,...]
//            [--mnemonic-versions] SWITCHES EXECS OUTDIR VEC0 VEC1 CAP1
//            [CAP2 ...]
//   --bins    bin sizes in instructions for thread_bins.tsv (default none)
//   --mnemonic-versions  without encodings in the trace (v1), take the
//             mnemonic as the encoding: a lower bound on rewrites (only
//             those that change the mnemonic)
//   SWITCHES  global instruction count of each switch event, one per line,
//             in trace order (the markers after the first one)
//   EXECS     "insts tgid name" per exec event, by instruction count
//   VEC0/1    link addresses (hex) of the kernel vector tables; a
//             transfer into either is an exception, not a taken branch
//   CAPn      cache sizes in 64-byte lines for the hit counts

#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

constexpr uint64_t kMask48 = (1ull << 48) - 1;
constexpr uint64_t kEmpty = ~0ull;
constexpr int kHistBuckets = 40;

uint64_t
mix(uint64_t x)
{
    x ^= x >> 33;
    x *= 0xff51afd7ed558ccdull;
    x ^= x >> 33;
    x *= 0xc4ceb9fe1a85ec53ull;
    x ^= x >> 33;
    return x;
}

// Open-addressing map from 64-bit keys (never kEmpty) to 32-bit values.
class FlatMap
{
  public:
    explicit FlatMap(size_t cap = 1 << 16) { reset(cap); }

    // The value slot for key, inserting `init` if absent.
    uint32_t *
    get(uint64_t key, uint32_t init, bool *inserted)
    {
        if ((size_ + 1) * 10 > keys_.size() * 6)
            grow();
        size_t i = mix(key) & (keys_.size() - 1);
        while (keys_[i] != kEmpty) {
            if (keys_[i] == key) {
                *inserted = false;
                return &vals_[i];
            }
            i = (i + 1) & (keys_.size() - 1);
        }
        keys_[i] = key;
        vals_[i] = init;
        size_++;
        *inserted = true;
        return &vals_[i];
    }

    uint32_t *
    find(uint64_t key)
    {
        size_t i = mix(key) & (keys_.size() - 1);
        while (keys_[i] != kEmpty) {
            if (keys_[i] == key)
                return &vals_[i];
            i = (i + 1) & (keys_.size() - 1);
        }
        return nullptr;
    }

    size_t size() const { return size_; }

    template <typename F>
    void
    each(F f) const
    {
        for (size_t i = 0; i < keys_.size(); i++)
            if (keys_[i] != kEmpty)
                f(keys_[i], vals_[i]);
    }

  private:
    void
    reset(size_t cap)
    {
        keys_.assign(cap, kEmpty);
        vals_.assign(cap, 0);
        size_ = 0;
    }

    void
    grow()
    {
        std::vector<uint64_t> k;
        std::vector<uint32_t> v;
        k.swap(keys_);
        v.swap(vals_);
        reset(k.size() * 2);
        bool ins;
        for (size_t i = 0; i < k.size(); i++)
            if (k[i] != kEmpty)
                *get(k[i], v[i], &ins) = v[i];
    }

    std::vector<uint64_t> keys_;
    std::vector<uint32_t> vals_;
    size_t size_ = 0;
};

// LRU stack distance (number of distinct lines touched since the previous
// access to the same line) with a Fenwick tree over access slots: a slot
// holds 1 while it is the latest access of its line. Slots are renumbered
// when they run out.
class StackDistance
{
  public:
    // Small to start: there is one per process instance.
    explicit StackDistance(size_t n = 1 << 12) : last_(n) { resize(n); }

    // Distance of this access, or -1 for the first access to the line.
    int64_t
    access(uint64_t key)
    {
        if (now_ == slotKey_.size())
            compact();
        bool inserted;
        uint32_t *slot = last_.get(key, 0, &inserted);
        int64_t d = -1;
        if (!inserted) {
            uint32_t t = *slot;
            d = live_ - prefix(t + 1);
            add(t, -1);
            slotKey_[t] = kEmpty;
        } else {
            live_++;
        }
        add(now_, 1);
        slotKey_[now_] = key;
        *slot = now_++;
        return d;
    }

  private:
    void
    resize(size_t n)
    {
        tree_.assign(n + 1, 0);
        slotKey_.assign(n, kEmpty);
    }

    void
    add(size_t i, int v)
    {
        for (i++; i < tree_.size(); i += i & -i)
            tree_[i] += v;
    }

    int64_t
    prefix(size_t i) const   // live slots in [0, i)
    {
        int64_t s = 0;
        for (; i > 0; i -= i & -i)
            s += tree_[i];
        return s;
    }

    void
    compact()
    {
        std::vector<uint64_t> keys;
        keys.reserve(live_);
        for (size_t s = 0; s < now_; s++)
            if (slotKey_[s] != kEmpty)
                keys.push_back(slotKey_[s]);
        size_t n = slotKey_.size();
        while (keys.size() * 2 > n)
            n *= 2;
        resize(n);
        for (size_t s = 0; s < keys.size(); s++) {
            slotKey_[s] = keys[s];
            *last_.find(keys[s]) = s;
            tree_[s + 1] = 1;
        }
        for (size_t i = 1; i < tree_.size(); i++) {   // O(n) build
            size_t j = i + (i & -i);
            if (j < tree_.size())
                tree_[j] += tree_[i];
        }
        now_ = keys.size();
    }

    FlatMap last_;
    std::vector<int32_t> tree_;
    std::vector<uint64_t> slotKey_;
    size_t now_ = 0;
    int64_t live_ = 0;
};

enum Branch : uint8_t {
    NotBranch, Cond, Direct, Call, IndirectCall, IndirectJump, Return,
    ExceptionReturn, NumBranch
};
const char *kBranchNames[] = {
    "", "cond", "direct", "call", "indirect_call", "indirect_jump",
    "return", "exception_return"
};

bool
startsWith(const char *s, const char *p)
{
    return strncmp(s, p, strlen(p)) == 0;
}

Branch
classify(const char *m)
{
    switch (m[0]) {
      case 'b':
        if (m[1] == '\0') return Direct;
        if (m[1] == '.') return Cond;
        if (!strcmp(m, "bl")) return Call;
        if (startsWith(m, "blr")) return IndirectCall;
        if (!strcmp(m, "br") || startsWith(m, "braa") || startsWith(m, "brab"))
            return IndirectJump;
        if (m[1] == 'c' && m[2] == '.') return Cond;   // bc.cond
        return NotBranch;
      case 'c':
        return !strcmp(m, "cbz") || !strcmp(m, "cbnz") ? Cond : NotBranch;
      case 't':
        return !strcmp(m, "tbz") || !strcmp(m, "tbnz") ? Cond : NotBranch;
      case 'r':
        return startsWith(m, "ret") ? Return : NotBranch;
      case 'e':
        return startsWith(m, "eret") ? ExceptionReturn : NotBranch;
      default:
        return NotBranch;
    }
}

// Line accesses of one group or instance in one address view.
struct Stats
{
    uint64_t insts = 0, accesses = 0, privCold = 0, sharedCold = 0;
    // Of the cold misses, those on a rewritten line (a version after the
    // first): the refetch after the code changed.
    uint64_t privRwCold = 0, sharedRwCold = 0;
    std::vector<uint64_t> privHits, sharedHits;
    uint64_t privHist[kHistBuckets] = {}, sharedHist[kHistBuckets] = {};
    StackDistance *priv = nullptr;   // this group's or instance's code alone

    explicit Stats(size_t nc = 0) : privHits(nc), sharedHits(nc) {}

    // Records one access: dp from the private stack, ds from the shared;
    // rw: the line is a rewritten version.
    void
    record(int64_t dp, int64_t ds, const std::vector<int64_t> &caps,
           bool rw)
    {
        accesses++;
        if (dp < 0) privCold++, privRwCold += rw;
        else privHist[bucket(dp)]++;
        if (ds < 0) sharedCold++, sharedRwCold += rw;
        else sharedHist[bucket(ds)]++;
        for (size_t c = 0; c < caps.size(); c++) {
            if (dp >= 0 && dp < caps[c]) privHits[c]++;
            if (ds >= 0 && ds < caps[c]) sharedHits[c]++;
        }
    }

    int64_t
    privAccess(uint64_t line)
    {
        if (!priv)
            priv = new StackDistance;
        return priv->access(line);
    }

    static int
    bucket(int64_t d)   // d in [2^(b-1) - 1, 2^b - 1)
    {
        return std::min<int64_t>(64 - __builtin_clzll(d + 1),
                                 kHistBuckets - 1);
    }
};

struct Group
{
    std::string name;
    bool kernel = false;
    Stats byInstance, byName;   // the two address views
    // Kernel code run on behalf of this group (its tasks were current),
    // in the per-instance view's shared stream.
    uint64_t kInsts = 0, kAccesses = 0, kSharedCold = 0;
    std::vector<uint64_t> kSharedHits;
};

struct Instance
{
    int64_t tgid;
    int gen;
    uint32_t group;
    Stats stats;
    uint64_t kInsts = 0;
};

// Values counted per bin: distinct user and kernel instructions, distinct
// user and kernel lines, distinct branches by type, distinct taken branches.
constexpr int kBinVals = 4 + (NumBranch - 1) + 1;
constexpr int kBinTaken = kBinVals - 1;

// One thread's bins of one size and one cut. Bins are closed in order;
// each closed bin adds its values weighted by its instructions.
struct BinAcc
{
    uint64_t cur = kEmpty, w = 0, v[kBinVals] = {};
    uint64_t bins = 0, sumW = 0, sumWV[kBinVals] = {}, maxV[kBinVals] = {};

    void
    close()
    {
        bins++;
        sumW += w;
        for (int i = 0; i < kBinVals; i++) {
            sumWV[i] += w * v[i];
            maxV[i] = std::max(maxV[i], v[i]);
        }
    }

    void
    start(uint64_t b)
    {
        cur = b;
        w = 0;
        memset(v, 0, sizeof v);
    }
};

// One thread: a pid within a process instance (an exec starts a new one),
// or a kernel thread.
struct Thread
{
    int64_t tgid, pid;
    uint32_t instance, group;
    bool kthread;
    std::string comm;
    uint64_t kInsts = 0;
    Stats lines;                 // per line; insts counts user and kernel
    StackDistance pcStack;       // per instruction address
    uint64_t pcCold = 0, pcHist[kHistBuckets] = {};
    // Distinct instructions (value: branch type | taken << 8) and lines,
    // keyed by the full PC, so kernel code (bit 63) is apart.
    FlatMap pcs{1 << 12}, uniqLines{1 << 10};
    // Per bin size, two cuts (even: the thread's own count, odd: the run's).
    // binPc/binLine give each distinct PC or line an index into the marks:
    // the bin (+1) it was last counted in, per cut, and for a PC also the
    // bin it was last counted as taken in.
    std::vector<BinAcc> bins;
    FlatMap binPc{1 << 10}, binLine{1 << 8};
    std::vector<uint32_t> pcMark, lineMark;
    uint64_t lastLine = kEmpty;

    Thread(int64_t tgid, int64_t pid, uint32_t instance, uint32_t group,
           bool kthread, std::string comm, size_t nc)
        : tgid(tgid), pid(pid), instance(instance), group(group),
          kthread(kthread), comm(std::move(comm)), lines(nc)
    {}

    // Counts one committed instruction in every bin; own and run are the
    // thread's and the run's instruction counts before it; pc and line are
    // the thread's keys of the instruction and its line (versioned).
    void
    binStep(const std::vector<uint64_t> &sizes, uint64_t own, uint64_t run,
            uint64_t pc, uint64_t line, bool kernel, Branch br)
    {
        if (sizes.empty())
            return;
        const size_t nb = bins.size();
        bool ins;
        uint32_t pi = *binPc.get(pc, binPc.size(), &ins);
        if (ins)
            pcMark.resize(pcMark.size() + 2 * nb, 0);
        bool newLine = line != lastLine;
        uint32_t li = 0;
        if (newLine) {
            li = *binLine.get(line, binLine.size(), &ins);
            if (ins)
                lineMark.resize(lineMark.size() + nb, 0);
            lastLine = line;
        }
        for (size_t c = 0; c < nb; c++) {
            uint64_t b = (c & 1 ? run : own) / sizes[c / 2];
            BinAcc &a = bins[c];
            if (a.cur != b) {
                if (a.cur != kEmpty)
                    a.close();
                a.start(b);
            }
            a.w++;
            uint32_t tag = b + 1;
            uint32_t &m = pcMark[size_t(pi) * 2 * nb + 2 * c];
            if (m != tag) {
                m = tag;
                a.v[kernel]++;
                if (br != NotBranch)
                    a.v[3 + br]++;
            }
            if (newLine) {
                uint32_t &lm = lineMark[size_t(li) * nb + c];
                if (lm != tag) {
                    lm = tag;
                    a.v[2 + kernel]++;
                }
            }
        }
    }

    // The thread's last instruction, at pc, was a taken branch.
    void
    binTaken(uint64_t pc)
    {
        uint32_t *pi = binPc.find(pc);
        if (!pi)
            return;
        const size_t nb = bins.size();
        for (size_t c = 0; c < nb; c++) {
            uint32_t tag = bins[c].cur + 1;
            uint32_t &m = pcMark[size_t(*pi) * 2 * nb + 2 * c + 1];
            if (m != tag) {
                m = tag;
                bins[c].v[kBinTaken]++;
            }
        }
    }
};

struct Exec
{
    uint64_t insts;
    int64_t tgid;
    std::string name;
};

// Distinct instructions, lines and pages of one address view, with each
// instruction's group (bits 0-15), branch type (16-23) and taken flag (24).
// insts holds the first version of each PC, keyed by (space, address);
// rwInsts the later versions, keyed by (space, version serial). lines holds
// both: a later line version's key has bit 47 set (a real line number has
// at most 42 bits), with its serial below.
struct Footprint
{
    FlatMap insts{1 << 24}, rwInsts{1 << 10}, lines{1 << 20}, pages{1 << 16};
};

constexpr uint64_t kRwLineBit = 1ull << 47;

// The encodings seen at one PC of one address space: a list in first-seen
// order (the head is the first). serial: 0 for the first, else a run-wide
// serial number that keys the version. cur (head only): the list node
// executed last.
struct CodeVersion
{
    uint32_t enc, next, serial, cur;
};

// One line of one address space: its current version's serial (0: the
// first) and the most encodings any of its PCs has had.
struct LineVersion
{
    uint32_t serial, maxPcVersions;
};

uint32_t
fnv1a(const char *s)
{
    uint32_t h = 2166136261u;
    for (; *s; s++)
        h = (h ^ uint8_t(*s)) * 16777619u;
    return h;
}

// Rewrites in one address space (an instance, or the kernel).
struct RwCount
{
    uint64_t pcs = 0;      // PCs that had more than one encoding
    uint64_t flips = 0;    // a PC going back to an encoding it had before
    uint64_t linesLb = 0;  // sum over lines of (most encodings at a PC - 1)
};

void
writeStatsHeader(FILE *o, const char *prefix,
                 const std::vector<int64_t> &caps)
{
    fprintf(o, "\t%sinsts\t%sline_accesses\t%spriv_cold\t%sshared_cold",
            prefix, prefix, prefix, prefix);
    for (auto c : caps) fprintf(o, "\t%spriv_hits_%" PRId64, prefix, c);
    for (auto c : caps) fprintf(o, "\t%sshared_hits_%" PRId64, prefix, c);
    fprintf(o, "\t%spriv_rw_cold\t%sshared_rw_cold", prefix, prefix);
}

void
writeStats(FILE *o, const Stats &s)
{
    fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64, s.insts,
            s.accesses, s.privCold, s.sharedCold);
    for (auto h : s.privHits) fprintf(o, "\t%" PRIu64, h);
    for (auto h : s.sharedHits) fprintf(o, "\t%" PRIu64, h);
    fprintf(o, "\t%" PRIu64 "\t%" PRIu64, s.privRwCold, s.sharedRwCold);
}

// Distinct counts and branches of one footprint, per space (the key's top
// 16 bits) or per group (the value's low 16 bits).
struct Distinct
{
    std::vector<uint64_t> insts, lines, pages, rwInsts, rwLines, rwBr;
    std::vector<std::vector<uint64_t>> br, taken;

    Distinct(const Footprint &fp, size_t n, bool bySpace)
        : insts(n), lines(n), pages(n), rwInsts(n), rwLines(n), rwBr(n),
          br(n, std::vector<uint64_t>(NumBranch)), taken(br)
    {
        auto id = [&](uint64_t k, uint32_t v) -> size_t {
            size_t i = bySpace ? k >> 48 : v & 0xffff;
            return i < n ? i : n;   // n: not counted (the kernel space)
        };
        auto inst = [&](uint64_t k, uint32_t v, bool rw) {
            size_t i = id(k, v);
            if (i == n) return;
            insts[i]++;
            rwInsts[i] += rw;
            Branch b = Branch((v >> 16) & 0xff);
            if (b != NotBranch) {
                br[i][b]++;
                rwBr[i] += rw;
                if (v >> 24 & 1) taken[i][b]++;
            }
        };
        fp.insts.each([&](uint64_t k, uint32_t v) { inst(k, v, false); });
        fp.rwInsts.each([&](uint64_t k, uint32_t v) { inst(k, v, true); });
        fp.lines.each([&](uint64_t k, uint32_t v) {
            size_t i = id(k, v);
            if (i < n) {
                lines[i]++;
                rwLines[i] += (k & kRwLineBit) != 0;
            }
        });
        fp.pages.each([&](uint64_t k, uint32_t v) {
            size_t i = id(k, v);
            if (i < n) pages[i]++;
        });
    }

    void
    write(FILE *o, size_t i) const
    {
        fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64, insts[i], lines[i],
                pages[i]);
        for (int b = 1; b < NumBranch; b++)
            fprintf(o, "\t%" PRIu64 "\t%" PRIu64, br[i][b], taken[i][b]);
        fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64, rwInsts[i],
                rwLines[i], rwBr[i]);
    }

    static void
    header(FILE *o, const char *prefix)
    {
        fprintf(o, "\t%suniq_insts\t%suniq_lines\t%suniq_pages", prefix,
                prefix, prefix);
        for (int b = 1; b < NumBranch; b++)
            fprintf(o, "\t%sbr_%s\t%sbr_%s_taken", prefix, kBranchNames[b],
                    prefix, kBranchNames[b]);
        fprintf(o, "\t%srw_insts\t%srw_lines\t%srw_br", prefix, prefix,
                prefix);
    }
};

void
writeHist(FILE *o, const std::string &name, const char *view,
          const uint64_t *hist)
{
    for (int b = 0; b < kHistBuckets; b++)
        if (hist[b])
            fprintf(o, "%s\t%s\t%d\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64 "\n",
                    name.c_str(), view, b, uint64_t(b ? (1ull << (b - 1)) - 1 : 0),
                    uint64_t((1ull << b) - 1), hist[b]);
}

}  // namespace

int
main(int argc, char **argv)
{
    std::vector<uint64_t> binSizes;
    bool proxy = false;   // --mnemonic-versions
    while (argc > 1 && startsWith(argv[1], "--")) {
        if (startsWith(argv[1], "--bins=")) {
            for (char *s = strtok(argv[1] + 7, ","); s;
                 s = strtok(nullptr, ","))
                binSizes.push_back(strtoull(s, nullptr, 10));
        } else if (!strcmp(argv[1], "--mnemonic-versions")) {
            proxy = true;
        } else {
            fprintf(stderr, "unknown option %s\n", argv[1]);
            return 2;
        }
        argv++;
        argc--;
    }
    if (argc < 7) {
        fprintf(stderr, "usage: %s [--bins=N,...] [--mnemonic-versions] "
                "SWITCHES EXECS OUTDIR VEC0 VEC1 CAP...\n", argv[0]);
        return 2;
    }
    std::vector<uint64_t> switches;
    {
        FILE *f = fopen(argv[1], "r");
        unsigned long long x;
        while (f && fscanf(f, "%llu", &x) == 1)
            switches.push_back(x);
        if (f) fclose(f);
    }
    std::vector<Exec> execs;
    {
        FILE *f = fopen(argv[2], "r");
        char line[4096];
        while (f && fgets(line, sizeof line, f)) {
            unsigned long long n;
            long long t;
            char name[4000];
            if (sscanf(line, "%llu %lld %3999[^\n]", &n, &t, name) == 3)
                execs.push_back({n, t, name});
        }
        if (f) fclose(f);
    }
    std::string outdir = argv[3];
    uint64_t vecLink[2] = {strtoull(argv[4], nullptr, 16),
                           strtoull(argv[5], nullptr, 16)};
    std::vector<int64_t> caps;
    for (int i = 6; i < argc; i++)
        caps.push_back(atoll(argv[i]));
    const size_t nc = caps.size();

    std::vector<Group> groups;
    std::unordered_map<std::string, uint32_t> groupId;
    auto group = [&](const std::string &name, bool kernel) -> uint32_t {
        auto it = groupId.find(name);
        if (it != groupId.end())
            return it->second;
        Group g;
        g.name = name;
        g.kernel = kernel;
        g.byInstance = Stats(nc);
        g.byName = Stats(nc);
        g.kSharedHits.assign(nc, 0);
        groups.push_back(std::move(g));
        if (groups.size() >= 0xffff) {
            fprintf(stderr, "too many process names\n");
            exit(1);
        }
        return groupId[name] = groups.size() - 1;
    };
    const uint32_t kernelGroup = group("[kernel]", true);

    std::vector<Instance> instances;
    instances.push_back({-1, 0, kernelGroup, Stats(nc)});   // 0: none
    std::unordered_map<int64_t, uint32_t> tgidInstance;
    std::unordered_map<int64_t, int> tgidGen;
    auto newInstance = [&](int64_t tgid, uint32_t g) -> uint32_t {
        int gen = tgidGen[tgid]++;
        instances.push_back({tgid, gen, g, Stats(nc)});
        if (instances.size() >= 0xffff) {
            fprintf(stderr, "too many process instances\n");
            exit(1);
        }
        return tgidInstance[tgid] = instances.size() - 1;
    };

    std::vector<std::unique_ptr<Thread>> threads;
    std::unordered_map<uint64_t, uint32_t> threadId;
    auto thread = [&](uint32_t inst, int64_t tgid, int64_t pid, uint32_t gid,
                      bool kthread, const char *comm) -> uint32_t {
        uint64_t k = (uint64_t(inst) << 32) | uint32_t(pid);
        auto it = threadId.find(k);
        if (it != threadId.end()) {
            Thread &t = *threads[it->second];
            t.group = gid;
            t.comm = comm;
            return it->second;
        }
        threads.push_back(std::make_unique<Thread>(tgid, pid, inst, gid,
                                                   kthread, comm, nc));
        threads.back()->bins.resize(2 * binSizes.size());
        return threadId[k] = threads.size() - 1;
    };

    // User code is keyed by instance in one view and by group (name) in the
    // other; kernel code is global (space 0xffff) in both.
    Footprint fpInst, fpName;
    FlatMap kInstsBehalf(1 << 22), kLinesBehalf(1 << 18);
    StackDistance sharedInst(1 << 16), sharedName(1 << 16);

    uint64_t slide = 0, vec[2] = {0, 0};
    // Global instruction count, as the tracer counts: O3 leaves NOPs out,
    // the atomic core counts them. Both are kept until a switch event
    // shows which one the run uses.
    uint64_t g = 0, gNops = 0;
    int countNops = -1;          // unknown until a switch tells them apart
    size_t nextSwitch = 0, nextExec = 0, markers = 0;
    uint64_t renames = 0, execsApplied = 0;
    uint64_t countMismatches = 0, maxMismatch = 0;
    int64_t curTgid = -1;
    uint32_t curInst = 0, curGroup = kernelGroup, behalf = kernelGroup;
    uint32_t curThread = 0, prevThread = 0;
    threads.push_back(std::make_unique<Thread>(-1, -1, 0, kernelGroup, true,
                                               "[before any marker]", nc));
    threads.back()->bins.resize(2 * binSizes.size());
    bool haveMarker = false;

    uint64_t prevPc = 0, prevKey = kEmpty, prevNameKey = kEmpty;
    uint64_t prevThPc = kEmpty;
    FlatMap *prevInstMap = &fpInst.insts, *prevNameMap = &fpName.insts;
    uint64_t prevLine = kEmpty;
    Branch prevBranch = NotBranch;
    uint64_t total = 0;

    // Code versions (see the top of the file). versionsOn once the trace
    // shows an encoding (or with --mnemonic-versions). decodeEnc rebuilds
    // each instruction's encoding (pc_trace.py's decode key); pcVersion
    // maps (space, address) to the head of its CodeVersion list;
    // lineVersion holds the lines that were ever rewritten.
    bool versionsOn = proxy;
    std::vector<CodeVersion> versions(1);   // index 0: none
    std::vector<LineVersion> lineVersions(1);
    FlatMap decodeEnc(1 << 16), pcVersion(1 << 16), lineVersion(1 << 10);
    std::vector<RwCount> rw(1);   // per instance; 0: the kernel
    uint32_t nextSerial = 0;
    uint64_t missingEnc = 0, encFields = 0;
    uint64_t prevRawLine = kEmpty;
    uint32_t curLineSerial = 0;
    bool bumpedThisVisit = false;

    static char buf[1 << 16];
    while (fgets(buf, sizeof buf, stdin)) {
        size_t len = strlen(buf);
        if (len && buf[len - 1] == '\n')
            buf[--len] = '\0';
        if (buf[0] == '#') {
            // "#\ttask\t<tick>\t<tgid>\t<pid>\t<u|k>\t<process>\t<comm>"
            std::vector<char *> f;
            for (char *s = strtok(buf, "\t"); s; s = strtok(nullptr, "\t"))
                f.push_back(s);
            if (f.size() >= 3 && !strcmp(f[1], "kaslr_slide")) {
                slide = strtoull(f[2], nullptr, 16);
                vec[0] = vecLink[0] + slide;
                vec[1] = vecLink[1] + slide;
            } else if (f.size() >= 7 && !strcmp(f[1], "task")) {
                if (markers++ > 0) {
                    if (nextSwitch >= switches.size()) {
                        fprintf(stderr, "more markers than switches\n");
                        return 1;
                    }
                    // The count since the previous switch must land on this
                    // one exactly, or execs would be misplaced.
                    uint64_t want = switches[nextSwitch++];
                    if (countNops < 0 && g != gNops) {
                        if (g == want) countNops = 0;
                        else if (gNops == want) countNops = 1;
                    }
                    uint64_t have = countNops == 1 ? gNops : g;
                    if (have != want) {
                        countMismatches++;
                        maxMismatch = std::max(maxMismatch,
                            have > want ? have - want : want - have);
                    }
                    g = gNops = want;
                }
                haveMarker = true;
                bool kthread = f[5][0] == 'k';
                curTgid = f[3][0] == '?' ? -1 : atoll(f[3]);
                int64_t pid = f[4][0] == '?' ? -1 : atoll(f[4]);
                uint32_t gid = group(f[6], false);
                behalf = gid;
                curGroup = gid;
                if (kthread || curTgid < 0) {
                    curInst = 0;
                } else {
                    auto it = tgidInstance.find(curTgid);
                    if (it == tgidInstance.end()) {
                        curInst = newInstance(curTgid, gid);
                    } else {
                        curInst = it->second;
                        if (instances[curInst].group != gid) {
                            instances[curInst].group = gid;   // renamed
                            renames++;
                        }
                    }
                }
                curThread = thread(curInst, curTgid, pid, gid, kthread,
                                   f.size() > 7 ? f[7] : f[6]);
            }
            continue;
        }
        if (!haveMarker)
            continue;
        // An exec changes the address space and the name of its tgid.
        while (nextExec < execs.size() && execs[nextExec].insts <= (countNops == 1 ? gNops : g)) {
            const Exec &e = execs[nextExec++];
            uint32_t gid = group(e.name, false);
            uint32_t inst = newInstance(e.tgid, gid);
            execsApplied++;
            if (e.tgid == curTgid) {
                curInst = inst;
                curGroup = gid;
                behalf = gid;
                // The exec'ing thread becomes the group leader.
                curThread = thread(inst, e.tgid, e.tgid, gid, false,
                                   e.name.c_str());
            }
        }

        // "[pc ]mnemonic[\tencoding]"
        bool hasEnc = false;
        uint32_t encField = 0;
        if (char *tab = strchr(buf, '\t')) {
            *tab = '\0';
            encField = strtoul(tab + 1, nullptr, 16);
            hasEnc = versionsOn = true;
            encFields++;
        }
        char *sp = strchr(buf, ' ');
        uint64_t pc;
        const char *mnem;
        if (sp) {
            *sp = '\0';
            pc = strtoull(buf, nullptr, 16);
            mnem = sp + 1;
        } else {
            pc = prevPc + 4;
            mnem = buf;
        }
        if (prevBranch != NotBranch && pc != prevPc + 4) {
            bool exception = (pc >= vec[0] && pc < vec[0] + 0x800) ||
                             (pc >= vec[1] && pc < vec[1] + 0x800);
            if (!exception) {
                if (uint32_t *v = prevInstMap->find(prevKey)) *v |= 1u << 24;
                if (uint32_t *v = prevNameMap->find(prevNameKey))
                    *v |= 1u << 24;
                if (uint32_t *v = threads[prevThread]->pcs.find(prevThPc))
                    *v |= 1u << 8;
                threads[prevThread]->binTaken(prevThPc);
            }
        }

        bool kernel = pc >> 63;
        uint32_t gid = kernel ? kernelGroup : curGroup;
        uint64_t va = pc & kMask48;
        uint64_t spInst = kernel ? 0xffffull : curInst;
        uint64_t spName = kernel ? 0xffffull : curGroup;
        uint64_t key = (spInst << 48) | va;
        uint64_t rawLine = (spInst << 48) | (va >> 6);

        // ---- code version of this instruction and its line --------------
        uint32_t pcSerial = 0;
        bool rewrote = false;
        if (versionsOn) {
            if (rawLine != prevRawLine)
                bumpedThisVisit = false;
            const size_t space = kernel ? 0 : curInst;
            if (rw.size() <= space)
                rw.resize(instances.size());
            uint32_t enc = 0;
            bool known = true;
            if (proxy && !hasEnc) {
                enc = fnv1a(mnem);
            } else {
                // pc_trace.py's decode key: the PC for kernel code; for
                // user code the PC and the marker's tgid, -1 before the
                // first switch (between the first and second marker).
                int64_t dt = markers >= 2 ? curTgid : -1;
                if (!kernel && uint64_t(dt + 2) >= 0xffff) {
                    fprintf(stderr, "tgid %" PRId64 " too large for the "
                            "decode key\n", dt);
                    return 1;
                }
                uint64_t dk = kernel ? pc : (uint64_t(dt + 2) << 48) | va;
                bool ins;
                if (hasEnc) {
                    enc = *decodeEnc.get(dk, encField, &ins) = encField;
                } else if (uint32_t *e = decodeEnc.find(dk)) {
                    enc = *e;
                } else {
                    missingEnc++;
                    known = false;
                }
            }
            if (known) {
                bool ins;
                uint32_t *h = pcVersion.get(key, 0, &ins);
                if (ins) {
                    *h = versions.size();
                    versions.push_back({enc, 0, 0, *h});
                } else {
                    const uint32_t head = *h;
                    uint32_t i = head, last = 0, n = 0;
                    while (i && versions[i].enc != enc) {
                        last = i;
                        i = versions[i].next;
                        n++;
                    }
                    if (!i) {   // an encoding this PC never had
                        i = versions.size();
                        versions.push_back({enc, 0, ++nextSerial, 0});
                        versions[last].next = i;
                        const uint32_t count = n + 1;   // encodings now
                        if (count == 2)
                            rw[space].pcs++;
                        uint32_t *l = lineVersion.get(rawLine,
                                                      lineVersions.size(),
                                                      &ins);
                        if (ins)
                            lineVersions.push_back({0, 1});
                        LineVersion &lv = lineVersions[*l];
                        lv.maxPcVersions = std::max(lv.maxPcVersions, count);
                        // One visit to a line (until the stream leaves it)
                        // reads one snapshot of it: new encodings found in
                        // the same visit belong to the same new version.
                        if (!bumpedThisVisit) {
                            lv.serial = ++nextSerial;
                            bumpedThisVisit = true;
                            rewrote = true;
                        }
                    } else if (versions[head].cur != i) {
                        rw[space].flips++;
                    }
                    versions[head].cur = i;
                    pcSerial = versions[i].serial;
                }
            }
            if (rawLine != prevRawLine || rewrote) {
                uint32_t *l = lineVersion.find(rawLine);
                curLineSerial = l ? lineVersions[*l].serial : 0;
                prevRawLine = rawLine;
            }
        }
        const uint32_t lineSerial = versionsOn ? curLineSerial : 0;
        const bool rwLine = lineSerial != 0;
        // Keys of this instruction and line: the address for a first
        // version, the serial for a later one.
        FlatMap &instMap = pcSerial ? fpInst.rwInsts : fpInst.insts;
        FlatMap &nameMap = pcSerial ? fpName.rwInsts : fpName.insts;
        if (pcSerial)
            key = (spInst << 48) | pcSerial;
        uint64_t nameKey = (spName << 48) | (pcSerial ? pcSerial : va);
        uint64_t line = rwLine ? (spInst << 48) | kRwLineBit | lineSerial
                               : rawLine;
        uint64_t nameLine = (spName << 48) |
            (rwLine ? kRwLineBit | lineSerial : va >> 6);
        // The thread's keys: raw PC and PC >> 6 for a first version; later
        // versions apart from every real address (user: top bits 0x4000 or
        // bit 50; kernel: 0xc000 or bit 57 alone, so bit 63 and bit 57
        // still tell kernel code).
        uint64_t thPc = pcSerial ? ((kernel ? 0xc000ull : 0x4000ull) << 48) |
                                       pcSerial
                                 : pc;
        uint64_t thLine = rwLine ? (kernel ? 1ull << 57 : 1ull << 50) |
                                       lineSerial
                                 : pc >> 6;

        Branch br = classify(mnem);
        uint32_t init = gid | (uint32_t(br) << 16);
        bool ins;
        instMap.get(key, init, &ins);
        nameMap.get(nameKey, init, &ins);
        Group &grp = groups[gid];
        Instance &inst = instances[kernel ? 0 : curInst];
        grp.byInstance.insts++;
        grp.byName.insts++;
        if (!kernel) inst.stats.insts++;
        Thread &th = *threads[curThread];
        th.binStep(binSizes, th.lines.insts, total, thPc, thLine, kernel, br);
        th.lines.insts++;
        th.pcs.get(thPc, br, &ins);
        int64_t dpc = th.pcStack.access(thPc);
        if (dpc < 0) th.pcCold++;
        else th.pcHist[Stats::bucket(dpc)]++;
        if (kernel) {
            th.kInsts++;
            groups[behalf].kInsts++;
            instances[curInst].kInsts++;
            kInstsBehalf.get((uint64_t(behalf) << 48) | va, 0, &ins);
        }
        if (line != prevLine) {
            fpInst.lines.get(line, gid, &ins);
            fpInst.pages.get((spInst << 48) | (va >> 12), gid, &ins);
            fpName.lines.get(nameLine, gid, &ins);
            fpName.pages.get((spName << 48) | (va >> 12), gid, &ins);
            if (kernel)
                kLinesBehalf.get((uint64_t(behalf) << 48) | (va >> 6), 0,
                                 &ins);
            int64_t ds = sharedInst.access(line);
            grp.byInstance.record(grp.byInstance.privAccess(line), ds, caps,
                                  rwLine);
            if (!kernel)
                inst.stats.record(inst.stats.privAccess(line), ds, caps,
                                  rwLine);
            th.uniqLines.get(thLine, 0, &ins);
            th.lines.record(th.lines.privAccess(thLine), ds, caps, rwLine);
            grp.byName.record(grp.byName.privAccess(nameLine),
                              sharedName.access(nameLine), caps, rwLine);
            if (kernel) {
                Group &b = groups[behalf];
                b.kAccesses++;
                if (ds < 0) b.kSharedCold++;
                for (size_t c = 0; c < nc; c++)
                    if (ds >= 0 && ds < caps[c]) b.kSharedHits[c]++;
            }
            prevLine = line;
        }
        prevPc = pc;
        prevThread = curThread;
        prevKey = key;
        prevNameKey = nameKey;
        prevThPc = thPc;
        prevInstMap = &instMap;
        prevNameMap = &nameMap;
        prevBranch = br;
        total++;
        if (strcmp(mnem, "nop") != 0)
            g++;
        gNops++;
        if ((total & ((1ull << 30) - 1)) == 0)
            fprintf(stderr, "%" PRIu64 "G instructions\n", total >> 30);
    }

    // ---- distinct counts -------------------------------------------------
    size_t ng = groups.size(), ni = instances.size();
    Distinct dGroup(fpInst, ng, false), dName(fpName, ng, false),
        dInst(fpInst, ni, true);
    std::vector<uint64_t> kbInsts(ng), kbLines(ng);
    kInstsBehalf.each([&](uint64_t k, uint32_t) { kbInsts[k >> 48]++; });
    kLinesBehalf.each([&](uint64_t k, uint32_t) { kbLines[k >> 48]++; });
    std::vector<uint64_t> instancesOf(ng);
    for (size_t i = 1; i < ni; i++)
        instancesOf[instances[i].group]++;
    // Rewrites per instance (0: the kernel) and per group.
    rw.resize(ni);
    lineVersion.each([&](uint64_t k, uint32_t v) {
        uint64_t s = k >> 48;
        rw[s == 0xffff ? 0 : s].linesLb += lineVersions[v].maxPcVersions - 1;
    });
    std::vector<RwCount> rwGroup(ng);
    for (size_t i = 0; i < ni; i++) {
        RwCount &d = rwGroup[i ? instances[i].group : kernelGroup];
        d.pcs += rw[i].pcs;
        d.flips += rw[i].flips;
        d.linesLb += rw[i].linesLb;
    }
    auto writeRw = [](FILE *f, const RwCount &r) {
        fprintf(f, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64, r.pcs, r.flips,
                r.linesLb);
    };

    // groups.tsv: per name; plain columns in the per-instance view, m_
    // columns in the per-name view.
    FILE *o = fopen((outdir + "/groups.tsv").c_str(), "w");
    fprintf(o, "group\tkernel\tinstances");
    writeStatsHeader(o, "", caps);
    Distinct::header(o, "");
    writeStatsHeader(o, "m_", caps);
    Distinct::header(o, "m_");
    fprintf(o, "\tk_insts\tk_accesses\tk_shared_cold");
    for (auto c : caps) fprintf(o, "\tk_shared_hits_%" PRId64, c);
    fprintf(o, "\tk_uniq_insts\tk_uniq_lines\trw_pcs\trw_flips\t"
            "rw_lines_lb\n");
    for (size_t i = 0; i < ng; i++) {
        const Group &gr = groups[i];
        fprintf(o, "%s\t%d\t%" PRIu64, gr.name.c_str(), gr.kernel,
                instancesOf[i]);
        writeStats(o, gr.byInstance);
        dGroup.write(o, i);
        writeStats(o, gr.byName);
        dName.write(o, i);
        fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64, gr.kInsts,
                gr.kAccesses, gr.kSharedCold);
        for (auto h : gr.kSharedHits) fprintf(o, "\t%" PRIu64, h);
        fprintf(o, "\t%" PRIu64 "\t%" PRIu64, kbInsts[i], kbLines[i]);
        writeRw(o, rwGroup[i]);
        fprintf(o, "\n");
    }
    fclose(o);

    // instances.tsv: per process instance (user code only).
    o = fopen((outdir + "/instances.tsv").c_str(), "w");
    fprintf(o, "instance\ttgid\tgeneration\tgroup");
    writeStatsHeader(o, "", caps);
    Distinct::header(o, "");
    fprintf(o, "\tk_insts\trw_pcs\trw_flips\trw_lines_lb\n");
    for (size_t i = 1; i < ni; i++) {
        const Instance &in = instances[i];
        fprintf(o, "%zu\t%" PRId64 "\t%d\t%s", i, in.tgid, in.gen,
                groups[in.group].name.c_str());
        writeStats(o, in.stats);
        dInst.write(o, i);
        fprintf(o, "\t%" PRIu64, in.kInsts);
        writeRw(o, rw[i]);
        fprintf(o, "\n");
    }
    fclose(o);

    // threads.tsv: per thread, user and kernel code together; the stack
    // distance columns are per line, pc_cold per instruction address.
    o = fopen((outdir + "/threads.tsv").c_str(), "w");
    fprintf(o, "thread\ttgid\tpid\tinstance\tgroup\tcomm\tkthread\t"
            "k_insts");
    writeStatsHeader(o, "", caps);
    fprintf(o, "\tpc_cold\tu_uniq_insts\tk_uniq_insts\tu_uniq_lines\t"
            "k_uniq_lines");
    for (int b = 1; b < NumBranch; b++)
        fprintf(o, "\tbr_%s\tbr_%s_taken\tk_br_%s", kBranchNames[b],
                kBranchNames[b], kBranchNames[b]);
    fprintf(o, "\tu_rw_insts\tk_rw_insts\tu_rw_lines\tk_rw_lines\trw_br\n");
    for (size_t i = 0; i < threads.size(); i++) {
        const Thread &t = *threads[i];
        if (!t.lines.insts)
            continue;
        uint64_t ui[2] = {}, ul[2] = {}, br[NumBranch] = {},
                 tk[NumBranch] = {}, kbr[NumBranch] = {};
        uint64_t rwi[2] = {}, rwl[2] = {}, rwb = 0;
        t.pcs.each([&](uint64_t pc, uint32_t v) {
            int k = pc >> 63;
            uint64_t top = pc >> 48;
            bool rwPc = top == 0x4000 || top == 0xc000;   // a later version
            ui[k]++;
            rwi[k] += rwPc;
            Branch b = Branch(v & 0xff);
            if (b != NotBranch) {
                br[b]++;
                rwb += rwPc;
                if (v >> 8 & 1) tk[b]++;
                if (k) kbr[b]++;
            }
        });
        t.uniqLines.each([&](uint64_t l, uint32_t) {
            int k = l >> 57;
            ul[k]++;
            // A later version: user bit 50; kernel bit 57 with bits 42-56
            // clear (a real kernel line has them all set).
            rwl[k] += k ? ((l >> 42) & 0x7fff) == 0 : (l >> 50) & 1;
        });
        fprintf(o, "%zu\t%" PRId64 "\t%" PRId64 "\t%u\t%s\t%s\t%d\t%"
                PRIu64, i, t.tgid, t.pid, t.instance,
                groups[t.group].name.c_str(), t.comm.c_str(), t.kthread,
                t.kInsts);
        writeStats(o, t.lines);
        fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64
                "\t%" PRIu64, t.pcCold, ui[0], ui[1], ul[0], ul[1]);
        for (int b = 1; b < NumBranch; b++)
            fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64, br[b], tk[b],
                    kbr[b]);
        fprintf(o, "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64 "\t%" PRIu64
                "\t%" PRIu64 "\n", rwi[0], rwi[1], rwl[0], rwl[1], rwb);
    }
    fclose(o);

    // thread_bins.tsv: per thread, bin size and cut, the bins' values
    // weighted by their instructions. Only whole bins count (a thread's own
    // count reached the size; the run's window ended), unless the thread has
    // none, and then its partial bins do (partial_only).
    o = fopen((outdir + "/thread_bins.tsv").c_str(), "w");
    fprintf(o, "thread\tcut\tbin_insts\tbins\tpartial_only\tsum_w");
    const char *binVal[kBinVals] = {"u_insts", "k_insts", "u_lines",
                                    "k_lines"};
    std::vector<std::string> brCols;
    for (int b = 1; b < NumBranch; b++)
        brCols.push_back(std::string("br_") + kBranchNames[b]);
    for (int b = 1; b < NumBranch; b++)
        binVal[3 + b] = brCols[b - 1].c_str();
    binVal[kBinTaken] = "taken";
    for (int i = 0; i < kBinVals; i++)
        fprintf(o, "\tsum_wv_%s", binVal[i]);
    for (int i = 0; i < kBinVals; i++)
        fprintf(o, "\tmax_%s", binVal[i]);
    fprintf(o, "\n");
    for (size_t i = 0; i < threads.size(); i++) {
        Thread &t = *threads[i];
        if (!t.lines.insts)
            continue;
        for (size_t c = 0; c < t.bins.size(); c++) {
            BinAcc &a = t.bins[c];
            uint64_t size = binSizes[c / 2];
            bool whole = c & 1 ? (a.cur + 1) * size <= total : a.w == size;
            bool partialOnly = false;
            if (a.cur != kEmpty && (whole || a.bins == 0)) {
                partialOnly = !whole && a.bins == 0;
                a.close();
            }
            fprintf(o, "%zu\t%s\t%" PRIu64 "\t%" PRIu64 "\t%d\t%" PRIu64,
                    i, c & 1 ? "run" : "own", size, a.bins, partialOnly,
                    a.sumW);
            for (int v = 0; v < kBinVals; v++)
                fprintf(o, "\t%" PRIu64, a.sumWV[v]);
            for (int v = 0; v < kBinVals; v++)
                fprintf(o, "\t%" PRIu64, a.maxV[v]);
            fprintf(o, "\n");
        }
    }
    fclose(o);

    o = fopen((outdir + "/thread_hist.tsv").c_str(), "w");
    fprintf(o, "thread\tview\tbucket\tlo\thi\taccesses\n");
    for (size_t i = 0; i < threads.size(); i++) {
        const Thread &t = *threads[i];
        std::string id = std::to_string(i);
        writeHist(o, id, "pc", t.pcHist);
        writeHist(o, id, "line", t.lines.privHist);
        writeHist(o, id, "line_shared", t.lines.sharedHist);
    }
    fclose(o);

    o = fopen((outdir + "/hist.tsv").c_str(), "w");
    fprintf(o, "group\tview\tbucket\tlines_lo\tlines_hi\taccesses\n");
    for (const Group &gr : groups) {
        writeHist(o, gr.name, "private", gr.byInstance.privHist);
        writeHist(o, gr.name, "shared", gr.byInstance.sharedHist);
        writeHist(o, gr.name, "name_private", gr.byName.privHist);
        writeHist(o, gr.name, "name_shared", gr.byName.sharedHist);
    }
    fclose(o);

    fprintf(stderr, "%" PRIu64 " instructions, %zu markers, %zu/%zu switches "
            "used, %" PRIu64 "/%zu execs applied, %" PRIu64 " renames, %zu "
            "threads; "
            "distinct: %zu instructions, %zu lines, %zu pages (by name: %zu, "
            "%zu, %zu); final count %" PRIu64 " (NOPs %s); instruction "
            "count off at %" PRIu64 " markers (max %" PRIu64 ")\n", total,
            markers,
            nextSwitch, switches.size(), execsApplied, execs.size(), renames,
            threads.size(),
            fpInst.insts.size(), fpInst.lines.size(), fpInst.pages.size(),
            fpName.insts.size(), fpName.lines.size(), fpName.pages.size(),
            countNops == 1 ? gNops : g,
            countNops < 0 ? "undecided" : countNops ? "counted" : "not counted",
            countMismatches, maxMismatch);
    uint64_t rwPcs = 0, rwFlips = 0;
    for (const RwCount &r : rw) rwPcs += r.pcs, rwFlips += r.flips;
    fprintf(stderr, "code versions: %s; %" PRIu64 " encodings in the trace, "
            "%zu PC versions (%u serials), %" PRIu64 " PCs with several "
            "encodings, %zu lines rewritten, %" PRIu64 " flips back; %"
            PRIu64 " instructions without a known encoding\n",
            !versionsOn ? "off (no encodings in the trace)"
                        : proxy && !encFields ? "mnemonics as encodings"
                                              : "encodings",
            encFields, versions.size() - 1, nextSerial, rwPcs,
            lineVersions.size() - 1, rwFlips, missingEnc);
    return 0;
}
